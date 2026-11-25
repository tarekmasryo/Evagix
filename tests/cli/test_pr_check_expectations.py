from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from evagix.cli import main
from evagix.commands import pr_checks
from evagix.verification.github_collection import GitHubCollectionError
from evagix.verification.github_pr_checks import PullRequestChecks

PR_URL = "https://github.com/owner/repo/pull/7"


def _check(identifier: int, result: str, name: str) -> dict[str, Any]:
    status, conclusion = {
        "passed": ("completed", "success"),
        "failed": ("completed", "failure"),
        "pending": ("in_progress", None),
        "other": ("completed", "skipped"),
    }[result]
    return {
        "kind": "check_run",
        "id": identifier,
        "name": name,
        "producer": "Check App",
        "producer_id": 9,
        "status": status,
        "conclusion": conclusion,
        "result": result,
        "url": f"https://github.com/owner/repo/actions/runs/20/job/{identifier}",
    }


@pytest.fixture
def report_payload() -> dict[str, Any]:
    return {
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
        "revisions": [
            {
                "kind": "head",
                "sha": "b" * 40,
                "completeness": "complete",
                "checks": [
                    _check(i, result, f"check-{result}")
                    for i, result in enumerate(["passed", "failed", "pending", "other"], 1)
                ],
            }
        ],
    }


def _expectations(names: list[str], *, revision: str = "head", repository_id: int = 17) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "repository_id": repository_id,
        "checks": [{"revision": revision, "kind": "check_run", "name": name, "producer_id": 9} for name in names],
    }


def _write(root: Path, value: dict[str, Any]) -> Path:
    path = root / "expectations.json"
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def no_unexpected_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVAGIX_GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(pr_checks, "collect_pr_checks", lambda *args, **kwargs: pytest.fail("Unexpected collection"))


@pytest.fixture
def schema() -> Draft202012Validator:
    payload = json.loads(
        files("evagix.schemas").joinpath("github-pr-expectations.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(payload)
    return Draft202012Validator(payload)


@pytest.mark.parametrize("output_format", ["text", "json"])
@pytest.mark.parametrize("show_all", [False, True])
def test_expectation_outcomes_and_schema(
    tmp_path: Path,
    report_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    schema: Draft202012Validator,
    output_format: str,
    show_all: bool,
) -> None:
    names = ["check-passed", "check-failed", "check-pending", "check-other", "not-reported"]
    path = _write(tmp_path, _expectations(names))
    monkeypatch.setattr(pr_checks, "collect_pr_checks", lambda *args, **kwargs: PullRequestChecks(report_payload))
    args = ["pr-checks", PR_URL, "--expectations", str(path), "--format", output_format]
    assert main(args + (["--all"] if show_all else [])) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    if output_format == "json":
        payload = json.loads(captured.out)
        schema.validate(payload)
        assert [item["outcome"] for item in payload["results"]] == [
            "passed",
            "failed",
            "pending",
            "unverified",
            "missing",
        ]
        assert payload["expectations_authority"] == "caller_supplied"
        assert payload["policy_decision"] == "not_evaluated"
    else:
        assert "passed=1, failed=1, pending=1, missing=1, unverified=1" in captured.out
        assert ("[passed] check-passed" in captured.out) is show_all
        for state in ["failed", "pending", "missing", "unverified"]:
            assert f"[{state}]" in captured.out
        assert "producer ID: 9" in captured.out
        assert "Revision: " + "b" * 40 in captured.out
        assert "reason: not_observed" in captured.out
        assert "Next: Review failed or missing" in captured.out
        assert "not_evaluated" in captured.out


@pytest.mark.parametrize("complete", [False, True])
def test_incomplete_collection_differs_from_missing_expectation(
    tmp_path: Path,
    report_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    schema: Draft202012Validator,
    complete: bool,
) -> None:
    report_payload["completeness"] = "complete" if complete else "incomplete"
    report_payload["revisions"][0]["completeness"] = report_payload["completeness"]
    path = _write(tmp_path, _expectations(["not-reported"]))
    monkeypatch.setattr(pr_checks, "collect_pr_checks", lambda *args, **kwargs: PullRequestChecks(report_payload))
    assert main(["pr-checks", PR_URL, "--expectations", str(path), "--format", "json"]) == (0 if complete else 1)
    payload = json.loads(capsys.readouterr().out)
    schema.validate(payload)
    assert payload["results"][0]["outcome"] == ("missing" if complete else "unverified")


def test_unavailable_merge_revision_is_not_missing(
    tmp_path: Path,
    report_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    schema: Draft202012Validator,
) -> None:
    path = _write(tmp_path, _expectations(["check-passed"], revision="test_merge"))
    monkeypatch.setattr(pr_checks, "collect_pr_checks", lambda *args, **kwargs: PullRequestChecks(report_payload))
    assert main(["pr-checks", PR_URL, "--expectations", str(path), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    schema.validate(payload)
    assert payload["results"][0]["revision_sha"] is None
    assert payload["results"][0]["reason"] == "revision_unavailable"


def test_repository_mismatch_is_operational_error(
    tmp_path: Path, report_payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, _expectations(["check-passed"], repository_id=18))
    monkeypatch.setattr(pr_checks, "collect_pr_checks", lambda *args, **kwargs: PullRequestChecks(report_payload))
    assert main(["pr-checks", PR_URL, "--expectations", str(path), "--format", "json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR: Expectations repository does not match the collected repository\n"


@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "directory",
        "utf8",
        "malformed",
        "duplicate",
        "nonobject",
        "oversized",
        "unknown",
        "bool",
        "float",
        "empty",
    ],
)
def test_invalid_expectations_fail_before_collection(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    kind: str,
) -> None:
    path = tmp_path / "input.json"
    valid = _expectations(["check-passed"])
    if kind == "directory":
        path.mkdir()
    elif kind == "utf8":
        path.write_bytes(b"\xff")
    elif kind == "malformed":
        path.write_text("{ not JSON secret-value", encoding="utf-8")
    elif kind == "duplicate":
        path.write_text('{"repository_id":17,"repository_id":18}', encoding="utf-8")
    elif kind == "nonobject":
        path.write_text("[]", encoding="utf-8")
    elif kind == "oversized":
        path.write_text(json.dumps(valid).ljust(65_537), encoding="utf-8")
    elif kind != "missing":
        if kind == "unknown":
            valid["$ref"] = "https://untrusted.invalid/schema"
        elif kind == "bool":
            valid["repository_id"] = True
        elif kind == "float":
            valid["checks"][0]["producer_id"] = 9.0
        elif kind == "empty":
            valid["checks"] = []
        path.write_text(json.dumps(valid), encoding="utf-8")
    assert main(["pr-checks", PR_URL, "--expectations", str(path), "--format", "json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR: Expectations must be a valid bounded UTF-8 check expectations file.\n"


def test_exact_character_limit_accepts_the_file(
    tmp_path: Path, report_payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, _expectations(["check-passed"]))
    path.write_text(path.read_text().ljust(65_536), encoding="utf-8")
    monkeypatch.setattr(pr_checks, "collect_pr_checks", lambda *args, **kwargs: PullRequestChecks(report_payload))
    assert main(["pr-checks", PR_URL, "--expectations", str(path)]) == 0
    output = capsys.readouterr().out
    assert "passed=1" in output
    assert "Next: Review whether" in output


@pytest.mark.parametrize("output_format", ["text", "json"])
def test_raw_identity_matching_precedes_redacted_and_escaped_output(
    tmp_path: Path,
    report_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    output_format: str,
) -> None:
    secret = "ghp_" + "a" * 36
    name = "اختبار\u202e-" + secret
    report_payload["revisions"][0]["checks"][0]["name"] = name
    path = _write(tmp_path, _expectations([name]))
    monkeypatch.setattr(pr_checks, "collect_pr_checks", lambda *args, **kwargs: PullRequestChecks(report_payload))
    assert main(["pr-checks", PR_URL, "--expectations", str(path), "--all", "--format", output_format]) == 0
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err
    assert "\u202e" not in captured.out
    assert "\\u202e" in captured.out
    if output_format == "json":
        assert json.loads(captured.out)["results"][0]["outcome"] == "passed"
    else:
        assert "[passed]" in captured.out
        assert "اختبار" in captured.out


@pytest.mark.parametrize("name", ["check-pending", "check-other"])
def test_next_action_for_pending_or_unverified(
    tmp_path: Path,
    report_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    name: str,
) -> None:
    path = _write(tmp_path, _expectations([name]))
    monkeypatch.setattr(pr_checks, "collect_pr_checks", lambda *args, **kwargs: PullRequestChecks(report_payload))
    assert main(["pr-checks", PR_URL, "--expectations", str(path)]) == 0
    assert ("Next: Wait" if name == "check-pending" else "Next: Resolve") in capsys.readouterr().out


def test_expected_mode_collection_error_is_not_a_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, _expectations(["check-passed"]))

    def fail(*args: object, **kwargs: object) -> None:
        raise GitHubCollectionError("rate_limited")

    monkeypatch.setattr(pr_checks, "collect_pr_checks", fail)
    assert main(["pr-checks", PR_URL, "--expectations", str(path), "--format", "json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "rate_limited" in captured.err


def test_unreadable_expectations_error_does_not_expose_path_or_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    marker = "private-file-marker"

    def fail(*args: object, **kwargs: object) -> None:
        raise PermissionError(marker)

    monkeypatch.setattr(pr_checks, "safe_read_text_result", fail)
    assert main(["pr-checks", PR_URL, "--expectations", str(tmp_path / marker)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert marker not in captured.err
    assert captured.err.startswith("ERROR: Expectations")


def test_unknown_producer_is_displayed_as_unverified(
    tmp_path: Path, report_payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report_payload["revisions"][0]["checks"][0]["producer_id"] = None
    path = _write(tmp_path, _expectations(["check-passed"]))
    monkeypatch.setattr(pr_checks, "collect_pr_checks", lambda *args, **kwargs: PullRequestChecks(report_payload))
    assert main(["pr-checks", PR_URL, "--expectations", str(path)]) == 0
    captured = capsys.readouterr()
    assert "[unverified] check-passed" in captured.out
    assert "reason: producer_unknown" in captured.out
    assert "Observed ID: 1; producer ID: unknown" in captured.out


@pytest.mark.parametrize("output_format", ["text", "json"])
def test_rendered_expectations_budget_rejects_without_partial_output(
    tmp_path: Path,
    report_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    output_format: str,
) -> None:
    path = _write(tmp_path, _expectations(["check-passed"]))
    monkeypatch.setattr(pr_checks, "collect_pr_checks", lambda *args, **kwargs: PullRequestChecks(report_payload))
    monkeypatch.setattr(pr_checks, "_MAX_EXPECTATIONS_OUTPUT_BYTES", 64)
    assert main(["pr-checks", PR_URL, "--expectations", str(path), "--format", output_format]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR: Expectations report exceeds the 64-byte output limit.\n"
    assert main(["pr-checks", PR_URL, "--format", output_format]) == 0
    assert capsys.readouterr().out


@pytest.mark.parametrize("output_format", ["text", "json"])
def test_output_limit_counts_utf8_bytes_and_final_newline(
    tmp_path: Path,
    report_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    output_format: str,
) -> None:
    name = "اختبار"
    report_payload["revisions"][0]["checks"][0]["name"] = name
    path = _write(tmp_path, _expectations([name]))
    monkeypatch.setattr(pr_checks, "collect_pr_checks", lambda *args, **kwargs: PullRequestChecks(report_payload))
    args = ["pr-checks", PR_URL, "--expectations", str(path), "--all", "--format", output_format]
    assert main(args) == 0
    output = capsys.readouterr().out
    limit = len(output.encode("utf-8"))
    assert limit > len(output)
    monkeypatch.setattr(pr_checks, "_MAX_EXPECTATIONS_OUTPUT_BYTES", limit - 1)
    assert main(args) == 2
    assert capsys.readouterr().out == ""
    monkeypatch.setattr(pr_checks, "_MAX_EXPECTATIONS_OUTPUT_BYTES", limit)
    assert main(args) == 0
    assert capsys.readouterr().out == output
