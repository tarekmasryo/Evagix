from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from evagix.cli import main
from evagix.commands import common, pr_checks
from evagix.verification.github_collection import GitHubCollectionError
from evagix.verification.github_pr_checks import PullRequestChecks

PR_URL = "https://github.com/owner/repo/pull/7"


def _check(identifier: int, result: str, name: str) -> dict[str, Any]:
    status, conclusion = {
        "passed": ("completed", "success"),
        "failed": ("completed", "failure"),
        "pending": ("in_progress", None),
        "other": ("completed", "skipped"),
        "unknown": ("completed", "future_conclusion"),
    }[result]
    return {
        "kind": "check_run",
        "id": identifier,
        "name": name,
        "producer": "GitHub Actions",
        "producer_id": 9,
        "status": status,
        "conclusion": conclusion,
        "result": result,
        "url": f"https://github.com/owner/repo/actions/runs/20/job/{identifier}",
    }


@pytest.fixture
def report_payload() -> dict[str, Any]:
    status = _check(12, "failed", "merge-status-failed")
    status.update(kind="commit_status", producer=None, producer_id=None, status="failure", conclusion=None)
    return {
        "schema_version": "1.0",
        "kind": "github_pr_checks",
        "repository": "owner/repo",
        "repository_id": 17,
        "pull_request": 7,
        "state": "open",
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "test_merge_status": "available",
        "completeness": "complete",
        "policy_decision": "not_evaluated",
        "required_checks": "unknown",
        "revisions": [
            {
                "kind": "head",
                "sha": "b" * 40,
                "completeness": "complete",
                "checks": [
                    _check(index, result, f"head-{result}")
                    for index, result in enumerate(("passed", "failed", "pending", "other", "unknown"), 1)
                ],
            },
            {
                "kind": "test_merge",
                "sha": "c" * 40,
                "completeness": "complete",
                "checks": [_check(11, "passed", "merge-passed"), status],
            },
        ],
    }


@pytest.fixture
def schema_validator() -> Draft202012Validator:
    payload = json.loads(files("evagix.schemas").joinpath("github-pr-checks.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(payload)
    return Draft202012Validator(payload)


@pytest.fixture(autouse=True)
def no_implicit_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVAGIX_GITHUB_TOKEN", raising=False)

    def unexpected_collection(*args: object, **kwargs: object) -> PullRequestChecks:
        pytest.fail("Unexpected PR collection")

    monkeypatch.setattr(pr_checks, "collect_pr_checks", unexpected_collection)


@pytest.mark.parametrize("show_all", [False, True])
def test_text_separates_revisions_counts_all_results_and_filters_passed_rows(
    report_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    show_all: bool,
) -> None:
    monkeypatch.setattr(pr_checks, "collect_pr_checks", lambda *args, **kwargs: PullRequestChecks(report_payload))

    assert main(["pr-checks", PR_URL, *(["--all"] if show_all else [])]) == 0

    output = capsys.readouterr()
    assert output.err == ""
    assert output.out.startswith("GitHub-reported pull request checks\n")
    head, merge = output.out.split("\ntest_merge\n")
    assert "\nhead\n" in head
    assert "Observed: passed=1, failed=1, pending=1, other outcomes=1, unknown=1" in head
    assert "Observed: passed=1, failed=1, pending=0, other outcomes=0, unknown=0" in merge
    for result in ("failed", "pending", "other", "unknown"):
        label = "other outcomes" if result == "other" else result
        assert f"[{label}] head-{result}" in head
    assert "[failed] merge-status-failed (commit_status; producer: unknown; status: failure; conclusion: none)" in merge
    assert "producer: GitHub Actions" in head
    assert "https://github.com/owner/repo/actions/runs/20/job/2" in head
    assert ("head-passed" in head) == show_all
    assert ("merge-passed" in merge) == show_all
    assert "Required-check coverage is not assessed; this report does not decide merge readiness." in output.out
    assert "not_evaluated" not in output.out
    assert "GitHub-reported metadata only." in output.out
    assert "PASS" not in output.out
    assert "merge-ready" not in output.out


@pytest.mark.parametrize(
    "results,complete,next_action",
    [
        (["failed", "pending"], True, "Inspect failed checks using their detail links or the PR checks page."),
        (["pending", "other"], True, "Wait for pending checks, or review approvals on the PR."),
        (["other"], True, "Inspect workflow/provider outcomes on the PR; execution is not established."),
        (["unknown"], True, "Inspect workflow/provider outcomes on the PR; execution is not established."),
        ([], True, "Inspect workflow/provider outcomes on the PR; execution is not established."),
        (["passed"], False, "Review the remaining check inventory on the PR."),
        (["passed"], True, "Review required-check coverage and approvals on the PR."),
    ],
)
def test_text_gives_one_next_action_for_observed_results(
    report_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    results: list[str],
    complete: bool,
    next_action: str,
) -> None:
    report_payload["completeness"] = "complete" if complete else "incomplete"
    for revision in report_payload["revisions"]:
        revision["completeness"] = report_payload["completeness"]
        revision["checks"] = [_check(index, result, f"observed-{result}") for index, result in enumerate(results, 1)]
    monkeypatch.setattr(pr_checks, "collect_pr_checks", lambda *args, **kwargs: PullRequestChecks(report_payload))

    assert main(["pr-checks", PR_URL]) == (0 if complete else 1)

    output = capsys.readouterr()
    assert output.err == ""
    assert f"Next: {next_action}\n" in output.out
    assert output.out.count("Next:") == 1
    assert f"PR checks: {PR_URL}/checks\n" in output.out


@pytest.mark.parametrize("show_all", [False, True])
def test_json_always_contains_full_report_and_matches_schema(
    report_payload: dict[str, Any],
    schema_validator: Draft202012Validator,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    show_all: bool,
) -> None:
    report = PullRequestChecks(report_payload)
    monkeypatch.setattr(pr_checks, "collect_pr_checks", lambda *args, **kwargs: report)

    assert main(["pr-checks", PR_URL, "--format", "json", *(["--all"] if show_all else [])]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload == report.to_dict()
    assert output.err == ""
    schema_validator.validate(payload)


@pytest.mark.parametrize("complete,result,exit_code", [(True, "failed", 0), (False, "passed", 1)])
def test_exit_status_reports_inventory_completeness_instead_of_check_success(
    report_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    complete: bool,
    result: str,
    exit_code: int,
) -> None:
    report_payload["completeness"] = "complete" if complete else "incomplete"
    for revision in report_payload["revisions"]:
        revision["completeness"] = report_payload["completeness"]
        revision["checks"] = [_check(1, result, "observed-check")]
    monkeypatch.setattr(pr_checks, "collect_pr_checks", lambda *args, **kwargs: PullRequestChecks(report_payload))

    assert main(["pr-checks", PR_URL]) == exit_code

    output = capsys.readouterr()
    assert output.err == ""
    assert f"Report inventory: {report_payload['completeness']}" in output.out


@pytest.mark.parametrize("availability,state", [("unavailable", "open"), ("not_applicable", "closed")])
def test_missing_test_merge_inventory_is_explicit(
    report_payload: dict[str, Any],
    schema_validator: Draft202012Validator,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    availability: str,
    state: str,
) -> None:
    report_payload.update(test_merge_status=availability, state=state)
    report_payload["revisions"] = report_payload["revisions"][:1]
    report_payload["revisions"][0]["checks"] = []
    monkeypatch.setattr(pr_checks, "collect_pr_checks", lambda *args, **kwargs: PullRequestChecks(report_payload))

    assert main(["pr-checks", PR_URL]) == 0

    output = capsys.readouterr()
    head, merge = output.out.split("\ntest_merge\n")
    assert "Observed: passed=0, failed=0, pending=0, other outcomes=0, unknown=0" in head
    assert "No checks observed." in head
    assert f"Availability: {availability}" in merge
    assert "No inventory available for this revision." in merge
    assert "Observed:" not in merge
    schema_validator.validate(report_payload)


@pytest.mark.parametrize("credential", [None, "private-credential-canary"])
def test_command_needs_no_checkout_and_uses_only_explicit_token_environment(
    tmp_path: Path,
    report_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    credential: str | None,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "ignored-github-token")
    monkeypatch.setenv("GH_TOKEN", "ignored-gh-token")
    if credential is not None:
        monkeypatch.setenv("EVAGIX_GITHUB_TOKEN", credential)
    (tmp_path / ".env").write_text("EVAGIX_GITHUB_TOKEN=ignored-dotenv-token\n", encoding="utf-8")
    (tmp_path / "evagix.toml").write_text('github_token = "ignored-config-token"\n', encoding="utf-8")
    calls: list[tuple[str, str | None]] = []

    def collect(url: str, *, token: str | None) -> PullRequestChecks:
        calls.append((url, token))
        return PullRequestChecks(report_payload)

    def unexpected_scan(*args: object, **kwargs: object) -> None:
        pytest.fail("pr-checks must not scan a local checkout")

    monkeypatch.setattr(pr_checks, "collect_pr_checks", collect)
    monkeypatch.setattr(common, "_facts", unexpected_scan)

    assert main(["pr-checks", PR_URL]) == 0

    output = capsys.readouterr()
    assert calls == [(PR_URL, credential)]
    assert output.err == ""
    assert "credential-canary" not in output.out
    assert "ignored-" not in output.out


@pytest.mark.parametrize("output_format", ["text", "json"])
def test_remote_text_is_redacted_and_invisible_controls_are_escaped_without_escaping_arabic(
    report_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    output_format: str,
) -> None:
    hostile = "اختبار\x1b[31m\nrow\r\t\u202e\u2066\u200b\u2028\u2029\U000e0001\ud800 password=private-canary"
    check = report_payload["revisions"][0]["checks"][1]
    for field in ("name", "producer", "status", "conclusion"):
        check[field] = hostile
    report = PullRequestChecks(report_payload)
    monkeypatch.setattr(pr_checks, "collect_pr_checks", lambda *args, **kwargs: report)

    assert main(["pr-checks", PR_URL, "--format", output_format]) == 0

    output = capsys.readouterr()
    assert output.err == ""
    assert "اختبار" in output.out
    assert "private-canary" not in output.out
    assert "[REDACTED]" in output.out
    for char in ("\x1b", "\r", "\t", "\u202e", "\u2066", "\u200b", "\u2028", "\u2029", "\U000e0001", "\ud800"):
        assert char not in output.out
    assert "\nrow" not in output.out
    assert "\\u202e" in output.out
    if output_format == "json":
        assert json.loads(output.out) == report.to_dict()


@pytest.mark.parametrize("code", ["invalid_pull_request", "pr_changed", "unauthorized", "rate_limited"])
def test_collection_failure_has_safe_classified_stderr_and_empty_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], code: str
) -> None:
    def fail(*args: object, **kwargs: object) -> PullRequestChecks:
        raise GitHubCollectionError(code)

    monkeypatch.setattr(pr_checks, "collect_pr_checks", fail)

    assert main(["pr-checks", "private-url-canary"]) == 2

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == f"ERROR: {GitHubCollectionError(code)} ({code})\n"
    assert "private-url-canary" not in output.err


@pytest.mark.parametrize("args", [[], [PR_URL, "--format", "private-format-canary"]])
def test_url_required_and_format_error_does_not_echo_value(capsys: pytest.CaptureFixture[str], args: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["pr-checks", *args])

    output = capsys.readouterr()
    assert error.value.code == 2
    assert output.out == ""
    assert "private-format-canary" not in output.err


def test_default_commands_and_help_do_not_collect(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    assert main(["scan", str(tmp_path)]) == 0
    assert main(["doctor", str(tmp_path)]) in {0, 1}
    capsys.readouterr()
    for args in (["--help"], ["pr-checks", "--help"]):
        with pytest.raises(SystemExit) as error:
            main(args)
        assert error.value.code == 0
        output = capsys.readouterr()
        assert output.err == ""
    help_text = " ".join(output.out.split())
    assert "network requests" in help_text
    assert "EVAGIX_GITHUB_TOKEN" in help_text
    assert "not check success" in help_text
    assert "JSON always includes every collected row" in help_text


@pytest.mark.parametrize(
    "path,value",
    [
        (("unexpected",), True),
        (("schema_version",), "2.0"),
        (("kind",), "check_verification"),
        (("repository_id",), True),
        (("repository_id",), 0),
        (("repository_id",), 2**63),
        (("pull_request",), "7"),
        (("base_sha",), "a" * 39),
        (("head_sha",), "b" * 40 + "\n"),
        (("state",), "merged"),
        (("test_merge_status",), "not_applicable"),
        (("policy_decision",), "allow"),
        (("required_checks",), "passed"),
        (("completeness",), "done"),
        (("revisions",), []),
        (("revisions", 0, "kind"), "test_merge"),
        (("revisions", 1, "kind"), "head"),
        (("revisions", 0, "unexpected"), True),
        (("revisions", 0, "sha"), "B" * 40),
        (("revisions", 0, "completeness"), True),
        (("revisions", 0, "checks", 0, "unexpected"), True),
        (("revisions", 0, "checks", 0, "kind"), "job"),
        (("revisions", 0, "checks", 0, "id"), 0),
        (("revisions", 0, "checks", 0, "producer_id"), 2**63),
        (("revisions", 0, "checks", 0, "name"), ""),
        (("revisions", 0, "checks", 0, "status"), None),
        (("revisions", 0, "checks", 0, "result"), "success"),
        (("revisions", 0, "checks", 0, "url"), []),
    ],
)
def test_schema_rejects_invalid_types_enums_identities_and_extra_fields(
    report_payload: dict[str, Any],
    schema_validator: Draft202012Validator,
    path: tuple[str | int, ...],
    value: object,
) -> None:
    target = report_payload
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    assert not schema_validator.is_valid(report_payload)


@pytest.mark.parametrize("location", [(), ("revisions", 0), ("revisions", 0, "checks", 0)])
def test_schema_requires_every_report_field(
    report_payload: dict[str, Any], schema_validator: Draft202012Validator, location: tuple[str | int, ...]
) -> None:
    target = report_payload
    for part in location:
        target = target[part]
    for field in tuple(target):
        value = target.pop(field)
        assert not schema_validator.is_valid(report_payload), field
        target[field] = value
