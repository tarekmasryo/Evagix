from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from evagix import pr_summary
from evagix.verification.github_collection import GitHubCollectionError
from evagix.verification.github_pr_checks import PullRequestChecks

PR_URL = "https://github.com/owner/repo/pull/7"
EXPECTATIONS_PATH = ".github/checks.json"


def _git(root: Path, *args: str, input_text: str | None = None) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=Fixture User", "-c", "user.email=fixture@example.invalid", *args],
        cwd=root,
        input=input_text,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def _expectations(name: str = "required-tests") -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "repository_id": 17,
        "checks": [{"revision": "head", "kind": "check_run", "name": name, "producer_id": 9}],
    }


@dataclass(frozen=True)
class _Repository:
    root: Path
    base: str
    head: str

    def args(self, *, expectations: bool = True) -> list[str]:
        arguments = [
            PR_URL,
            "--repo",
            str(self.root),
            "--base",
            self.base,
            "--head",
            self.head,
        ]
        if expectations:
            arguments.extend(("--expectations", EXPECTATIONS_PATH))
        return arguments


def _repository(
    root: Path,
    *,
    expectations_bytes: bytes | None = None,
    include_expectations: bool = True,
    symlink_expectations: bool = False,
    invalid_document: bool = False,
    context_text: str = "Use the [test script](scripts/test.sh).\n",
) -> _Repository:
    _git(root, "init", "-b", "main")
    (root / ".github").mkdir()
    (root / "scripts").mkdir()
    (root / "AGENTS.md").write_text(context_text, encoding="utf-8")
    (root / "scripts/test.sh").write_text("#!/bin/sh\ntouch SHOULD_NOT_RUN\n", encoding="utf-8")
    if include_expectations:
        contents = expectations_bytes if expectations_bytes is not None else json.dumps(_expectations()).encode("utf-8")
        (root / EXPECTATIONS_PATH).write_bytes(contents)
    _git(root, "add", ".")
    if symlink_expectations:
        oid = _git(root, "hash-object", "-w", "--stdin", input_text="outside.json")
        _git(root, "update-index", "--cacheinfo", "120000", oid, EXPECTATIONS_PATH)
    _git(root, "commit", "--no-gpg-sign", "-m", "initial")
    base = _git(root, "rev-parse", "HEAD")
    (root / "scripts/test.sh").unlink()
    (root / EXPECTATIONS_PATH).write_text(json.dumps(_expectations("head-only-check")), encoding="utf-8")
    if invalid_document:
        (root / "AGENTS.md").write_bytes(b"\xff")
    _git(root, "add", ".")
    _git(root, "commit", "--no-gpg-sign", "-m", "remove script and edit expectations")
    return _Repository(root, base, _git(root, "rev-parse", "HEAD"))


def _payload(repo: _Repository, *, result: str | None = None, complete: bool = True) -> dict[str, Any]:
    checks = []
    if result is not None:
        checks.append(
            {
                "kind": "check_run",
                "id": 31,
                "name": "required-tests",
                "producer": "Fixture App",
                "producer_id": 9,
                "status": "in_progress" if result == "pending" else "completed",
                "conclusion": {"passed": "success", "failed": "failure", "pending": None, "other": "skipped"}[result],
                "result": result,
                "url": None,
            }
        )
    completeness = "complete" if complete else "incomplete"
    return {
        "schema_version": "1.0",
        "kind": "github_pr_checks",
        "repository": "owner/repo",
        "repository_id": 17,
        "pull_request": 7,
        "state": "open",
        "base_sha": repo.base,
        "head_sha": repo.head,
        "test_merge_status": "unavailable",
        "completeness": completeness,
        "policy_decision": "not_evaluated",
        "required_checks": "unknown",
        "revisions": [{"kind": "head", "sha": repo.head, "completeness": completeness, "checks": checks}],
    }


@pytest.fixture(autouse=True)
def no_unexpected_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVAGIX_GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(pr_summary, "collect_pr_checks", lambda *a, **k: pytest.fail("Unexpected collection"))


def _junit_xml(*, marker: str = "", tests: int = 1, failures: int = 0, errors: int = 0, skipped: int = 0) -> str:
    case = f'<testcase name="test_case" classname="suite.module">{marker}</testcase>' if tests else ""
    return (
        f'<testsuite name="pytest" tests="{tests}" failures="{failures}" errors="{errors}" skipped="{skipped}">'
        + case
        + "</testsuite>"
    )


@pytest.mark.parametrize("use_expectations", [True, False])
@pytest.mark.parametrize(
    "xml,outcome,status",
    [
        (_junit_xml(), "passed", 0),
        (_junit_xml(marker="<failure>private failure body</failure>", failures=1), "failed", 0),
        (_junit_xml(marker="<error/><error/>", errors=2), "failed", 0),
        (_junit_xml(marker="<skipped/>", skipped=1), "skipped_only", 0),
        (_junit_xml(tests=0), "empty", 0),
        (_junit_xml(tests=2), "unknown", 1),
        (_junit_xml(marker="<failure/>", failures=2), "failed", 1),
        (_junit_xml().replace(' tests="1"', ""), "unknown", 1),
        (_junit_xml().replace("</testsuite>", "<other>"), "unknown", 1),
        ("<testsuite>unsupported body", "unknown", 1),
    ],
    ids=[
        "pass",
        "failure",
        "errors",
        "skipped",
        "empty",
        "count-mismatch",
        "incomplete-failure",
        "missing-counts",
        "unsupported-before-malformed-tail",
        "unsupported-body",
    ],
)
def test_optional_junit_outcomes_and_collection_remain_separate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    use_expectations: bool,
    xml: str,
    outcome: str,
    status: int,
) -> None:
    repo = _repository(tmp_path)
    report = tmp_path / "local report.xml"
    report.write_text(xml, encoding="utf-8")
    calls: list[str] = []

    def collect(url: str, **kwargs: object) -> PullRequestChecks:
        calls.append(url)
        return PullRequestChecks(_payload(repo, result="failed"))

    monkeypatch.setattr(pr_summary, "collect_pr_checks", collect)
    before = _git(tmp_path, "status", "--porcelain")
    assert pr_summary.main([*repo.args(expectations=use_expectations), "--junit-report", str(report)]) == status
    captured = capsys.readouterr()
    assert captured.err == "" and calls == [PR_URL]
    assert "## Local pytest JUnit report" in captured.out
    assert f"**Reported outcome:** {outcome}" in captured.out
    assert "Source verification: `unverified`" in captured.out
    assert "revision binding: `unknown`" in captured.out and "run completion: `unknown`" in captured.out
    assert "not associated with a GitHub job or the requested commits" in captured.out
    assert "All sections use the requested base and head commits" not in captured.out
    assert "Deleted-file reference review" in captured.out and "Deleted-script instruction review" in captured.out
    assert "required-tests" in captured.out and "failed: 1" in captured.out
    assert "private failure body" not in captured.out and str(report) not in captured.out
    assert ("**Collection:** incomplete" in captured.out) == (status == 1)
    assert _git(tmp_path, "status", "--porcelain") == before
    assert not (tmp_path / "SHOULD_NOT_RUN").exists()


@pytest.mark.parametrize("use_expectations", [True, False])
def test_without_junit_preserves_summary_and_never_reads_a_local_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], use_expectations: bool
) -> None:
    repo = _repository(tmp_path)
    monkeypatch.setattr(pr_summary, "collect_pr_checks", lambda *a, **k: PullRequestChecks(_payload(repo)))
    assert pr_summary.main(repo.args(expectations=use_expectations)) == 0
    previous = capsys.readouterr()
    (tmp_path / "junit.xml").write_text("invalid XML must not be discovered", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        pr_summary, "read_junit_report", lambda *a, **k: pytest.fail("Unexpected local report read"), raising=False
    )
    assert pr_summary.main(repo.args(expectations=use_expectations)) == 0
    captured = capsys.readouterr()
    assert captured == previous
    assert "All sections use the requested base and head commits" in captured.out
    assert "JUnit" not in captured.out


@pytest.mark.parametrize("checks_complete,invalid_document", [(False, False), (True, True)])
def test_complete_junit_cannot_override_existing_incomplete_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    checks_complete: bool,
    invalid_document: bool,
) -> None:
    repo = _repository(tmp_path, invalid_document=invalid_document)
    report = tmp_path / "passed.xml"
    report.write_text(_junit_xml(), encoding="utf-8")
    monkeypatch.setattr(
        pr_summary, "collect_pr_checks", lambda *a, **k: PullRequestChecks(_payload(repo, complete=checks_complete))
    )
    assert pr_summary.main([*repo.args(), "--junit-report", str(report)]) == 1
    captured = capsys.readouterr()
    assert captured.err == "" and "**Reported outcome:** passed" in captured.out
    assert "Deleted-file reference review" in captured.out and "incomplete" in captured.out


@pytest.mark.parametrize("kind", ["malformed", "unsafe", "missing", "directory"])
def test_invalid_optional_junit_fails_before_network_without_partial_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str
) -> None:
    repo = _repository(tmp_path)
    report = tmp_path / "private-report-path.xml"
    if kind == "malformed":
        report.write_text(_junit_xml().replace("</testsuite>", ""), encoding="utf-8")
    elif kind == "unsafe":
        report.write_text('<!DOCTYPE testsuite SYSTEM "file:///private-fixture">' + _junit_xml(), encoding="utf-8")
    elif kind == "directory":
        report.mkdir()
    assert pr_summary.main([*repo.args(), "--junit-report", str(report)]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "local JUnit report" in captured.err
    assert "private" not in captured.err and str(tmp_path) not in captured.err


@pytest.mark.parametrize("arguments", [["--junit-report"], ["--junit-report", "one.xml", "--junit-report", "two.xml"]])
def test_optional_junit_requires_exactly_one_explicit_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], arguments: list[str]
) -> None:
    repo = _repository(tmp_path)
    assert pr_summary.main([*repo.args(), *arguments]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err.startswith("ERROR:")
    assert "one.xml" not in captured.err and "two.xml" not in captured.err


def test_relative_junit_path_uses_caller_directory_without_rebinding_its_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    repo = _repository(root)
    (root / "report.xml").write_text("invalid repository-controlled report", encoding="utf-8")
    (tmp_path / "report.xml").write_text(
        _junit_xml().replace(
            "<testcase", f'<properties><property name="commit" value="{repo.head}"/></properties><testcase'
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pr_summary, "collect_pr_checks", lambda *a, **k: PullRequestChecks(_payload(repo)))
    assert pr_summary.main([*repo.args(), "--junit-report", "report.xml"]) == 0
    captured = capsys.readouterr()
    junit_section = captured.out.split("## Local pytest JUnit report", 1)[1]
    assert "**Reported outcome:** passed" in junit_section
    assert "revision binding: `unknown`" in junit_section
    assert repo.head not in junit_section


def test_junit_section_preserves_existing_check_and_repository_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repository(tmp_path)
    monkeypatch.setattr(
        pr_summary, "collect_pr_checks", lambda *a, **k: PullRequestChecks(_payload(repo, result="failed"))
    )
    assert pr_summary.main(repo.args()) == 0
    original = capsys.readouterr().out
    report = tmp_path / "report.xml"
    report.write_text(_junit_xml(), encoding="utf-8")
    assert pr_summary.main([*repo.args(), "--junit-report", str(report)]) == 0
    existing_sections = capsys.readouterr().out.split("## Local pytest JUnit report", 1)[0]
    existing_sections = existing_sections.replace(
        "GitHub checks and repository sections use the requested base and head commits. "
        "The optional local JUnit section has no verified revision binding. ",
        "All sections use the requested base and head commits. ",
        1,
    )
    assert existing_sections.rstrip() == original.rstrip()


@pytest.mark.parametrize("limit", ["junit_section", "combined_bytes"])
def test_optional_junit_output_limits_reject_without_partial_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], limit: str
) -> None:
    repo = _repository(tmp_path)
    report = tmp_path / "report.xml"
    if limit == "junit_section":
        cases = f'<testcase name="{"x" * 2048}"><failure/></testcase>' * 300
        xml = '<testsuite name="large" tests="300" failures="300" errors="0" skipped="0">' + cases + "</testsuite>"
    else:
        xml = _junit_xml()
        for renderer in (
            "render_pr_checks_markdown",
            "render_reference_drift_markdown",
            "render_script_drift_markdown",
            "render_junit_report_markdown",
        ):
            monkeypatch.setattr(pr_summary, renderer, lambda *a, **k: "é" * 120_000)
    report.write_text(xml, encoding="utf-8")
    monkeypatch.setattr(pr_summary, "collect_pr_checks", lambda *a, **k: PullRequestChecks(_payload(repo)))
    assert pr_summary.main([*repo.args(), "--junit-report", str(report)]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err.startswith("ERROR:")
    assert (
        "Combined summary exceeds" in captured.err if limit == "combined_bytes" else "bounded Markdown" in captured.err
    )


def test_untrusted_junit_labels_are_redacted_literal_and_do_not_leak_bodies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repository(tmp_path)
    secret = "ghp_" + "a" * 36
    name = f'```&#10;## forged-heading&#10;&lt;img src="fixture"&gt;\u202e token={secret}'
    # Attribute quotes are XML-escaped; newlines are character references so the parser preserves them.
    name = name.replace('"', "&quot;")
    xml = _junit_xml(marker='<failure message="private-message">private-traceback</failure>', failures=1)
    xml = xml.replace('name="test_case"', f'name="{name}" file="private-source"')
    xml = xml.replace("</testsuite>", "<system-out>private-logs</system-out></testsuite>")
    report = tmp_path / "report.xml"
    report.write_text(xml, encoding="utf-8")
    monkeypatch.setattr(pr_summary, "collect_pr_checks", lambda *a, **k: PullRequestChecks(_payload(repo)))
    assert pr_summary.main([*repo.args(), "--junit-report", str(report)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert secret not in captured.out and "[REDACTED" in captured.out
    assert "\n## forged-heading" not in captured.out and "\\n## forged-heading" in captured.out
    assert "\u202e" not in captured.out and r"\u202e" in captured.out
    assert all(
        value not in captured.out
        for value in ("private-message", "private-traceback", "private-source", "private-logs")
    )


def test_summary_uses_base_expectations_and_one_collection_without_worktree_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repository(tmp_path)
    (tmp_path / EXPECTATIONS_PATH).write_text("invalid working-tree JSON", encoding="utf-8")
    (tmp_path / ".env").write_text("API_KEY=private-fixture-value", encoding="utf-8")
    (tmp_path / "evagix.py").write_text("raise RuntimeError('must not execute repository code')", encoding="utf-8")
    calls: list[tuple[str, str | None]] = []

    def collect(url: str, *, token: str | None = None) -> PullRequestChecks:
        calls.append((url, token))
        return PullRequestChecks(_payload(repo))

    monkeypatch.setattr(pr_summary, "collect_pr_checks", collect)
    monkeypatch.chdir(tmp_path)
    before = _git(tmp_path, "status", "--porcelain")
    assert pr_summary.main(repo.args()) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert calls == [(PR_URL, None)]
    assert "required-tests" in captured.out and "**missing**" in captured.out
    assert "head-only-check" not in captured.out
    assert "scripts/test.sh" in captured.out and "AGENTS.md:1:23" in captured.out
    assert repo.base in captured.out and repo.head in captured.out
    assert "private-fixture-value" not in captured.out
    assert "base commit" in captured.out and "does not authenticate" in captured.out
    assert not (tmp_path / "SHOULD_NOT_RUN").exists()
    assert _git(tmp_path, "status", "--porcelain") == before


@pytest.mark.parametrize("contents", [None, b"{"], ids=["absent", "malformed"])
def test_inventory_mode_does_not_read_or_infer_expectations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], contents: bytes | None
) -> None:
    repo = _repository(tmp_path, include_expectations=contents is not None, expectations_bytes=contents)
    (tmp_path / ".github/evagix-checks.json").write_text("invalid unselected configuration", encoding="utf-8")
    calls: list[str] = []

    def collect(url: str, *, token: str | None = None) -> PullRequestChecks:
        calls.append(url)
        return PullRequestChecks(_payload(repo))

    monkeypatch.setattr(pr_summary, "collect_pr_checks", collect)
    before = _git(tmp_path, "status", "--porcelain")
    assert pr_summary.main(repo.args(expectations=False)) == 0
    captured = capsys.readouterr()
    assert captured.err == "" and calls == [PR_URL]
    assert "No expectations supplied" in captured.out
    assert "Required-check coverage is unknown" in captured.out
    assert "merge readiness is not evaluated" in captured.out
    assert "No checks observed; this does not establish test execution" in captured.out
    assert "Expected checks" not in captured.out and "missing:" not in captured.out
    assert "scripts/test.sh" in captured.out and "AGENTS.md:1:23" in captured.out
    assert _git(tmp_path, "status", "--porcelain") == before
    assert not (tmp_path / "SHOULD_NOT_RUN").exists()


def test_inventory_summary_reports_deleted_link_in_unchanged_list_paragraph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repository(tmp_path, context_text="*   Verify changes with\n    [test script](scripts/test.sh).\n")
    monkeypatch.setattr(pr_summary, "collect_pr_checks", lambda *a, **k: PullRequestChecks(_payload(repo)))
    assert _git(tmp_path, "diff", repo.base, repo.head, "--", "AGENTS.md") == ""
    assert pr_summary.main(repo.args(expectations=False)) == 0
    captured = capsys.readouterr()
    assert captured.err == "" and "**Findings:** 1" in captured.out
    assert "AGENTS.md:2:19" in captured.out and "scripts/test.sh" in captured.out
    assert "does not decide merge readiness" in captured.out


@pytest.mark.parametrize("use_expectations", [True, False])
@pytest.mark.parametrize("result", ["passed", "failed", "pending", "other"])
def test_complete_provider_outcomes_remain_advisory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    result: str,
    use_expectations: bool,
) -> None:
    repo = _repository(tmp_path)
    monkeypatch.setattr(
        pr_summary, "collect_pr_checks", lambda *a, **k: PullRequestChecks(_payload(repo, result=result))
    )
    assert pr_summary.main(repo.args(expectations=use_expectations)) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    outcome = "unverified" if result == "other" and use_expectations else result
    assert f"{outcome}: 1" in captured.out
    if use_expectations:
        assert "not_evaluated" in captured.out and "Expected checks" in captured.out
    else:
        assert "Required-check coverage is unknown" in captured.out and "Head checks" in captured.out
        assert "Expected checks" not in captured.out


@pytest.mark.parametrize("use_expectations", [True, False])
@pytest.mark.parametrize("checks_complete,invalid_document", [(False, False), (True, True), (False, True)])
def test_incomplete_part_is_visible_and_has_distinct_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    checks_complete: bool,
    invalid_document: bool,
    use_expectations: bool,
) -> None:
    repo = _repository(tmp_path, invalid_document=invalid_document)
    payload = _payload(repo, complete=checks_complete)
    monkeypatch.setattr(pr_summary, "collect_pr_checks", lambda *a, **k: PullRequestChecks(payload))
    assert pr_summary.main(repo.args(expectations=use_expectations)) == 1
    captured = capsys.readouterr()
    assert captured.err == "" and "incomplete" in captured.out
    assert "Deleted-file reference review" in captured.out
    assert "Deleted-script instruction review" in captured.out
    assert ("Expected checks" if use_expectations else "Head checks") in captured.out
    if not checks_complete and use_expectations:
        assert "unverified: 1" in captured.out and "missing: 0" in captured.out
    if not checks_complete and not use_expectations:
        assert "Incomplete collection: do not infer missing checks or a clean result" in captured.out


@pytest.mark.parametrize("use_expectations", [True, False])
@pytest.mark.parametrize("field", ["base_sha", "head_sha"])
def test_changed_pr_revision_publishes_no_combined_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    field: str,
    use_expectations: bool,
) -> None:
    repo = _repository(tmp_path)
    payload = _payload(repo)
    payload[field] = "c" * 40
    monkeypatch.setattr(pr_summary, "collect_pr_checks", lambda *a, **k: PullRequestChecks(payload))
    assert pr_summary.main(repo.args(expectations=use_expectations)) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "no longer matches" in captured.err


@pytest.mark.parametrize("use_expectations", [True, False])
@pytest.mark.parametrize("code", ["forbidden", "pr_changed", "transport_error"])
def test_collection_error_does_not_become_missing_checks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    code: str,
    use_expectations: bool,
) -> None:
    repo = _repository(tmp_path)

    def fail(*args: object, **kwargs: object) -> PullRequestChecks:
        raise GitHubCollectionError(code)

    monkeypatch.setattr(pr_summary, "collect_pr_checks", fail)
    assert pr_summary.main(repo.args(expectations=use_expectations)) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and f"({code})" in captured.err


@pytest.mark.parametrize(
    "contents",
    [b"\xff", b"{", b'{"schema_version":"1.0","schema_version":"1.0"}', b"x" * 65_537],
    ids=["non-utf8", "malformed-json", "duplicate-key", "oversized"],
)
def test_invalid_base_expectations_fail_before_collection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], contents: bytes
) -> None:
    repo = _repository(tmp_path, expectations_bytes=contents)
    assert pr_summary.main(repo.args()) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "committed inputs" in captured.err


@pytest.mark.parametrize("symlink", [False, True])
def test_missing_or_nonregular_base_file_does_not_use_head_or_worktree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], symlink: bool
) -> None:
    repo = _repository(tmp_path, include_expectations=symlink, symlink_expectations=symlink)
    assert pr_summary.main(repo.args()) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "regular tracked file" in captured.err


def test_explicit_expectations_flag_without_path_does_not_select_inventory_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _Repository(tmp_path, "a" * 40, "b" * 40)
    assert pr_summary.main(repo.args(expectations=False) + ["--expectations"]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "Invalid summary arguments" in captured.err


def test_inventory_mode_requires_available_git_history(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _Repository(tmp_path, "a" * 40, "b" * 40)
    assert pr_summary.main(repo.args(expectations=False)) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "check local history and repository data" in captured.err
    assert "expectations" not in captured.err and str(tmp_path) not in captured.err


@pytest.mark.parametrize(
    "path", ["../checks.json", "/checks.json", "C:/checks.json", "a\\checks.json", "a/./b", "a//b"]
)
def test_noncanonical_expectations_paths_are_rejected_without_disclosing_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], path: str
) -> None:
    repo = _Repository(tmp_path, "a" * 40, "b" * 40)
    args = repo.args()
    args[-1] = path
    assert pr_summary.main(args) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "ERROR: Invalid summary arguments; use --help for usage.\n"


@pytest.mark.parametrize("revision", ["main", "abc123", "a" * 39, "B" * 40, "HEAD~1"])
def test_mutable_or_abbreviated_revisions_fail_before_git_and_network(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], revision: str
) -> None:
    repo = _Repository(tmp_path, revision, "b" * 40)
    assert pr_summary.main(repo.args()) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "Invalid summary arguments" in captured.err


def test_annotated_tag_object_is_not_accepted_as_a_commit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repository(tmp_path)
    _git(tmp_path, "tag", "-a", "alias", "-m", "fixture")
    tag = _git(tmp_path, "rev-parse", "alias")
    args = _Repository(tmp_path, tag, repo.head).args()
    assert pr_summary.main(args) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "identify commits directly" in captured.err


def test_repository_identity_mismatch_does_not_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repository(tmp_path)
    payload = _payload(repo)
    payload["repository_id"] = 18
    monkeypatch.setattr(pr_summary, "collect_pr_checks", lambda *a, **k: PullRequestChecks(payload))
    assert pr_summary.main(repo.args()) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "compare expectations" in captured.err


def test_raw_check_names_are_compared_before_redaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    expected_name, observed_name = "ghp_" + "a" * 36, "ghp_" + "b" * 36
    repo = _repository(tmp_path, expectations_bytes=json.dumps(_expectations(expected_name)).encode())
    payload = _payload(repo, result="passed")
    payload["revisions"][0]["checks"][0]["name"] = observed_name
    monkeypatch.setattr(pr_summary, "collect_pr_checks", lambda *a, **k: PullRequestChecks(payload))
    assert pr_summary.main(repo.args()) == 0
    captured = capsys.readouterr()
    assert "missing: 1" in captured.out and "passed: 0" in captured.out
    assert expected_name not in captured.out and observed_name not in captured.out


@pytest.mark.parametrize("use_expectations", [True, False])
def test_only_explicit_provider_token_is_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], use_expectations: bool
) -> None:
    repo = _repository(tmp_path)
    token = "ghp_" + "c" * 36
    monkeypatch.setenv("EVAGIX_GITHUB_TOKEN", token)
    monkeypatch.setenv("GITHUB_TOKEN", "unrelated-fixture-token")

    def collect(url: str, *, token: str | None = None) -> PullRequestChecks:
        assert token == "ghp_" + "c" * 36
        return PullRequestChecks(_payload(repo))

    monkeypatch.setattr(pr_summary, "collect_pr_checks", collect)
    assert pr_summary.main(repo.args(expectations=use_expectations)) == 0
    captured = capsys.readouterr()
    assert token not in captured.out + captured.err


@pytest.mark.parametrize("use_expectations", [True, False])
@pytest.mark.parametrize(
    "renderer", ["render_reference_drift_markdown", "render_script_drift_markdown", "render_test_changes_markdown"]
)
def test_rendering_failure_emits_no_partial_report_or_exception_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    use_expectations: bool,
    renderer: str,
) -> None:
    repo = _repository(tmp_path)
    monkeypatch.setattr(pr_summary, "collect_pr_checks", lambda *a, **k: PullRequestChecks(_payload(repo)))

    def fail(*args: object, **kwargs: object) -> str:
        raise ValueError("private rendering detail")

    monkeypatch.setattr(pr_summary, renderer, fail)
    assert pr_summary.main(repo.args(expectations=use_expectations)) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "private rendering detail" not in captured.err


@pytest.mark.parametrize("use_expectations", [True, False])
@pytest.mark.parametrize("oversized_section", ["checks", "scripts", "tests", "combined"])
def test_combined_size_limit_is_checked_in_bytes_before_any_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    use_expectations: bool,
    oversized_section: str,
) -> None:
    repo = _repository(tmp_path)
    monkeypatch.setattr(pr_summary, "collect_pr_checks", lambda *a, **k: PullRequestChecks(_payload(repo)))
    combined = "é" * 170_000 if oversized_section == "combined" else ""
    checks = "é" * 475_001 if oversized_section == "checks" else combined
    scripts = "é" * 475_001 if oversized_section == "scripts" else combined
    tests = "é" * 475_001 if oversized_section == "tests" else combined
    monkeypatch.setattr(pr_summary, "render_pr_checks_markdown", lambda *a, **k: checks)
    monkeypatch.setattr(pr_summary, "render_reference_drift_markdown", lambda *a, **k: combined)
    monkeypatch.setattr(pr_summary, "render_script_drift_markdown", lambda *a, **k: scripts)
    monkeypatch.setattr(pr_summary, "render_test_changes_markdown", lambda *a, **k: tests)
    assert pr_summary.main(repo.args(expectations=use_expectations)) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "Combined summary exceeds" in captured.err


@pytest.mark.parametrize("use_expectations", [True, False])
def test_final_redaction_precedes_the_combined_size_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], use_expectations: bool
) -> None:
    repo = _repository(tmp_path)
    secret = "ghp_" + "d" * 600
    monkeypatch.setattr(pr_summary, "collect_pr_checks", lambda *a, **k: PullRequestChecks(_payload(repo)))
    monkeypatch.setattr(pr_summary, "render_pr_checks_markdown", lambda *a, **k: secret)
    monkeypatch.setattr(pr_summary, "render_reference_drift_markdown", lambda *a, **k: "")
    monkeypatch.setattr(pr_summary, "render_script_drift_markdown", lambda *a, **k: "")
    monkeypatch.setattr(pr_summary, "render_test_changes_markdown", lambda *a, **k: "")
    monkeypatch.setattr(pr_summary, "_SUMMARY_BYTES", 400)
    assert pr_summary.main(repo.args(expectations=use_expectations)) == 0
    captured = capsys.readouterr()
    assert secret not in captured.out and "[REDACTED]" in captured.out


def test_unknown_arguments_do_not_echo_private_values(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _Repository(tmp_path, "a" * 40, "b" * 40)
    assert pr_summary.main(repo.args() + ["--unexpected-private-value"]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "unexpected-private-value" not in captured.err


def _script_repository(
    root: Path, change: str, *, document: str = "AGENTS.md", script_name: str = "test.sh"
) -> _Repository:
    _git(root, "init", "-b", "main")
    (root / ".github").mkdir()
    (root / "scripts").mkdir()
    target = f"scripts/{script_name}"
    instruction = f"Use the [test script]({target}).\n\nRun `sh {target}`.\n"
    (root / document).write_text(instruction, encoding="utf-8")
    (root / target).write_text("#!/bin/sh\ntouch SHOULD_NOT_RUN\n", encoding="utf-8")
    (root / EXPECTATIONS_PATH).write_text(json.dumps(_expectations()), encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "--no-gpg-sign", "-m", "document script")
    base = _git(root, "rev-parse", "HEAD")
    if change == "retained":
        (root / "unrelated.txt").write_text("unrelated change\n", encoding="utf-8")
    elif change in {"renamed", "corrected"}:
        (root / target).rename(root / "scripts/check.sh")
        if change == "corrected":
            (root / document).write_text(instruction.replace(target, "scripts/check.sh"), encoding="utf-8")
    elif change in {"deleted", "blocked"}:
        (root / target).unlink()
        if change == "blocked":
            (root / "scripts").rmdir()
            (root / "scripts").write_text("no longer a directory\n", encoding="utf-8")
    else:
        raise ValueError("Unknown fixture change")
    _git(root, "add", ".")
    _git(root, "commit", "--no-gpg-sign", "-m", "change script")
    return _Repository(root, base, _git(root, "rev-parse", "HEAD"))


@pytest.mark.parametrize("use_expectations", [True, False])
@pytest.mark.parametrize(
    "change,document,findings",
    [
        ("retained", "README.md", 0),
        ("deleted", "AGENTS.md", 1),
        ("renamed", "README.md", 1),
        ("corrected", "AGENTS.md", 0),
    ],
)
def test_summary_includes_committed_script_instructions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    use_expectations: bool,
    change: str,
    document: str,
    findings: int,
) -> None:
    repo = _script_repository(tmp_path, change, document=document)
    calls: list[str] = []

    def collect(url: str, *, token: str | None = None) -> PullRequestChecks:
        calls.append(url)
        return PullRequestChecks(_payload(repo, result="passed"))

    monkeypatch.setattr(pr_summary, "collect_pr_checks", collect)
    (tmp_path / document).write_text("Uncommitted replacement instructions.\n", encoding="utf-8")
    before = _git(tmp_path, "status", "--porcelain")
    assert pr_summary.main(repo.args(expectations=use_expectations)) == 0
    captured = capsys.readouterr()
    assert captured.err == "" and calls == [PR_URL]
    references, scripts = captured.out.split("## Deleted-script instruction review\n", 1)
    assert "Deleted-file reference review" in references
    assert f"**Findings:** {findings}." in references and f"**Findings:** {findings}." in scripts
    assert "**Inspection:** complete" in scripts
    assert repo.base in scripts and repo.head in scripts
    assert "repository-root working directory assumed" in scripts
    assert "does not prove execution failure, select a replacement, or decide merge readiness" in scripts
    if findings:
        assert f"{document}:3:9" in scripts and "scripts/test.sh" in scripts
        assert "scripts/check.sh" not in scripts
    else:
        assert "No deleted-script references found within the inspected scope" in scripts
    assert _git(tmp_path, "status", "--porcelain") == before
    assert not (tmp_path / "SHOULD_NOT_RUN").exists()


@pytest.mark.parametrize("use_expectations", [True, False])
def test_script_only_incompleteness_preserves_other_sections_and_returns_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    use_expectations: bool,
) -> None:
    repo = _script_repository(tmp_path, "blocked")
    monkeypatch.setattr(
        pr_summary, "collect_pr_checks", lambda *a, **k: PullRequestChecks(_payload(repo, result="passed"))
    )
    assert pr_summary.main(repo.args(expectations=use_expectations)) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    references, scripts = captured.out.split("## Deleted-script instruction review\n", 1)
    assert "**Inspection:** complete" in references and "passed: 1" in references
    assert "**Inspection:** incomplete" in scripts
    assert "below non-directory Git entries" in scripts
    assert "Complete the missing inspection before relying on this report" in scripts


def test_summary_redacts_removed_script_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "ghp_" + "f" * 36
    repo = _script_repository(tmp_path, "deleted", script_name=f"{secret}.sh")
    monkeypatch.setattr(pr_summary, "collect_pr_checks", lambda *a, **k: PullRequestChecks(_payload(repo)))
    assert pr_summary.main(repo.args(expectations=False)) == 0
    captured = capsys.readouterr()
    scripts = captured.out.split("## Deleted-script instruction review\n", 1)[1]
    assert "**Findings:** 1" in scripts and "[REDACTED]" in scripts
    assert secret not in captured.out + captured.err
