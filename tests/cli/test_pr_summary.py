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
) -> _Repository:
    _git(root, "init", "-b", "main")
    (root / ".github").mkdir()
    (root / "scripts").mkdir()
    (root / "AGENTS.md").write_text("Use the [test script](scripts/test.sh).\n", encoding="utf-8")
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
def test_rendering_failure_emits_no_partial_report_or_exception_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], use_expectations: bool
) -> None:
    repo = _repository(tmp_path)
    monkeypatch.setattr(pr_summary, "collect_pr_checks", lambda *a, **k: PullRequestChecks(_payload(repo)))

    def fail(*args: object, **kwargs: object) -> str:
        raise ValueError("private rendering detail")

    monkeypatch.setattr(pr_summary, "render_reference_drift_markdown", fail)
    assert pr_summary.main(repo.args(expectations=use_expectations)) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "private rendering detail" not in captured.err


@pytest.mark.parametrize("use_expectations", [True, False])
def test_combined_size_limit_is_checked_in_bytes_before_any_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], use_expectations: bool
) -> None:
    repo = _repository(tmp_path)
    monkeypatch.setattr(pr_summary, "collect_pr_checks", lambda *a, **k: PullRequestChecks(_payload(repo)))
    monkeypatch.setattr(pr_summary, "render_pr_checks_markdown", lambda *a, **k: "é" * 475_001)
    monkeypatch.setattr(pr_summary, "render_reference_drift_markdown", lambda *a, **k: "")
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
    monkeypatch.setattr(pr_summary, "_SUMMARY_BYTES", 400)
    assert pr_summary.main(repo.args(expectations=use_expectations)) == 0
    captured = capsys.readouterr()
    assert secret not in captured.out and "[REDACTED]" in captured.out


def test_unknown_arguments_do_not_echo_private_values(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _Repository(tmp_path, "a" * 40, "b" * 40)
    assert pr_summary.main(repo.args() + ["--unexpected-private-value"]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "unexpected-private-value" not in captured.err
