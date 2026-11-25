from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from evagix.cli import main
from evagix.commands import pr_checks
from evagix.reports import safe_markdown
from evagix.verification.github_collection import GitHubCollectionError
from evagix.verification.github_pr_checks import PullRequestChecks

PR_URL = "https://github.com/owner/repo/pull/7"


@pytest.fixture
def payload(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    checks = []
    for identifier, (result, conclusion) in enumerate(
        (("passed", "success"), ("failed", "failure"), ("pending", None), ("other", "skipped")), 1
    ):
        checks.append(
            {
                "kind": "check_run",
                "id": identifier,
                "name": f"check-{result}",
                "producer": "Check App",
                "producer_id": 9,
                "status": "in_progress" if result == "pending" else "completed",
                "conclusion": conclusion,
                "result": result,
                "url": f"https://github.com/owner/repo/actions/runs/20/job/{identifier}",
            }
        )
    data = {
        "schema_version": "1.0",
        "kind": "github_pr_checks",
        "repository": "owner/repo",
        "repository_id": 17,
        "pull_request": 7,
        "state": "open",
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "test_merge_status": "unavailable",
        "completeness": "complete",
        "policy_decision": "not_evaluated",
        "required_checks": "unknown",
        "revisions": [{"kind": "head", "sha": "b" * 40, "completeness": "complete", "checks": checks}],
    }
    monkeypatch.delenv("EVAGIX_GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(pr_checks, "collect_pr_checks", lambda *args, **kwargs: PullRequestChecks(data))
    return data


@pytest.mark.parametrize("show_all", [False, True])
def test_markdown_inventory_preserves_scope_outcomes_and_visibility(
    payload: dict[str, Any], capsys: pytest.CaptureFixture[str], show_all: bool
) -> None:
    assert main(["pr-checks", PR_URL, "--format", "markdown", *(["--all"] if show_all else [])]) == 0
    captured = capsys.readouterr()
    assert not captured.err
    assert captured.out.startswith("## Evagix PR checks\n")
    assert "Base: ` " + "a" * 40 in captured.out
    assert "head: ` " + "b" * 40 in captured.out
    assert "passed: 1; failed: 1; pending: 1; other: 1; unknown: 0" in captured.out
    assert ("check-passed" in captured.out) is show_all
    assert "**failed**" in captured.out and "**pending**" in captured.out
    assert "conclusion: ` skipped `" in captured.out
    assert "### Test-merge checks" in captured.out and "` unavailable `" in captured.out
    assert "[Details](<https://github.com/owner/repo/actions/runs/20/job/2>)" in captured.out
    assert "does not prove which code was tested or authorize merging" in captured.out


@pytest.mark.parametrize("complete", [False, True])
def test_markdown_empty_inventory_does_not_claim_tests_ran(
    payload: dict[str, Any], capsys: pytest.CaptureFixture[str], complete: bool
) -> None:
    payload["completeness"] = "complete" if complete else "incomplete"
    payload["revisions"][0].update(completeness=payload["completeness"], checks=[])
    assert main(["pr-checks", PR_URL, "--format", "markdown"]) == (0 if complete else 1)
    output = capsys.readouterr().out
    assert "No checks observed; this does not establish test execution." in output
    assert ("Incomplete collection:" in output) is not complete


@pytest.mark.parametrize("complete", [False, True])
@pytest.mark.parametrize("show_all", [False, True])
def test_markdown_expected_checks_keep_missing_and_unverified_distinct(
    tmp_path: Path,
    payload: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    complete: bool,
    show_all: bool,
) -> None:
    payload["completeness"] = "complete" if complete else "incomplete"
    payload["revisions"][0]["completeness"] = payload["completeness"]
    path = tmp_path / "checks.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "repository_id": 17,
                "checks": [
                    {"revision": "head", "kind": "check_run", "name": name, "producer_id": 9}
                    for name in ("check-passed", "check-failed", "check-pending", "check-other", "not-observed")
                ],
            }
        ),
        encoding="utf-8",
    )
    assert main(
        ["pr-checks", PR_URL, "--expectations", str(path), "--format", "markdown", *(["--all"] if show_all else [])]
    ) == (0 if complete else 1)
    output = capsys.readouterr().out
    assert "### Expected checks" in output
    assert "Authority: `caller_supplied`; policy decision: `not_evaluated`." in output
    assert "Expectations digest:" in output
    if complete:
        assert "passed: 1; failed: 1; pending: 1; missing: 1; unverified: 1" in output
        assert "**missing** — ` not-observed `" in output
        assert "**unverified** — ` check-other `" in output
        assert ("**passed** — ` check-passed `" in output) is show_all
    else:
        assert "passed: 0; failed: 0; pending: 0; missing: 0; unverified: 5" in output
        assert "**missing**" not in output


def test_markdown_contains_provider_text_as_redacted_code_literals(
    payload: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "ghp_" + "a" * 36
    name = f"اختبار ``` ![image](https://example.invalid/pixel) @reviewer\n::error::fake\u202e {secret}"
    payload["revisions"][0]["checks"][1].update(
        name=name, url="https://example.invalid/log)(![image](https://example.invalid/pixel))<img/src=x>"
    )
    assert main(["pr-checks", PR_URL, "--format", "markdown"]) == 0
    output = capsys.readouterr().out
    assert secret not in output and "[REDACTED]" in output
    assert "اختبار" in output and "\u202e" not in output
    assert "\\n::error::fake\\u202e" in output
    assert not any(line.startswith("::") for line in output.splitlines())
    assert "```` اختبار ```" in output
    assert "%28" in output and "%3Cimg" in output
    assert "<img" not in output


def test_markdown_size_failure_is_not_partial_success(
    payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(safe_markdown, "_MAX_MARKDOWN_BYTES", 80)
    assert main(["pr-checks", PR_URL, "--format", "markdown"]) == 2
    captured = capsys.readouterr()
    assert not captured.out
    assert "Markdown report exceeds" in captured.err


def test_markdown_collection_failure_has_no_report(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*args: object, **kwargs: object) -> PullRequestChecks:
        raise GitHubCollectionError("pr_changed")

    monkeypatch.setattr(pr_checks, "collect_pr_checks", fail)
    assert main(["pr-checks", PR_URL, "--format", "markdown"]) == 2
    captured = capsys.readouterr()
    assert not captured.out and "ERROR:" in captured.err
