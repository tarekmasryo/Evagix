from __future__ import annotations

import json
import subprocess
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from evagix.cli import main
from evagix.commands import git_cli, git_cmds, reference_drift
from evagix.reference_drift import DeletedReference, ReferenceDriftReport


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=Fixture User", "-c", "user.email=fixture@example.invalid", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def deleted_reference_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-b", "main")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    target = scripts / "test.sh"
    target.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("Use the [test script](scripts/test.sh).\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--no-gpg-sign", "-m", "initial")
    _git(tmp_path, "checkout", "-b", "feature")
    target.unlink()
    _git(tmp_path, "add", "-u")
    _git(tmp_path, "commit", "--no-gpg-sign", "-m", "remove script")
    return tmp_path


def test_json_report_with_finding_is_advisory_and_matches_packaged_schema(
    deleted_reference_repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        git_cmds, "_facts", lambda *args: pytest.fail("Reference inspection must not scan the worktree")
    )
    assert main(["changed", str(deleted_reference_repo), "--references", "--format", "json"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    schema = json.loads(files("evagix.schemas").joinpath("reference-drift.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    assert payload["completeness"] == "complete"
    assert payload["scope"]["working_tree"] == "excluded"
    assert payload["findings"] == [
        {
            "code": "context.deleted-file-reference",
            "document": "AGENTS.md",
            "line": 1,
            "column": 23,
            "target": "scripts/test.sh",
            "severity": "advisory",
        }
    ]


@pytest.mark.parametrize("output_format", ["text", "github-annotations", "markdown"])
def test_reference_output_formats_report_the_source(
    deleted_reference_repo: Path, capsys: pytest.CaptureFixture[str], output_format: str
) -> None:
    assert main(["changed", str(deleted_reference_repo), "--references", "--format", output_format]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "AGENTS.md" in captured.out
    assert "scripts/test.sh" in captured.out
    if output_format == "github-annotations":
        assert "::notice " in captured.out
        assert "::error " not in captured.out


def test_legacy_changed_dispatch_and_exit_are_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def legacy(root: Path, **kwargs: object) -> int:
        assert root == tmp_path
        calls.append(kwargs)
        return 1

    monkeypatch.setattr(git_cli, "_cmd_changed", legacy)
    monkeypatch.setattr(git_cli, "_cmd_reference_drift", lambda *args, **kwargs: pytest.fail("Unexpected new mode"))
    assert main(["changed", str(tmp_path), "--base", "old", "--head", "new", "--format", "json"]) == 1
    assert len(calls) == 1
    assert calls[0]["base"] == "old"
    assert calls[0]["head"] == "new"
    assert calls[0]["output_format"] == "json"


@pytest.mark.parametrize("output_format", ["text", "json", "github-annotations"])
def test_incomplete_reference_report_has_distinct_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], output_format: str
) -> None:
    report = SimpleNamespace(complete=False)
    monkeypatch.setattr(reference_drift, "build_reference_drift_report", lambda *args, **kwargs: report)
    for name in ["text", "json", "github_annotations"]:
        monkeypatch.setattr(reference_drift, f"render_reference_drift_{name}", lambda value: "incomplete\n")
    assert main(["changed", str(tmp_path), "--references", "--format", output_format]) == 1
    captured = capsys.readouterr()
    assert captured.out == "incomplete\n"
    assert captured.err == ""


@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
def test_reference_errors_use_stderr_and_redaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], error_type: type[Exception]
) -> None:
    secret = "ghp_" + "a" * 36

    def fail(*args: object, **kwargs: object) -> None:
        raise error_type(f"Could not inspect repository: {secret}")

    monkeypatch.setattr(reference_drift, "build_reference_drift_report", fail)
    assert main(["changed", str(tmp_path), "--references", "--format", "json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("ERROR: Could not inspect repository:")
    assert secret not in captured.err


def test_missing_revision_does_not_emit_a_clean_json_report(
    deleted_reference_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["changed", str(deleted_reference_repo), "--references", "--base", "missing", "--format", "json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("ERROR:")


@pytest.mark.parametrize("is_file", [False, True])
def test_invalid_root_uses_reference_mode_error_exit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], is_file: bool
) -> None:
    root = tmp_path / "not-a-directory"
    if is_file:
        root.write_text("not a repository", encoding="utf-8")
    assert main(["changed", str(root), "--references", "--format", "json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("ERROR:")


def test_markdown_reports_committed_revisions_and_supported_scope(
    deleted_reference_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    revisions = subprocess.run(
        ["git", "rev-parse", "main", "HEAD"],
        cwd=deleted_reference_repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert main(["changed", str(deleted_reference_repo), "--references", "--format", "markdown"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.startswith("## Deleted-file reference review\n")
    assert "**Inspection:** complete" in captured.out
    assert "**Findings:** 1" in captured.out
    assert all(revision in captured.out for revision in revisions)
    for label in ("- Base:", "- Head:", "- Merge base:", "- Inspected documents:"):
        assert label in captured.out
    assert "AGENTS.md:1:23" in captured.out
    assert "scripts/test.sh" in captured.out
    assert "explicit local Markdown links only" in captured.out
    assert "Working-tree changes are excluded" in captured.out
    assert "does not decide merge readiness or select a replacement file" in captured.out


@pytest.mark.parametrize("incomplete", [False, True])
def test_markdown_empty_results_do_not_hide_incomplete_inspection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    incomplete: bool,
) -> None:
    report = ReferenceDriftReport(
        "a" * 40,
        "b" * 40,
        "a" * 40,
        ["README.md"],
        ["AGENTS.md: invalid UTF-8; not inspected."] if incomplete else [],
        [],
    )
    monkeypatch.setattr(reference_drift, "build_reference_drift_report", lambda *args, **kwargs: report)
    assert main(["changed", str(tmp_path), "--references", "--format", "markdown"]) == (1 if incomplete else 0)
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "No deleted-file references found in the inspected documents." in captured.out
    assert ("**Inspection:** incomplete" in captured.out) is incomplete
    assert ("### Inspection limits" in captured.out) is incomplete
    assert ("Complete the missing inspection" in captured.out) is incomplete
    assert "PASS" not in captured.out


def test_markdown_rejects_legacy_changed_without_scanning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(git_cli, "_cmd_changed", lambda *args, **kwargs: pytest.fail("Unexpected legacy scan"))
    monkeypatch.setattr(
        git_cli, "_cmd_reference_drift", lambda *args, **kwargs: pytest.fail("Unexpected reference scan")
    )
    assert main(["changed", str(tmp_path), "--format", "markdown"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR: Markdown output requires changed --references.\n"


def test_markdown_contains_untrusted_fields_and_redacts_before_formatting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "ghp_" + "a" * 36
    injected = (
        f"file`![image](https://example.invalid/x) <img src='https://example.invalid/y'> @reviewer {secret}"
        "\n## forged\n::error::forged\u202e\x1b[31mاختبار.md"
    )
    report = ReferenceDriftReport(
        "a" * 40,
        "b" * 40,
        "a" * 40,
        ["AGENTS.md"],
        [injected],
        [DeletedReference("AGENTS.md", 3, 10, injected)],
    )
    monkeypatch.setattr(reference_drift, "build_reference_drift_report", lambda *args, **kwargs: report)
    assert main(["changed", str(tmp_path), "--references", "--format", "markdown"]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert secret not in captured.out
    assert "[REDACTED]" in captured.out
    assert "اختبار.md" in captured.out
    assert "\x1b" not in captured.out
    assert "\u202e" not in captured.out
    assert "\n## forged" not in captured.out
    assert "\n::error::forged" not in captured.out
    assert "Deleted target: `` " in captured.out
    assert captured.out.count("## Deleted-file reference review") == 1
    assert "**Inspection:** incomplete" in captured.out


def test_markdown_refuses_oversized_output_without_a_partial_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = ReferenceDriftReport(
        "a" * 40,
        "b" * 40,
        "a" * 40,
        ["AGENTS.md"],
        [],
        [DeletedReference("AGENTS.md", line, 10, "segment/" * 64 + "file.md") for line in range(1, 801)],
    )
    monkeypatch.setattr(reference_drift, "build_reference_drift_report", lambda *args, **kwargs: report)
    assert main(["changed", str(tmp_path), "--references", "--format", "markdown"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "450000" in captured.err
    assert captured.err.startswith("ERROR:")
