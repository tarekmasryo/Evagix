from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from evagix.cli import main
from evagix.commands import common, verification
from evagix.core.io import safe_read_text_result
from evagix.verification.checks import evaluate_check
from evagix.verification.contracts import (
    MAX_ATTEMPT,
    Conclusion,
    ContractError,
    EvidenceBatch,
    RunEvidence,
    SourceAssessment,
    parse_request,
)
from evagix.verification.github_actions import GitHubActionsScope
from evagix.verification.github_collection import CollectedEvidence, GitHubCollectionError


@pytest.fixture
def request_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "kind": "check_succeeded",
        "subject": {
            "repository": "github:repository:17",
            "revision": "a" * 40,
            "subject_kind": "commit",
            "workflow": "github-actions:workflow:30",
            "job": "github-actions:job:100",
        },
        "run_id": "20",
        "attempt": 2,
    }


@pytest.fixture(autouse=True)
def no_implicit_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVAGIX_GITHUB_TOKEN", raising=False)

    def unexpected_collection(*args: object, **kwargs: object) -> CollectedEvidence:
        pytest.fail("Unexpected GitHub collection")

    monkeypatch.setattr(verification, "collect_actions_attempt", unexpected_collection)


def _request_file(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "selected check.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _collected(payload: dict[str, Any], conclusion: Conclusion | None = "success") -> CollectedEvidence:
    request = parse_request(payload)
    evidence = RunEvidence(
        request.subject.job,
        request.subject,
        request.run_id,
        request.attempt,
        "completed" if conclusion is not None else "in_progress",
        conclusion,
    )
    batch = EvidenceBatch("ci", "cli-fixture", (evidence,), complete=True)
    return CollectedEvidence(batch, SourceAssessment(batch.digest(), "verified", "cli-fixture"))


@pytest.mark.parametrize("output_format", ["text", "json"])
@pytest.mark.parametrize(
    "conclusion,condition,exit_code",
    [
        ("success", "supported", 0),
        ("failure", "contradicted", 1),
        ("skipped", "unverified", 1),
        (None, "unverified", 1),
    ],
)
def test_verify_check_preserves_result_and_exit_contract(
    tmp_path: Path,
    request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    output_format: str,
    conclusion: Conclusion | None,
    condition: str,
    exit_code: int,
) -> None:
    path = _request_file(tmp_path, request_payload)
    collected = _collected(request_payload, conclusion)
    calls: list[tuple[str, GitHubActionsScope, str | None]] = []

    def collect(repository: str, *, scope: GitHubActionsScope, token: str | None) -> CollectedEvidence:
        calls.append((repository, scope, token))
        return collected

    monkeypatch.setattr(verification, "collect_actions_attempt", collect)
    result = main(["verify-check", "--request", str(path), "--github-repo", "owner/repo", "--format", output_format])

    output = capsys.readouterr()
    assert result == exit_code
    assert output.err == ""
    assert calls == [("owner/repo", GitHubActionsScope(17, 20, 2), None)]
    if output_format == "json":
        expected = evaluate_check(parse_request(request_payload), collected.batch, assessment=collected.assessment)
        assert json.loads(output.out) == expected.to_dict()
    else:
        assert output.out.startswith(f"GitHub-reported check result: {condition}\n")
        assert "Caller-selected check; provider-reported metadata only." in output.out
        assert "Policy decision: not_evaluated" in output.out


def test_verify_check_keeps_original_selection_when_evidence_differs(
    tmp_path: Path,
    request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = _request_file(tmp_path, request_payload)
    different = _collected(request_payload)
    record = different.batch.records[0]
    batch = replace(different.batch, records=(replace(record, subject=replace(record.subject, revision="b" * 40)),))
    collected = CollectedEvidence(batch, SourceAssessment(batch.digest(), "verified", "cli-fixture"))
    monkeypatch.setattr(verification, "collect_actions_attempt", lambda *args, **kwargs: collected)

    assert main(["verify-check", "--request", str(path), "--github-repo", "owner/repo", "--format", "json"]) == 1

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["request"] == request_payload
    assert payload["reason"] == "subject_mismatch"
    assert payload["condition"] == "unverified"
    assert output.err == ""


@pytest.mark.parametrize("credential", [None, "credential-canary-not-for-output"])
def test_verify_check_only_uses_explicit_credential_environment_variable(
    tmp_path: Path,
    request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    credential: str | None,
) -> None:
    path = _request_file(tmp_path, request_payload)
    collected = _collected(request_payload)
    calls: list[str | None] = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "ignored-github-token")
    monkeypatch.setenv("GH_TOKEN", "ignored-gh-token")
    if credential is not None:
        monkeypatch.setenv("EVAGIX_GITHUB_TOKEN", credential)
    (tmp_path / ".env").write_text("EVAGIX_GITHUB_TOKEN=ignored-dotenv-token\n", encoding="utf-8")
    (tmp_path / "evagix.toml").write_text('github_token = "ignored-config-token"\n', encoding="utf-8")

    def collect(repository: str, *, scope: GitHubActionsScope, token: str | None) -> CollectedEvidence:
        calls.append(token)
        return collected

    def unexpected_scan(*args: object, **kwargs: object) -> None:
        pytest.fail("verify-check must not scan the checkout")

    monkeypatch.setattr(verification, "collect_actions_attempt", collect)
    monkeypatch.setattr(common, "_facts", unexpected_scan)

    assert main(["verify-check", "--request", str(path), "--github-repo", "owner/repo"]) == 0

    output = capsys.readouterr()
    assert calls == [credential]
    assert output.err == ""
    assert "credential-canary" not in output.out
    assert "ignored-" not in output.out


@pytest.mark.parametrize(
    "field,value",
    [
        ("repository", "owner/repo"),
        ("repository", "github:repository:017"),
        ("repository", "github:repository:0"),
        ("repository", f"github:repository:{2**63}"),
        ("workflow", "workflow:tests"),
        ("workflow", "github-actions:workflow:030"),
        ("workflow", f"github-actions:workflow:{2**63}"),
        ("job", "job:tests"),
        ("job", "github-actions:job:100/other"),
        ("job", f"github-actions:job:{2**63}"),
        ("subject_kind", "test_merge"),
        ("run_id", "run-20"),
        ("run_id", "020"),
        ("run_id", "0"),
        ("run_id", "+20"),
        ("run_id", "٢٠"),
        ("run_id", str(2**63)),
        ("attempt", True),
        ("attempt", 0),
        ("attempt", MAX_ATTEMPT + 1),
        ("source_assessment", {"verification": "verified"}),
    ],
)
def test_invalid_or_unsupported_request_is_rejected_before_collection(
    tmp_path: Path,
    request_payload: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: object,
) -> None:
    target = request_payload["subject"] if field in request_payload["subject"] else request_payload
    target[field] = value
    path = _request_file(tmp_path, request_payload)

    assert main(["verify-check", "--request", str(path), "--github-repo", "owner/repo"]) == 2

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "ERROR: Request must be a valid GitHub commit check request.\n"


@pytest.mark.parametrize(
    "text",
    [
        "not-json-untrusted-marker",
        "[]",
        "{}",
        '{"attempt": 1, "attempt": 2}',
        '{"subject": {"job": "one", "job": "two"}}',
        '{"attempt": NaN}',
        '{"attempt": Infinity}',
        '{"attempt": -Infinity}',
        "[" * 1100 + "]" * 1100,
    ],
)
def test_request_json_must_be_strict_before_collection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str
) -> None:
    path = tmp_path / "request.json"
    path.write_text(text, encoding="utf-8")

    assert main(["verify-check", "--request", str(path), "--github-repo", "owner/repo"]) == 2

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "ERROR: Request must be a valid GitHub commit check request.\n"


@pytest.mark.parametrize("extra_chars", [0, 1])
def test_request_read_is_once_and_exact_size_limit_is_allowed(
    tmp_path: Path,
    request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    extra_chars: int,
) -> None:
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request_payload).ljust(65536 + extra_chars), encoding="utf-8")
    reads: list[tuple[Path, int]] = []

    def read_once(path: Path, *, max_chars: int):
        reads.append((path, max_chars))
        return safe_read_text_result(path, max_chars=max_chars)

    monkeypatch.setattr(verification, "safe_read_text_result", read_once)
    if extra_chars == 0:
        collected = _collected(request_payload)
        monkeypatch.setattr(verification, "collect_actions_attempt", lambda *args, **kwargs: collected)

    assert main(["verify-check", "--request", str(path), "--github-repo", "owner/repo"]) == (
        0 if extra_chars == 0 else 2
    )

    output = capsys.readouterr()
    assert reads == [(path, 65536)]
    if extra_chars:
        assert output.out == ""
        assert output.err == "ERROR: Request file exceeds 65536 characters.\n"
    else:
        assert output.err == ""


@pytest.mark.parametrize("file_kind", ["missing", "directory", "invalid_utf8"])
def test_unreadable_request_does_not_echo_path_or_contents(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], file_kind: str
) -> None:
    path = tmp_path / "private-path-canary"
    if file_kind == "directory":
        path.mkdir()
    elif file_kind == "invalid_utf8":
        path.write_bytes(b"\xffprivate-content-canary")

    assert main(["verify-check", "--request", str(path), "--github-repo", "owner/repo"]) == 2

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "ERROR: Unable to read request file as UTF-8.\n"


@pytest.mark.parametrize(
    "code", ["unauthorized", "forbidden", "rate_limited", "redirect_refused", "invalid_repository"]
)
def test_collection_failures_are_classified_and_leave_stdout_empty(
    tmp_path: Path,
    request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    code: str,
) -> None:
    path = _request_file(tmp_path, request_payload)

    def fail(*args: object, **kwargs: object) -> CollectedEvidence:
        raise GitHubCollectionError(code)

    monkeypatch.setattr(verification, "collect_actions_attempt", fail)
    monkeypatch.setenv("EVAGIX_GITHUB_TOKEN", "private-credential-canary")

    assert main(["verify-check", "--request", str(path), "--github-repo", "private/repository"]) == 2

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == f"ERROR: {GitHubCollectionError(code)} ({code})\n"
    assert "private" not in output.err


def test_evaluation_failure_has_safe_fixed_message(
    tmp_path: Path,
    request_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = _request_file(tmp_path, request_payload)
    collected = _collected(request_payload)
    monkeypatch.setattr(verification, "collect_actions_attempt", lambda *args, **kwargs: collected)

    def fail(*args: object, **kwargs: object) -> None:
        raise ContractError("private-provider-payload-canary")

    monkeypatch.setattr(verification, "evaluate_check", fail)

    assert main(["verify-check", "--request", str(path), "--github-repo", "owner/repo"]) == 2

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "ERROR: GitHub evidence could not be evaluated.\n"


@pytest.mark.parametrize("args", [[], ["--request", "request.json"], ["--github-repo", "owner/repo"]])
def test_both_explicit_inputs_are_required(capsys: pytest.CaptureFixture[str], args: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["verify-check", *args])

    assert error.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "required" in output.err


def test_invalid_output_format_is_not_echoed(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(
            [
                "verify-check",
                "--request",
                "request.json",
                "--github-repo",
                "owner/repo",
                "--format",
                "private-format-canary",
            ]
        )

    output = capsys.readouterr()
    assert error.value.code == 2
    assert output.out == ""
    assert "Output format must be text or json." in output.err
    assert "private-format-canary" not in output.err


def test_default_commands_and_help_do_not_collect(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    assert main(["scan", str(tmp_path)]) == 0
    assert main(["doctor", str(tmp_path)]) in {0, 1}
    capsys.readouterr()
    for args in (["--help"], ["verify-check", "--help"]):
        with pytest.raises(SystemExit) as error:
            main(args)
        assert error.value.code == 0
        output = capsys.readouterr()
        assert output.err == ""
    assert "EVAGIX_GITHUB_TOKEN" in output.out
    assert "network requests to GitHub.com" in output.out
    assert "does not authenticate required-check policy" in output.out
