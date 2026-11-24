from __future__ import annotations

import json
from dataclasses import replace

import pytest

from scripts.verification_spike import (
    CheckClaim,
    Conclusion,
    Evidence,
    RunState,
    SubjectKind,
    SyntheticFixtureSource,
    assess,
    evaluate,
    main,
    naive_any_success,
)


@pytest.fixture
def claim() -> CheckClaim:
    return CheckClaim("example/repo", "head-2", "commit", "tests", "python-3.11")


@pytest.fixture
def success(claim: CheckClaim) -> Evidence:
    return Evidence(claim, "run-selected", 2, "completed", "success")


@pytest.mark.parametrize("subject_kind", ["commit", "test_merge"])
def test_exact_scoped_identity_can_satisfy_a_check(claim: CheckClaim, subject_kind: SubjectKind) -> None:
    claim = replace(claim, subject_kind=subject_kind)
    report = Evidence(claim, "run-selected", 2, "completed", "success")
    source = SyntheticFixtureSource((report,), report.run_id, report.attempt)

    result = evaluate(claim, (report,), fixture_source=source)

    assert result.claim == claim
    assert result.source_verification == "synthetic_verified"
    assert result.freshness == "current"
    assert result.completeness == "complete"
    assert result.condition_result == "satisfied"


@pytest.mark.parametrize("field", ["repository", "revision", "subject_kind", "check", "job"])
def test_success_for_another_identity_does_not_satisfy_claim(claim: CheckClaim, success: Evidence, field: str) -> None:
    changes = {field: "test_merge" if field == "subject_kind" else "other"}
    report = replace(success, subject=replace(claim, **changes))
    source = SyntheticFixtureSource((report,), report.run_id, report.attempt)

    result = evaluate(claim, (report,), fixture_source=source)

    assert result.condition_result == "unverified"
    assert result.reason == "subject_mismatch"
    assert naive_any_success((report,)) is True


def test_missing_source_does_not_authenticate_a_success(claim: CheckClaim, success: Evidence) -> None:
    result = evaluate(claim, (success,))

    assert result.source_verification == "unverified"
    assert result.condition_result == "unverified"
    assert result.reason == "source_unverified"


def test_equal_local_copy_has_no_synthetic_provenance(claim: CheckClaim, success: Evidence) -> None:
    copied = replace(success)
    source = SyntheticFixtureSource((success,), success.run_id, success.attempt)
    assert copied == success and copied is not success

    result = evaluate(claim, (copied,), fixture_source=source)

    assert source.recognizes(copied) is False
    assert result.source_verification == "unverified"
    assert result.condition_result == "unverified"


@pytest.mark.parametrize("conclusion", ["skipped", "neutral", "cancelled", "timed_out"])
def test_non_success_conclusions_do_not_satisfy_checks(
    claim: CheckClaim, success: Evidence, conclusion: Conclusion
) -> None:
    report = replace(success, conclusion=conclusion)
    source = SyntheticFixtureSource((report,), report.run_id, report.attempt)

    result = evaluate(claim, (report,), fixture_source=source)

    assert result.completeness == "complete"
    assert result.condition_result == "unverified"
    assert result.reason == f"non_decisive_conclusion:{conclusion}"


@pytest.mark.parametrize("state", ["queued", "in_progress", "cancelled"])
def test_unfinished_operational_states_do_not_satisfy_checks(
    claim: CheckClaim, success: Evidence, state: RunState
) -> None:
    report = replace(success, state=state, conclusion=None)
    source = SyntheticFixtureSource((report,), report.run_id, report.attempt)

    result = evaluate(claim, (report,), fixture_source=source)

    assert result.condition_result == "unverified"
    assert result.completeness == "incomplete"
    assert result.operational_state == state


def test_completed_run_without_conclusion_is_incomplete(claim: CheckClaim, success: Evidence) -> None:
    report = replace(success, conclusion=None)
    source = SyntheticFixtureSource((report,), report.run_id, report.attempt)

    result = evaluate(claim, (report,), fixture_source=source)

    assert result.condition_result == "unverified"
    assert result.completeness == "incomplete"
    assert result.reason == "conclusion_missing"


def test_incomplete_inventory_cannot_certify_success(claim: CheckClaim, success: Evidence) -> None:
    source = SyntheticFixtureSource((success,), success.run_id, success.attempt, inventory_complete=False)

    result = evaluate(claim, (success,), fixture_source=source)

    assert result.condition_result == "unverified"
    assert result.completeness == "incomplete"
    assert result.reason == "inventory_incomplete"


def test_missing_selected_run_does_not_fall_back_to_another_success(claim: CheckClaim, success: Evidence) -> None:
    source = SyntheticFixtureSource((success,), "another-run", success.attempt)

    result = evaluate(claim, (success,), fixture_source=source)

    assert result.condition_result == "unverified"
    assert result.freshness == "stale"
    assert result.reason == "selected_run_missing"


def test_missing_latest_attempt_does_not_fall_back_to_earlier_success(claim: CheckClaim, success: Evidence) -> None:
    source = SyntheticFixtureSource((success,), success.run_id, success.attempt + 1)

    result = evaluate(claim, (success,), fixture_source=source)

    assert result.condition_result == "unverified"
    assert result.freshness == "stale"
    assert result.reason == "latest_attempt_missing"


def test_attempt_newer_than_inventory_is_inconsistent(claim: CheckClaim, success: Evidence) -> None:
    source = SyntheticFixtureSource((success,), success.run_id, success.attempt - 1)

    result = evaluate(claim, (success,), fixture_source=source)

    assert result.condition_result == "unverified"
    assert result.reason == "attempt_inventory_inconsistent"


@pytest.mark.parametrize("reverse", [False, True])
def test_latest_in_progress_attempt_supersedes_older_success(
    claim: CheckClaim, success: Evidence, reverse: bool
) -> None:
    rerun = replace(success, attempt=success.attempt + 1, state="in_progress", conclusion=None)
    reports = (rerun, success) if reverse else (success, rerun)
    source = SyntheticFixtureSource(reports, rerun.run_id, rerun.attempt)

    result = evaluate(claim, reports, fixture_source=source)

    assert result.condition_result == "unverified"
    assert result.operational_state == "in_progress"
    assert naive_any_success(reports) is True


def test_selected_run_is_not_chosen_by_lexical_run_id(claim: CheckClaim, success: Evidence) -> None:
    selected_failure = replace(success, run_id="run-2", conclusion="failure")
    other_success = replace(success, run_id="run-999")
    reports = (other_success, selected_failure)
    source = SyntheticFixtureSource(reports, selected_failure.run_id, selected_failure.attempt)

    result = evaluate(claim, reports, fixture_source=source)

    assert result.condition_result == "contradicted"
    assert result.reason == "scoped_check_failed"


@pytest.mark.parametrize("reverse", [False, True])
def test_conflicting_results_for_the_selected_attempt_are_not_success(
    claim: CheckClaim, success: Evidence, reverse: bool
) -> None:
    failure = replace(success, conclusion="failure")
    reports = (failure, success) if reverse else (success, failure)
    source = SyntheticFixtureSource(reports, success.run_id, success.attempt)

    result = evaluate(claim, reports, fixture_source=source)

    assert result.condition_result == "unverified"
    assert result.operational_state == "conflicting"
    assert result.completeness == "incomplete"


def test_duplicate_identical_verified_records_do_not_create_conflict(claim: CheckClaim, success: Evidence) -> None:
    reports = (success, replace(success))
    source = SyntheticFixtureSource(reports, success.run_id, success.attempt)

    assert evaluate(claim, reports, fixture_source=source).condition_result == "satisfied"


def test_unrecognized_success_cannot_override_recognized_failure(claim: CheckClaim, success: Evidence) -> None:
    failure = replace(success, conclusion="failure")
    source = SyntheticFixtureSource((failure,), failure.run_id, failure.attempt)

    result = evaluate(claim, (success, failure), fixture_source=source)

    assert result.condition_result == "contradicted"


def test_omitting_claims_does_not_omit_required_policy(claim: CheckClaim, success: Evidence) -> None:
    failure = replace(success, conclusion="failure")
    source = SyntheticFixtureSource((failure,), failure.run_id, failure.attempt)

    result = assess((claim,), (), (failure,), fixture_source=source)

    assert len(result.required_checks) == 1
    assert result.submitted_claims == ()
    assert result.required_check_decision == "contradicted"


def test_missing_required_evidence_is_not_hidden_by_submitted_success(claim: CheckClaim, success: Evidence) -> None:
    required = replace(claim, check="lint")
    source = SyntheticFixtureSource((success,), success.run_id, success.attempt)

    result = assess((required,), (claim,), (success,), fixture_source=source)

    assert result.submitted_claims[0].condition_result == "satisfied"
    assert result.required_checks[0].condition_result == "unverified"
    assert result.required_check_decision == "unverified"


def test_all_required_jobs_must_succeed(claim: CheckClaim, success: Evidence) -> None:
    another_claim = replace(claim, job="python-3.12")
    another_success = replace(success, subject=another_claim)
    reports = (success, another_success)
    source = SyntheticFixtureSource(reports, success.run_id, success.attempt)

    result = assess((claim, another_claim), (), reports, fixture_source=source)

    assert result.required_check_decision == "satisfied"


def test_empty_policy_does_not_imply_readiness() -> None:
    assert assess((), (), ()).required_check_decision == "unverified"


def test_absent_required_report_remains_missing(claim: CheckClaim) -> None:
    result = assess((claim,), (), ())

    assert result.required_check_decision == "unverified"
    assert result.required_checks[0].source_verification == "missing"
    assert result.required_checks[0].reason == "no_evidence"


def test_dirty_worktree_is_not_covered_by_commit_evidence(claim: CheckClaim, success: Evidence) -> None:
    source = SyntheticFixtureSource((success,), success.run_id, success.attempt)

    result = assess((claim,), (claim,), (success,), fixture_source=source, uncommitted_work=True)

    assert result.required_check_decision == "unverified"
    for check in (*result.required_checks, *result.submitted_claims):
        assert check.completeness == "not_covered"
        assert check.condition_result == "unverified"
        assert check.reason == "uncommitted_work"


def test_demo_output_discloses_synthetic_scope(capsys: pytest.CaptureFixture[str]) -> None:
    assert main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert "SIMULATED fixture provenance" in payload["trust"]
    assert "no actual CI authentication" in payload["trust"]
    assert "not a product-value benchmark" in payload["scope"]
    assert payload["comparator"] == "Intentionally weak any-success demonstration; not a model of GitHub CI"
    scenarios = {row["scenario"]: row for row in payload["scenarios"]}
    assert scenarios["current_success"]["assessment"]["required_check_decision"] == "satisfied"
    assert scenarios["dirty_worktree"]["assessment"]["required_check_decision"] == "unverified"
