from __future__ import annotations

import json
import subprocess
from importlib.resources import files
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from evagix import coverage_drift as drift
from evagix.cli import main
from evagix.commands import coverage_drift as command
from evagix.commands import git_cli
from evagix.reports import coverage_drift as reports

WORKFLOW = ".github/workflows/ci.yml"


def workflow(value: str, *, step: str = "Coverage", command: str | None = None) -> str:
    invocation = (
        command
        or f'python -m pytest --cov=app --cov-branch --cov-fail-under={value} --junitxml="$RUNNER_TEMP/results.xml"'
    )
    return f"name: CI\non: [push, pull_request]\njobs:\n  quality:\n    runs-on: ubuntu-latest\n    steps:\n      - name: {step}\n        run: {invocation}\n"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture User",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.autocrlf=false",
            *args,
        ],
        cwd=repo,
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def repository(root: Path, before: dict[str, str | bytes], after: dict[str, str | bytes]) -> Path:
    root.mkdir(exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    for path, content in before.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    (root / "README.md").write_text("# Local fixture\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    git(root, "checkout", "-qb", "feature")
    for path in before.keys() - after.keys():
        (root / path).unlink()
    for path, content in after.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    git(root, "add", ".")
    git(root, "commit", "--allow-empty", "-qm", "change")
    return root


@pytest.mark.parametrize(
    "before,after,lowered",
    [
        ("80", "70", True),
        ("80", "90", False),
        ("80", "80", False),
        ("080.00", "80", False),
        ("80.00000000000000000000000000001", "80", True),
        ("100", "0", True),
    ],
)
def test_literal_threshold_comparison(tmp_path: Path, before: str, after: str, lowered: bool) -> None:
    repo = repository(
        tmp_path, {WORKFLOW: workflow(before)}, {WORKFLOW: workflow(after).replace("name: CI", "name: CI updated")}
    )
    report = drift.build_coverage_drift_report(repo)
    assert report.complete and bool(report.findings) is lowered
    assert report.compared_thresholds == 1
    if lowered:
        finding = report.findings[0]
        assert finding.previous_value == before and finding.value == after
        assert finding.code == "ci.coverage-threshold-lowered" and finding.severity == "advisory"
        assert finding.line == finding.previous_line == 8
        assert finding.column == workflow(after).splitlines()[7].index("--cov-fail-under") + 1
        assert finding.previous_column == workflow(before).splitlines()[7].index("--cov-fail-under") + 1


@pytest.mark.parametrize(
    "after",
    [
        workflow("70", command="python -m pytest --cov=app"),
        workflow("$MINIMUM"),
        workflow("${{ env.MINIMUM }}"),
        workflow(""),
        workflow("70", step="Other tests"),
        workflow("70").replace("--cov=app", "--cov=other"),
        b"\xff",
        "jobs: [not-a-block-workflow]\n",
    ],
)
def test_unavailable_or_noncomparable_evidence_is_not_zero(tmp_path: Path, after: str | bytes) -> None:
    repo = repository(tmp_path, {WORKFLOW: workflow("80")}, {WORKFLOW: after})
    report = drift.build_coverage_drift_report(repo)
    assert not report.complete and not report.findings and report.compared_thresholds == 0


def test_file_removal_or_rename_does_not_assume_zero(tmp_path: Path) -> None:
    repo = repository(tmp_path, {WORKFLOW: workflow("80")}, {".github/workflows/renamed.yml": workflow("70")})
    report = drift.build_coverage_drift_report(repo)
    assert not report.complete and not report.findings
    assert any("missing" in item for item in report.limitations)


def test_new_workflows_and_other_ci_formats_are_outside_scope(tmp_path: Path) -> None:
    repo = repository(
        tmp_path, {".gitlab-ci.yml": workflow("80")}, {".gitlab-ci.yml": workflow("70"), WORKFLOW: workflow("10")}
    )
    report = drift.build_coverage_drift_report(repo)
    assert report.complete and not report.findings and not report.inspected_files


def test_incomplete_workflow_does_not_hide_independent_finding(tmp_path: Path) -> None:
    other = ".github/workflows/broken.yaml"
    repo = repository(
        tmp_path, {WORKFLOW: workflow("80"), other: workflow("90")}, {WORKFLOW: workflow("70"), other: b"\xff"}
    )
    report = drift.build_coverage_drift_report(repo)
    assert not report.complete and len(report.findings) == 1
    assert report.findings[0].path == WORKFLOW


def test_committed_merge_base_comparison_ignores_working_tree_and_base_tip(tmp_path: Path) -> None:
    repo = repository(tmp_path, {WORKFLOW: workflow("80")}, {WORKFLOW: workflow("70")})
    head = git(repo, "rev-parse", "HEAD")
    ancestor = git(repo, "rev-parse", "main")
    git(repo, "checkout", "-q", "main")
    (repo / WORKFLOW).write_text(workflow("90"), encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base advance")
    git(repo, "checkout", "-q", "feature")
    (repo / WORKFLOW).write_text(workflow("99"), encoding="utf-8")
    report = drift.build_coverage_drift_report(repo)
    assert report.merge_base == ancestor and report.head == head and report.base != ancestor
    assert (report.findings[0].previous_value, report.findings[0].value) == ("80", "70")


def test_symlink_blob_is_not_followed(tmp_path: Path) -> None:
    repo = repository(tmp_path, {WORKFLOW: workflow("80")}, {WORKFLOW: workflow("70")})
    oid = git(repo, "rev-parse", f"HEAD:{WORKFLOW}")
    git(repo, "update-index", "--cacheinfo", f"120000,{oid},{WORKFLOW}")
    git(repo, "commit", "-qm", "nonregular workflow")
    report = drift.build_coverage_drift_report(repo)
    assert not report.complete and not report.findings
    assert any("not a regular tracked file" in item for item in report.limitations)


@pytest.mark.parametrize("budget", ["_SOURCE_LIMIT", "_FILE_LIMIT", "_FINDING_LIMIT"])
def test_limits_are_explicit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, budget: str) -> None:
    repo = repository(tmp_path, {WORKFLOW: workflow("80")}, {WORKFLOW: workflow("70")})
    monkeypatch.setattr(drift, budget, 0)
    report = drift.build_coverage_drift_report(repo)
    assert not report.complete and not report.findings


@pytest.mark.parametrize("output_format", ["text", "json", "markdown", "github-annotations"])
def test_cli_is_advisory_and_json_matches_packaged_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], output_format: str
) -> None:
    repo = repository(tmp_path, {WORKFLOW: workflow("80")}, {WORKFLOW: workflow("70")})
    assert main(["changed", str(repo), "--coverage", "--format", output_format]) == 0
    captured = capsys.readouterr()
    assert not captured.err
    assert ("::notice" if output_format == "github-annotations" else "ci.coverage-threshold-lowered") in captured.out
    if output_format == "json":
        payload = json.loads(captured.out)
        schema = json.loads(files("evagix.schemas").joinpath("coverage-drift.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
        assert payload["policy_decision"] == "not_evaluated" and payload["completeness"] == "complete"
    else:
        assert "Advisory only" in captured.out
        decrease = "80%25 to 70%25" if output_format == "github-annotations" else "80% to 70%"
        assert decrease in captured.out and "::error" not in captured.out


def test_incomplete_and_invalid_ref_exits_remain_distinct(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = repository(tmp_path, {WORKFLOW: workflow("80")}, {WORKFLOW: workflow("$MINIMUM")})
    assert main(["changed", str(repo), "--coverage", "--format", "json"]) == 1
    captured = capsys.readouterr()
    assert not captured.err and json.loads(captured.out)["completeness"] == "incomplete"
    assert main(["changed", str(repo), "--coverage", "--head", "missing", "--format", "json"]) == 2
    captured = capsys.readouterr()
    assert not captured.out and captured.err.startswith("ERROR:")


@pytest.mark.parametrize("flag", ["--tests", "--scripts", "--references"])
def test_modes_are_mutually_exclusive(flag: str) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["changed", "--coverage", flag])
    assert exc.value.code == 2


@pytest.mark.parametrize(
    "mode,handler,code",
    [
        ([], "_cmd_changed", 1),
        (["--tests"], "_cmd_test_changes", 0),
        (["--scripts"], "_cmd_script_drift", 0),
        (["--references"], "_cmd_reference_drift", 0),
    ],
)
def test_existing_modes_never_enter_new_inspection(
    monkeypatch: pytest.MonkeyPatch, mode: list[str], handler: str, code: int
) -> None:
    monkeypatch.setattr(git_cli, handler, lambda *a, **k: code)
    monkeypatch.setattr(
        git_cli, "_cmd_coverage_drift", lambda *a, **k: pytest.fail("coverage inspection must be opt-in")
    )
    assert main(["changed", *mode]) == code


def test_all_outputs_contain_untrusted_metadata_and_omit_commands() -> None:
    finding = drift.CoverageDriftFinding(
        ".github/workflows/token=private-value.yml",
        "api_key=private-job",
        "name",
        "token=private-step\n::error::fake",
        "80",
        "70",
        8,
        20,
        9,
        20,
    )
    report = drift.CoverageDriftReport(
        "a" * 40, "b" * 40, "a" * 40, [finding.path], 1, ["token=private-limit"], [finding]
    )
    for renderer in (
        reports.render_coverage_drift_text,
        reports.render_coverage_drift_json,
        reports.render_coverage_drift_markdown,
        reports.render_coverage_drift_annotations,
    ):
        output = renderer(report)
        assert all(secret not in output for secret in ["private-value", "private-job", "private-step", "private-limit"])
        assert "\n::error::" not in output and "signature" not in output
    json.loads(reports.render_coverage_drift_json(report))


def test_render_error_has_no_partial_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = repository(tmp_path, {WORKFLOW: workflow("80")}, {WORKFLOW: workflow("70")})

    def reject(report: drift.CoverageDriftReport) -> str:
        raise ValueError("report exceeds rendering limit")

    monkeypatch.setattr(command, "render_coverage_drift_markdown", reject)
    assert main(["changed", str(repo), "--coverage", "--format", "markdown"]) == 2
    captured = capsys.readouterr()
    assert not captured.out and "rendering limit" in captured.err
