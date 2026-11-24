from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from itertools import permutations

import pytest

from evagix.verification import (
    CheckRequest,
    CheckSubject,
    ContractError,
    EvidenceBatch,
    RunEvidence,
    SourceAssessment,
    evaluate_check,
    parse_batch,
    parse_request,
)


@pytest.fixture
def subject() -> CheckSubject:
    return CheckSubject("example/project", "a" * 40, "commit", "workflow:tests", "python:3.11")


@pytest.fixture
def check_request(subject: CheckSubject) -> CheckRequest:
    return CheckRequest(subject, "run-20", 2)


@pytest.fixture
def success(subject: CheckSubject) -> RunEvidence:
    return RunEvidence("record-1", subject, "run-20", 2, "completed", "success")


def assessed(batch: EvidenceBatch) -> SourceAssessment:
    # A simulated trusted caller, not an authentication test.
    return SourceAssessment(batch.digest(), "verified", "acceptance-fixture")


@pytest.mark.parametrize("kind", ["ci", "local"])
@pytest.mark.parametrize("conclusion,condition", [("success", "supported"), ("failure", "contradicted")])
def test_decisive_result_requires_explicit_assessed_exact_check(check_request, success, kind, conclusion, condition):
    batch = EvidenceBatch(kind, "collector", (replace(success, conclusion=conclusion),), complete=True)

    result = evaluate_check(check_request, batch, assessment=assessed(batch))

    assert result.condition == condition
    assert result.source_verification == "caller_verified"
    assert result.evidence_match == "match"
    assert result.completeness == "complete"
    assert result.evidence_ids == ("record-1",)
    assert result.to_dict()["policy_decision"] == "not_evaluated"


@pytest.mark.parametrize("kind", ["ci", "local"])
def test_source_label_cannot_verify_itself(check_request, success, kind):
    batch = EvidenceBatch(kind, "trusted-looking-provider", (success,), complete=True)

    for assessment in (None, SourceAssessment(batch.digest(), "unverified", "collector")):
        result = evaluate_check(check_request, batch, assessment=assessment)
        assert result.condition == "unverified"
        assert result.reason == "source_unverified"
        assert result.evidence_match == "match"
        assert result.completeness == "complete"


@pytest.mark.parametrize(
    "field,value",
    [
        ("repository", "elsewhere/project"),
        ("revision", "b" * 40),
        ("subject_kind", "test_merge"),
        ("workflow", "workflow:other"),
        ("job", "python:3.12"),
    ],
)
def test_each_subject_component_is_required(check_request, success, field, value):
    evidence = replace(success, subject=replace(success.subject, **{field: value}))
    batch = EvidenceBatch("ci", "collector", (evidence,), complete=True)
    result = evaluate_check(check_request, batch, assessment=assessed(batch))
    assert (result.condition, result.reason, result.evidence_match) == ("unverified", "subject_mismatch", "mismatch")


def test_verification_does_not_reuse_the_display_name_of_a_different_job(check_request, success):
    other = replace(success, subject=replace(success.subject, job="other-job"))
    selected = replace(success, conclusion="failure")
    batch = EvidenceBatch("ci", "collector", (other, selected), complete=True)
    assert evaluate_check(check_request, batch, assessment=assessed(batch)).condition == "contradicted"


@pytest.mark.parametrize(
    "field,value,reason", [("run_id", "run-99", "run_mismatch"), ("attempt", 1, "attempt_mismatch")]
)
def test_selected_run_and_attempt_never_fall_back_to_any_success(check_request, success, field, value, reason):
    batch = EvidenceBatch("ci", "collector", (replace(success, **{field: value}),), complete=True)
    result = evaluate_check(check_request, batch, assessment=assessed(batch))
    assert result.condition == "unverified"
    assert result.reason == reason


def test_newer_attempt_invalidates_caller_selection_independent_of_order(check_request, success):
    newer = replace(success, record_id="record-2", attempt=3, state="in_progress", conclusion=None)
    for records in permutations((success, newer)):
        batch = EvidenceBatch("ci", "collector", records, complete=True)
        result = evaluate_check(check_request, batch, assessment=assessed(batch))
        assert (result.condition, result.reason) == ("unverified", "inconsistent_attempt_inventory")
        assert result.run_state is None
        assert result.to_dict()["engine_status"] == "completed"


def test_conflicts_and_equivalent_duplicates_are_order_independent(check_request, success):
    failure = replace(success, record_id="record-2", conclusion="failure")
    for records in permutations((success, failure)):
        batch = EvidenceBatch("ci", "collector", records, complete=True)
        result = evaluate_check(check_request, batch, assessment=assessed(batch))
        assert result.reason == "conflicting_results"
        assert result.condition == "unverified"
        assert result.evidence_ids == ("record-1", "record-2")
    batch = EvidenceBatch("ci", "collector", (success, success, replace(success, record_id="record-2")), complete=True)
    result = evaluate_check(check_request, batch, assessment=assessed(batch))
    assert result.condition == "supported"
    assert result.evidence_ids == ("record-1", "record-2")


@pytest.mark.parametrize("conclusion", [None, "neutral", "skipped", "cancelled", "timed_out"])
def test_non_decisive_conclusion_cannot_support_a_success_claim(check_request, success, conclusion):
    batch = EvidenceBatch("ci", "collector", (replace(success, conclusion=conclusion),), complete=True)
    result = evaluate_check(check_request, batch, assessment=assessed(batch))
    assert result.condition == "unverified"
    assert result.reason == ("conclusion_missing" if conclusion is None else "non_success_conclusion")


@pytest.mark.parametrize("state", ["queued", "in_progress", "cancelled"])
def test_ci_operational_state_is_not_the_engine_status(check_request, success, state):
    batch = EvidenceBatch("ci", "collector", (replace(success, state=state, conclusion=None),), complete=True)
    result = evaluate_check(check_request, batch, assessment=assessed(batch))
    assert result.run_state == state
    assert result.reason == "run_not_completed"
    assert result.to_dict()["engine_status"] == "completed"


def test_missing_and_incomplete_data_remain_explicit(check_request, success):
    empty = EvidenceBatch("ci", "collector", (), complete=True)
    assert evaluate_check(check_request, empty, assessment=assessed(empty)).reason == "no_evidence"
    incomplete = EvidenceBatch("ci", "collector", (success,))
    result = evaluate_check(check_request, incomplete, assessment=assessed(incomplete))
    assert (result.condition, result.reason, result.completeness) == (
        "unverified",
        "incomplete_inventory",
        "incomplete",
    )
    assert result.source_verification == "caller_verified"
    assert result.evidence_match == "match"


def test_assessment_cannot_be_replayed_after_any_material_batch_change(check_request, success):
    original = EvidenceBatch("ci", "collector", (success,), complete=True)
    assessment = assessed(original)
    alternatives = [
        replace(original, source_kind="local"),
        replace(original, source_id="different"),
        replace(original, complete=False),
        replace(original, records=()),
    ]
    for changes in (
        {"record_id": "different"},
        {"run_id": "run-21"},
        {"attempt": 3},
        {"state": "queued", "conclusion": None},
        {"conclusion": "failure"},
        {"subject": replace(success.subject, revision="b" * 40)},
    ):
        alternatives.append(replace(original, records=(replace(success, **changes),)))
    for batch in alternatives:
        result = evaluate_check(check_request, batch, assessment=assessment)
        assert (result.condition, result.source_verification, result.reason) == (
            "unverified",
            "binding_mismatch",
            "source_binding_mismatch",
        )


def test_digest_is_stable_for_reordering_and_data_is_immutable(subject, success):
    records = (success, replace(success, record_id="record-2", conclusion="failure"))
    batch = EvidenceBatch("local", "collector", records, complete=True)
    assert batch.digest() == replace(batch, records=tuple(reversed(records))).digest()
    assert batch.digest() != replace(batch, records=records + (success,)).digest()
    with pytest.raises(FrozenInstanceError):
        subject.revision = "b" * 40


def test_matching_and_digest_use_raw_identities_not_redacted_labels(check_request, success):
    claimed = replace(check_request.subject, workflow="password=synthetic-one")
    different = replace(claimed, workflow="password=synthetic-two")
    record = replace(success, subject=different)
    batch = EvidenceBatch("ci", "token=synthetic-three", (record,), complete=True)
    result = evaluate_check(replace(check_request, subject=claimed), batch, assessment=assessed(batch))
    assert result.reason == "subject_mismatch"
    output = json.dumps(result.to_dict())
    assert "synthetic-one" not in output and "synthetic-three" not in output
    assert "[REDACTED]" in output
    assert batch.digest() != replace(batch, records=(replace(record, subject=claimed),)).digest()
    assert all("synthetic" not in repr(item) for item in (claimed, record, batch, result))


@pytest.mark.parametrize("field", ["repository", "workflow", "job"])
def test_unicode_subjects_and_sha256_revisions_are_supported(subject, success, field):
    subject = replace(subject, **{field: "مشروع-اختبار"}, revision="a" * 64)
    check_request = CheckRequest(subject, "run-20", 2)
    batch = EvidenceBatch("local", "collector", (replace(success, subject=subject),), complete=True)
    assert evaluate_check(check_request, batch, assessment=assessed(batch)).condition == "supported"


def test_json_parsers_do_not_accept_self_attested_trust_or_unknown_fields(check_request, success):
    request_payload = check_request._payload()
    batch_payload = {
        "schema_version": "1.0",
        "kind": "check_evidence",
        "source_kind": "ci",
        "source_id": "collector",
        "complete": True,
        "records": [success._payload()],
    }
    assert parse_request(request_payload) == check_request
    batch = parse_batch(batch_payload)
    assert evaluate_check(check_request, batch).condition == "unverified"
    for name in ("verified", "source_verification", "assessment", "batch_digest", "metadata"):
        with pytest.raises(ContractError, match="Invalid batch fields"):
            parse_batch({**batch_payload, name: "token=synthetic-sensitive"})
    with pytest.raises(ContractError):
        parse_request({**request_payload, "policy": "allow"})


@pytest.mark.parametrize("attempt", [True, False, 0, -1, 1.0, "1", None, 9_007_199_254_740_992])
def test_attempt_validation_rejects_coercion_and_out_of_range_values(subject, attempt):
    with pytest.raises(ContractError, match="^Invalid attempt$"):
        CheckRequest(subject, "run", attempt)


@pytest.mark.parametrize(
    "text", ["", " leading", "trailing ", "a\nb", "a\x1bb", "a\u2028b", "a\ud800b", "x" * 257, 42, None]
)
def test_identity_validation_does_not_echo_bad_input(subject, text):
    with pytest.raises(ContractError, match="^Invalid repository$"):
        replace(subject, repository=text)


@pytest.mark.parametrize("revision", ["main", "a" * 7, "A" * 40, "a" * 41, "g" * 40, None])
def test_subject_requires_a_full_unambiguous_revision(subject, revision):
    with pytest.raises(ContractError, match="^Invalid revision$"):
        replace(subject, revision=revision)


def test_bounds_and_invalid_combinations_raise_contract_errors(subject, success, check_request):
    with pytest.raises(ContractError):
        EvidenceBatch("ci", "collector", [success], complete=True)
    with pytest.raises(ContractError):
        EvidenceBatch("ci", "collector", (success,) * 1001, complete=True)
    with pytest.raises(ContractError):
        EvidenceBatch("ci", "collector", (success,), complete="true")
    with pytest.raises(ContractError):
        replace(success, state="in_progress")
    with pytest.raises(ContractError):
        evaluate_check(check_request, {}, assessment=None)
    with pytest.raises(ContractError):
        evaluate_check(check_request, EvidenceBatch("ci", "collector", (success,)), assessment={"verified": True})


def test_result_cannot_be_relabelled_to_hide_unverified_prerequisites(check_request, success):
    batch = EvidenceBatch("ci", "collector", (success,), complete=True)
    result = evaluate_check(check_request, batch, assessment=assessed(batch))
    for changes in (
        {"source_verification": "unverified"},
        {"completeness": "incomplete"},
        {"evidence_match": "unknown"},
        {"run_state": None},
        {"evidence_ids": ()},
        {"conclusion": "failure"},
        {"condition": "unverified"},
    ):
        with pytest.raises(ContractError):
            replace(result, **changes)
