from __future__ import annotations

import json
import subprocess
from importlib.resources import files
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from evagix import script_drift
from evagix.cli import main
from evagix.commands import git_cmds
from evagix.commands import script_drift as command
from evagix.reference_drift import DeletedReference, ReferenceDriftReport


@pytest.fixture
def script_repo(tmp_path: Path) -> Path:
    def git(*args: str) -> None:
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Fixture User",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "commit.gpgsign=false",
                *args,
            ],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

    git("init", "-q", "-b", "main")
    (tmp_path / "scripts").mkdir()
    script = tmp_path / "scripts/old.py"
    script.write_text("raise SystemExit(97)\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        "Run `python scripts/old.py`.\n\nSee [script](scripts/old.py).\n", encoding="utf-8"
    )
    git("add", ".")
    git("commit", "-qm", "base")
    git("checkout", "-qb", "feature")
    script.unlink()
    git("add", "-u")
    git("commit", "-qm", "remove script")
    return tmp_path


def test_new_cli_json_contract_and_legacy_link_mode_are_separate(
    script_repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(git_cmds, "_facts", lambda *args: pytest.fail("Script review must not scan the working tree"))
    assert main(["changed", str(script_repo), "--scripts", "--format", "json"]) == 0
    captured = capsys.readouterr()
    assert not captured.err
    payload = json.loads(captured.out)
    schema = json.loads(files("evagix.schemas").joinpath("script-drift.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    assert payload["kind"] == "deleted_script_drift"
    assert payload["completeness"] == "complete"
    assert payload["findings"] == [
        {
            "code": "context.deleted-script-reference",
            "document": "AGENTS.md",
            "line": 1,
            "column": 13,
            "target": "scripts/old.py",
            "severity": "advisory",
        }
    ]
    assert main(["changed", str(script_repo), "--references", "--format", "json"]) == 0
    links = json.loads(capsys.readouterr().out)
    legacy_schema = json.loads(
        files("evagix.schemas").joinpath("reference-drift.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(legacy_schema).validate(links)
    assert links["kind"] == "deleted_reference_drift"
    assert len(links["findings"]) == 1 and links["findings"][0]["line"] == 3


@pytest.mark.parametrize("output_format", ["text", "markdown", "github-annotations"])
def test_new_cli_formats_are_advisory(
    script_repo: Path, capsys: pytest.CaptureFixture[str], output_format: str
) -> None:
    assert main(["changed", str(script_repo), "--scripts", "--format", output_format]) == 0
    captured = capsys.readouterr()
    assert not captured.err
    assert "AGENTS.md:1:13" in captured.out or "file=AGENTS.md,line=1,col=13" in captured.out
    assert "scripts/old.py" in captured.out
    assert "root" in captured.out and "assumed" in captured.out
    assert "::error" not in captured.out


def test_link_and_script_modes_cannot_be_combined(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["changed", "--references", "--scripts"])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert not captured.out and "not allowed" in captured.err


@pytest.mark.parametrize("output_format", ["json", "text", "markdown", "github-annotations"])
def test_incomplete_read_has_distinct_exit_and_no_clean_claim(
    script_repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, output_format: str
) -> None:
    monkeypatch.setattr(script_drift, "_DOCUMENT_LIMIT", 4)
    assert main(["changed", str(script_repo), "--scripts", "--format", output_format]) == 1
    captured = capsys.readouterr()
    assert not captured.err
    assert "incomplete" in captured.out or "::warning::" in captured.out


def test_missing_revision_emits_error_without_partial_report(
    script_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["changed", str(script_repo), "--scripts", "--head", "missing-branch", "--format", "json"]) == 2
    captured = capsys.readouterr()
    assert not captured.out and captured.err.startswith("ERROR:")


def test_invalid_root_uses_error_exit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["changed", str(tmp_path / "missing"), "--scripts", "--format", "json"]) == 2
    captured = capsys.readouterr()
    assert not captured.out and captured.err.startswith("ERROR:")


def test_empty_results_do_not_claim_execution_or_merge_approval(
    script_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["changed", str(script_repo), "--scripts", "--head", "main", "--format", "markdown"]) == 0
    captured = capsys.readouterr()
    assert "Findings:** 0" in captured.out
    assert "within this scope" in captured.out
    assert "does not prove execution failure" in captured.out


def test_renderers_redact_before_output_and_contain_markdown() -> None:
    report = ReferenceDriftReport(
        "a" * 40,
        "b" * 40,
        "a" * 40,
        ["AGENTS.md"],
        [],
        [
            DeletedReference(
                "AGENTS.md",
                1,
                13,
                "api_key=synthetic-private-value",
                code="context.deleted-script-reference",
            )
        ],
    )
    for renderer in (
        script_drift.render_script_drift_json,
        script_drift.render_script_drift_text,
        script_drift.render_script_drift_markdown,
        script_drift.render_script_drift_github_annotations,
    ):
        assert "synthetic-private-value" not in renderer(report)
    report.findings[:] = [DeletedReference("AGENTS.md", 1, 13, "file``[link](https://example.invalid)\u202e.py")]
    markdown = script_drift.render_script_drift_markdown(report)
    assert "``` file``[link](https://example.invalid)\\u202e.py ```" in markdown
    assert "\u202e" not in markdown


def test_oversized_markdown_fails_without_partial_stdout(
    script_repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def reject(_report: ReferenceDriftReport) -> str:
        raise ValueError("Markdown report exceeds the output limit.")

    monkeypatch.setattr(command, "render_script_drift_markdown", reject)
    assert main(["changed", str(script_repo), "--scripts", "--format", "markdown"]) == 2
    captured = capsys.readouterr()
    assert not captured.out and "output limit" in captured.err
