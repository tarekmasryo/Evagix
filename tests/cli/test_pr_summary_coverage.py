from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from evagix import coverage_drift, pr_summary
from evagix.verification.github_pr_checks import PullRequestChecks

PR_URL = "https://github.com/owner/repo/pull/7"
WORKFLOW = ".github/workflows/ci.yml"
HEADING = "## CI coverage threshold review\n"


def _workflow(value: str, *, step: str = "Coverage") -> str:
    return (
        "name: CI\non: [push, pull_request]\njobs:\n  quality:\n    runs-on: ubuntu-latest\n"
        f"    steps:\n      - name: {step}\n"
        f"        run: python -m pytest --cov=app --cov-branch --cov-fail-under={value}\n"
    )


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
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
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


@dataclass(frozen=True)
class _Repo:
    root: Path
    base: str
    head: str

    def args(self, *, expectations: bool = False) -> list[str]:
        args = [PR_URL, "--repo", str(self.root), "--base", self.base, "--head", self.head]
        if expectations:
            args.extend(("--expectations", ".github/checks.json"))
        return args


def _repository(root: Path, before: dict[str, str | bytes], after: dict[str, str | bytes]) -> _Repo:
    _git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("# Local fixture\n", encoding="utf-8")
    (root / ".github").mkdir()
    (root / ".github/checks.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "repository_id": 17,
                "checks": [{"revision": "head", "kind": "check_run", "name": "tests", "producer_id": 9}],
            }
        ),
        encoding="utf-8",
    )
    for path, content in before.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "base")
    base = _git(root, "rev-parse", "HEAD")
    for path in before.keys() - after.keys():
        (root / path).unlink()
    for path, content in after.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    _git(root, "add", ".")
    _git(root, "commit", "--allow-empty", "-qm", "head")
    return _Repo(root, base, _git(root, "rev-parse", "HEAD"))


@pytest.fixture(autouse=True)
def _no_unexpected_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVAGIX_GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(pr_summary, "collect_pr_checks", lambda *a, **k: pytest.fail("Unexpected PR collection"))
    monkeypatch.setattr(
        pr_summary, "inspect_github_junit", lambda *a, **k: pytest.fail("Unexpected artifact collection")
    )


def _collect(monkeypatch: pytest.MonkeyPatch, repo: _Repo, *, failed: bool = False) -> list[str]:
    calls: list[str] = []

    def collect(url: str, *, token: str | None = None) -> PullRequestChecks:
        assert token is None
        calls.append(url)
        return PullRequestChecks(
            {
                "schema_version": "1.0",
                "kind": "github_pr_checks",
                "repository": "owner/repo",
                "repository_id": 17,
                "pull_request": 7,
                "state": "open",
                "base_sha": repo.base,
                "head_sha": repo.head,
                "test_merge_status": "unavailable",
                "completeness": "complete",
                "policy_decision": "not_evaluated",
                "required_checks": "unknown",
                "revisions": [
                    {
                        "kind": "head",
                        "sha": repo.head,
                        "completeness": "complete",
                        "checks": [
                            {
                                "kind": "check_run",
                                "id": 31,
                                "name": "tests",
                                "producer": "Fixture App",
                                "producer_id": 9,
                                "status": "completed",
                                "conclusion": "failure" if failed else "success",
                                "result": "failed" if failed else "passed",
                                "url": None,
                            }
                        ],
                    }
                ],
            }
        )

    monkeypatch.setattr(pr_summary, "collect_pr_checks", collect)
    return calls


def _section(output: str) -> str:
    return output.split(HEADING, 1)[1].split("\n## ", 1)[0]


def _junit(root: Path, *, failed: bool = False) -> Path:
    path = root / "results.xml"
    marker = "<failure/>" if failed else ""
    path.write_text(
        f'<testsuite name="pytest" tests="1" failures="{int(failed)}" errors="0" skipped="0">'
        f'<testcase name="test_case">{marker}</testcase></testsuite>',
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize("use_expectations", [False, True])
@pytest.mark.parametrize("value,lowered", [("70", True), ("90", False), ("80", False)])
def test_changed_workflow_thresholds_are_advisory_in_both_summary_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    use_expectations: bool,
    value: str,
    lowered: bool,
) -> None:
    repo = _repository(
        tmp_path,
        {WORKFLOW: _workflow("80")},
        {WORKFLOW: _workflow(value).replace("name: CI", "name: Updated CI")},
    )
    calls = _collect(monkeypatch, repo)
    assert pr_summary.main(repo.args(expectations=use_expectations)) == 0
    captured = capsys.readouterr()
    assert captured.err == "" and calls == [PR_URL]
    section = _section(captured.out)
    assert "**Inspection:** complete" in section and "**Comparable declarations:** 1." in section
    assert repo.base in section and repo.head in section
    assert "effective coverage, execution, required checks and merge readiness are not verified" in section
    assert "Changes may be intentional" in section
    assert ("ci.coverage-threshold-lowered" in section) is lowered
    if lowered:
        assert "decreased from 80% to 70%" in section and WORKFLOW in section
    else:
        assert "No findings within the inspected scope" in section
    headings = [
        "## Evagix PR checks",
        "## Deleted-file reference review",
        "## Deleted-script instruction review",
        "## Test change review",
        HEADING,
    ]
    positions = [captured.out.index(heading) for heading in headings]
    assert positions == sorted(positions)
    assert ("Expected checks" in captured.out) is use_expectations
    if not use_expectations:
        assert "Required-check coverage is unknown" in captured.out


@pytest.mark.parametrize("use_expectations", [False, True])
@pytest.mark.parametrize("kind", ["missing-literal", "dynamic", "encoding", "malformed", "unsupported", "deleted"])
def test_incomplete_coverage_evidence_is_visible_and_not_a_clean_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    use_expectations: bool,
    kind: str,
) -> None:
    content: str | bytes = {
        "missing-literal": _workflow("80").replace(" --cov-fail-under=80", ""),
        "dynamic": _workflow("${{ env.MINIMUM }}"),
        "encoding": b"\xff",
        "malformed": _workflow("80").replace("name: Coverage", 'name: "unterminated'),
        "unsupported": "jobs: [not-a-block-workflow]\n",
        "deleted": "",
    }[kind]
    repo = _repository(tmp_path, {WORKFLOW: _workflow("80")}, {} if kind == "deleted" else {WORKFLOW: content})
    calls = _collect(monkeypatch, repo)
    assert pr_summary.main(repo.args(expectations=use_expectations)) == 1
    captured = capsys.readouterr()
    assert captured.err == "" and calls == [PR_URL]
    section = _section(captured.out)
    assert "**Inspection:** incomplete" in section and "**Comparable declarations:** 0." in section
    assert "### Inspection limits" in section and WORKFLOW in section
    assert "previous declaration has no comparable literal at head" in section
    assert "ci.coverage-threshold-lowered" not in section
    assert "## Evagix PR checks" in captured.out and "passed: 1" in captured.out
    assert "## Test change review" in captured.out


@pytest.mark.parametrize("use_expectations", [False, True])
def test_incomplete_coverage_preserves_lowered_finding_and_optional_junit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    use_expectations: bool,
) -> None:
    other = ".github/workflows/broken.yaml"
    repo = _repository(
        tmp_path,
        {WORKFLOW: _workflow("80"), other: _workflow("90")},
        {WORKFLOW: _workflow("70"), other: b"\xff"},
    )
    _collect(monkeypatch, repo)
    args = [*repo.args(expectations=use_expectations), "--junit-report", str(_junit(tmp_path, failed=True))]
    assert pr_summary.main(args) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    section = _section(captured.out)
    assert "**Inspection:** incomplete" in section and "**Comparable declarations:** 1." in section
    assert "ci.coverage-threshold-lowered" in section and "decreased from 80% to 70%" in section
    assert "### Inspection limits" in section and other in section
    junit_heading = "## Local pytest JUnit report"
    assert captured.out.index(HEADING) < captured.out.index(junit_heading)
    junit_section = captured.out.split(junit_heading, 1)[1]
    assert "**Collection:** complete; **Reported outcome:** failed." in junit_section
    assert "revision binding: `unknown`" in junit_section and "Source verification: `unverified`" in junit_section


@pytest.mark.parametrize("use_expectations", [False, True])
@pytest.mark.parametrize("failed_junit", [False, True])
def test_lowered_threshold_with_failed_github_check_and_complete_junit_remains_advisory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    use_expectations: bool,
    failed_junit: bool,
) -> None:
    repo = _repository(tmp_path, {WORKFLOW: _workflow("80")}, {WORKFLOW: _workflow("70")})
    _collect(monkeypatch, repo, failed=True)
    args = [*repo.args(expectations=use_expectations), "--junit-report", str(_junit(tmp_path, failed=failed_junit))]
    assert pr_summary.main(args) == 0
    captured = capsys.readouterr()
    assert captured.err == "" and "failed: 1" in captured.out
    section = _section(captured.out)
    assert "**Inspection:** complete" in section and "ci.coverage-threshold-lowered" in section
    assert "## Local pytest JUnit report" in captured.out
    assert "The optional local JUnit section has no verified revision binding" in captured.out


def test_coverage_uses_requested_commits_before_collection_and_excludes_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    original = _repository(tmp_path, {WORKFLOW: _workflow("80")}, {WORKFLOW: _workflow("70")})
    _git(tmp_path, "checkout", "-qb", "advanced-base", original.base)
    (tmp_path / WORKFLOW).write_text(_workflow("90"), encoding="utf-8")
    _git(tmp_path, "add", WORKFLOW)
    _git(tmp_path, "commit", "-qm", "advance base")
    repo = _Repo(tmp_path, _git(tmp_path, "rev-parse", "HEAD"), original.head)
    (tmp_path / WORKFLOW).write_text(_workflow("98"), encoding="utf-8")
    _git(tmp_path, "add", WORKFLOW)
    (tmp_path / WORKFLOW).write_text(_workflow("99"), encoding="utf-8")
    untracked = tmp_path / ".github/workflows/untracked.yml"
    untracked.write_text(_workflow("$UNTRACKED"), encoding="utf-8")
    status = _git(tmp_path, "status", "--porcelain")
    builder_calls: list[tuple[Path, str, str]] = []

    def build(root: Path, *, base: str, head: str) -> coverage_drift.CoverageDriftReport:
        builder_calls.append((root, base, head))
        return coverage_drift.build_coverage_drift_report(root, base=base, head=head)

    monkeypatch.setattr(pr_summary, "build_coverage_drift_report", build)
    calls = _collect(monkeypatch, repo)
    collect = pr_summary.collect_pr_checks

    def collect_after_inspection(url: str, *, token: str | None = None) -> PullRequestChecks:
        assert builder_calls == [(tmp_path, repo.base, repo.head)]
        return collect(url, token=token)

    monkeypatch.setattr(pr_summary, "collect_pr_checks", collect_after_inspection)
    assert pr_summary.main(repo.args()) == 0
    captured = capsys.readouterr()
    assert captured.err == "" and calls == [PR_URL]
    section = _section(captured.out)
    assert repo.base in section and repo.head in section and original.base in section
    assert "decreased from 80% to 70%" in section
    assert "untracked.yml" not in captured.out
    assert _git(tmp_path, "status", "--porcelain") == status
    assert (tmp_path / WORKFLOW).read_text(encoding="utf-8") == _workflow("99")
    assert _git(tmp_path, "show", f":{WORKFLOW}") == _workflow("98").strip()


@pytest.mark.parametrize("use_expectations", [False, True])
@pytest.mark.parametrize("error_type", [OSError, RuntimeError, ValueError])
def test_coverage_builder_failure_prevents_all_network_and_partial_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    use_expectations: bool,
    error_type: type[Exception],
) -> None:
    repo = _repository(tmp_path, {WORKFLOW: _workflow("80")}, {WORKFLOW: _workflow("70")})

    def unavailable(*args: object, **kwargs: object) -> None:
        raise error_type("private coverage inspection detail")

    monkeypatch.setattr(pr_summary, "build_coverage_drift_report", unavailable)
    args = [
        *repo.args(expectations=use_expectations),
        "--junit-archive",
        str(tmp_path / "unused.zip"),
        "--junit-run-id",
        "100",
        "--junit-attempt",
        "2",
        "--junit-artifact-id",
        "300",
    ]
    assert pr_summary.main(args) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err.startswith("ERROR:")
    assert "Unable to inspect committed inputs" in captured.err
    assert "private coverage inspection detail" not in captured.err and str(tmp_path) not in captured.err


def test_coverage_finding_paths_and_step_names_are_redacted_in_combined_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "ghp_" + "f" * 36
    path = f".github/workflows/{secret}.yml"
    repo = _repository(tmp_path, {path: _workflow("80", step=secret)}, {path: _workflow("70", step=secret)})
    _collect(monkeypatch, repo)
    assert pr_summary.main(repo.args()) == 0
    captured = capsys.readouterr()
    section = _section(captured.out)
    assert "ci.coverage-threshold-lowered" in section and "[REDACTED]" in section
    assert secret not in captured.out + captured.err


@pytest.mark.parametrize("oversized_section", ["coverage", "combined"])
def test_coverage_section_counts_toward_combined_utf8_output_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    oversized_section: str,
) -> None:
    repo = _repository(tmp_path, {WORKFLOW: _workflow("80")}, {WORKFLOW: _workflow("70")})
    _collect(monkeypatch, repo)
    other = "x" * 200_000 if oversized_section == "combined" else ""
    coverage = "é" * 475_001 if oversized_section == "coverage" else other
    for renderer in (
        "render_pr_checks_markdown",
        "render_reference_drift_markdown",
        "render_script_drift_markdown",
        "render_test_changes_markdown",
    ):
        monkeypatch.setattr(pr_summary, renderer, lambda *a, **k: other)
    monkeypatch.setattr(pr_summary, "render_coverage_drift_markdown", lambda *a, **k: coverage)
    assert pr_summary.main(repo.args()) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "Combined summary exceeds the output limit" in captured.err
