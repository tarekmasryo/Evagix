from __future__ import annotations

import json
import subprocess
from importlib.resources import files
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from evagix import test_changes as changes
from evagix.cli import main
from evagix.commands import git_cli
from evagix.commands import test_changes as command
from evagix.reports import test_changes as reports


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    def git(*args: str) -> None:
        subprocess.run(
            [
                "git",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "core.autocrlf=false",
                "-c",
                "user.name=Fixture User",
                "-c",
                "user.email=fixture@example.invalid",
                *args,
            ],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

    git("init", "-q", "-b", "main")
    source = "import pytest\n\ndef test_existing():\n    pass\n"
    (tmp_path / "test_example.py").write_text(source, encoding="utf-8")
    (tmp_path / "test_removed.py").write_text("def test_old():\n    pass\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "base")
    git("checkout", "-qb", "feature")
    (tmp_path / "test_example.py").write_text(
        source.replace("def test_existing", "@pytest.mark.skip(reason='later')\ndef test_existing"), encoding="utf-8"
    )
    git("rm", "test_removed.py")
    git("add", ".")
    git("commit", "-qm", "test changes")
    return tmp_path


def test_preview_json_schema_and_advisory_exit(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["changed", str(repo), "--tests", "--format", "json"]) == 0
    captured = capsys.readouterr()
    assert not captured.err
    payload = json.loads(captured.out)
    schema = json.loads(files("evagix.schemas").joinpath("test-changes.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    assert payload["completeness"] == "complete" and payload["policy_decision"] == "not_evaluated"
    assert {item["code"] for item in payload["findings"]} == {"tests.deleted-file", "tests.unconditional-skip-added"}
    assert payload["scope"]["working_tree"] == "excluded" and payload["scope"]["collection"] == "not_evaluated"


@pytest.mark.parametrize("output_format", ["text", "markdown", "github-annotations"])
def test_human_outputs_preserve_advisory_meaning_and_revision_locations(
    repo: Path, capsys: pytest.CaptureFixture[str], output_format: str
) -> None:
    assert main(["changed", str(repo), "--tests", "--format", output_format]) == 0
    captured = capsys.readouterr()
    assert not captured.err and "Advisory" in captured.out
    assert "test_example.py" in captured.out and "test_removed.py" in captured.out
    assert "merge_base" in captured.out and "head" in captured.out
    if output_format == "github-annotations":
        assert "::notice file=test_example.py,line=3,col=2" in captured.out
        assert "file=test_removed.py" not in captured.out
        assert "::error" not in captured.out


@pytest.mark.parametrize("mode", ["--references", "--scripts"])
def test_preview_modes_are_mutually_exclusive(mode: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["changed", "--tests", mode])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert not captured.out and "not allowed" in captured.err


@pytest.mark.parametrize(
    "mode,handler,result",
    [
        ([], "_cmd_changed", 1),
        (["--scripts"], "_cmd_script_drift", 0),
        (["--references"], "_cmd_reference_drift", 0),
    ],
)
def test_existing_dispatch_and_return_codes_are_unchanged(
    monkeypatch: pytest.MonkeyPatch, mode: list[str], handler: str, result: int
) -> None:
    observed = []

    def previous(*args: object, **kwargs: object) -> int:
        observed.append(kwargs)
        return result

    monkeypatch.setattr(git_cli, handler, previous)
    monkeypatch.setattr(git_cli, "_cmd_test_changes", lambda *a, **k: pytest.fail("new mode must be opt-in"))
    assert main(["changed", *mode]) == result
    assert len(observed) == 1 and observed[0]["base"] == "main" and observed[0]["head"] == "HEAD"


@pytest.mark.parametrize("output_format", ["text", "json", "markdown", "github-annotations"])
def test_incomplete_inspection_retains_findings_and_has_distinct_exit(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, output_format: str
) -> None:
    monkeypatch.setattr(changes, "_SOURCE_LIMIT", 4)
    assert main(["changed", str(repo), "--tests", "--format", output_format]) == 1
    captured = capsys.readouterr()
    assert not captured.err and "test_removed.py" in captured.out
    assert "incomplete" in captured.out or "::warning::" in captured.out


def test_invalid_refs_emit_no_partial_output(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["changed", str(repo), "--tests", "--head", "missing", "--format", "json"]) == 2
    captured = capsys.readouterr()
    assert not captured.out and captured.err.startswith("ERROR:")


def test_invalid_root_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["changed", str(tmp_path / "absent"), "--tests"]) == 2
    captured = capsys.readouterr()
    assert not captured.out and captured.err.startswith("ERROR:")


def test_empty_scope_does_not_imply_test_success(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["changed", str(repo), "--tests", "--head", "main"]) == 0
    output = capsys.readouterr().out
    assert "No findings within the inspected scope" in output
    assert "execution, test quality and merge readiness are not verified" in output


def test_all_renderers_redact_and_contain_repository_text() -> None:
    report = changes.TestChangesReport(
        "a" * 40,
        "b" * 40,
        "a" * 40,
        [],
        [],
        [],
        [
            changes.TestChangeFinding(
                "tests.unconditional-skip-added",
                "test_api_key=synthetic-private.py",
                "head",
                4,
                2,
                "test_token=synthetic-secret",
                "old.py",
                1,
                "test",
            ),
        ],
    )
    for renderer in (
        reports.render_test_changes_json,
        reports.render_test_changes_text,
        reports.render_test_changes_markdown,
        reports.render_test_changes_annotations,
    ):
        result = renderer(report)
        assert "synthetic-private" not in result and "synthetic-secret" not in result
    report.findings[:] = [
        changes.TestChangeFinding(
            "tests.unconditional-skip-added",
            "test_,line=99\n::error::`[link](https://example.invalid)\u202e.py",
            "head",
            4,
            2,
            "test_example",
            "old.py",
            1,
            "test",
        )
    ]
    text = reports.render_test_changes_text(report)
    markdown = reports.render_test_changes_markdown(report)
    annotations = reports.render_test_changes_annotations(report)
    assert "\u202e" not in text and "\u202e" not in markdown
    assert "\n::error::" not in text + markdown + annotations
    assert "file=" not in annotations
    assert "```" not in markdown  # one embedded backtick requires a two-backtick delimiter


def test_annotation_properties_escape_punctuation() -> None:
    report = changes.TestChangesReport(
        "a" * 40,
        "b" * 40,
        "a" * 40,
        [],
        [],
        [],
        [
            changes.TestChangeFinding(
                "tests.unconditional-skip-added",
                "test_,line=99:file%.py",
                "head",
                4,
                2,
                "test_example",
                "old.py",
                1,
                "test",
            ),
        ],
    )
    annotations = reports.render_test_changes_annotations(report)
    assert "file=test_%2Cline=99%3Afile%25.py,line=4,col=2" in annotations


def test_markdown_output_limit_has_no_partial_stdout(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def reject(_report: changes.TestChangesReport) -> str:
        raise ValueError("Markdown report exceeds the output limit.")

    monkeypatch.setattr(command, "render_test_changes_markdown", reject)
    assert main(["changed", str(repo), "--tests", "--format", "markdown"]) == 2
    captured = capsys.readouterr()
    assert not captured.out and "output limit" in captured.err
