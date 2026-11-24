"""Deterministic evaluation of one explicitly selected check result."""

from __future__ import annotations

from evagix.verification.contracts import (
    CheckRequest,
    CheckResult,
    Condition,
    ContractError,
    EvidenceBatch,
    EvidenceMatch,
    Reason,
    RunEvidence,
    SourceAssessment,
    SourceVerification,
)


def _select(
    request: CheckRequest, batch: EvidenceBatch
) -> tuple[EvidenceMatch, Reason | None, tuple[RunEvidence, ...]]:
    if not batch.records:
        return "unknown", "no_evidence", ()
    matching = tuple(record for record in batch.records if record.subject == request.subject)
    if not matching:
        return "mismatch", "subject_mismatch", ()
    run = tuple(record for record in matching if record.run_id == request.run_id)
    if not run:
        return "mismatch", "run_mismatch", ()
    if any(record.attempt > request.attempt for record in run):
        return "unknown", "inconsistent_attempt_inventory", run
    selected = tuple(record for record in run if record.attempt == request.attempt)
    if not selected:
        return "mismatch", "attempt_mismatch", ()
    if len({(record.state, record.conclusion) for record in selected}) != 1:
        return "unknown", "conflicting_results", selected
    return "match", None, selected


def evaluate_check(
    request: CheckRequest,
    batch: EvidenceBatch,
    *,
    assessment: SourceAssessment | None = None,
) -> CheckResult:
    """Evaluate supplied facts and a caller assessment, without authenticating them."""
    if not isinstance(request, CheckRequest) or not isinstance(batch, EvidenceBatch):
        raise ContractError("Invalid evaluation input")
    if assessment is not None and not isinstance(assessment, SourceAssessment):
        raise ContractError("Invalid source assessment")
    digest = batch.digest()
    source: SourceVerification = "unverified"
    if assessment is not None:
        if assessment.batch_digest != digest:
            source = "binding_mismatch"
        elif assessment.verification == "verified":
            source = "caller_verified"
    match, selection_reason, selected = _select(request, batch)
    record = selected[0] if match == "match" else None
    condition: Condition = "unverified"
    reason: Reason
    if source == "binding_mismatch":
        reason = "source_binding_mismatch"
    elif source != "caller_verified":
        reason = "source_unverified"
    elif not batch.complete:
        reason = "incomplete_inventory"
    elif selection_reason is not None:
        reason = selection_reason
    elif record is None:
        raise ContractError("Selected evidence unavailable")
    elif record.state != "completed":
        reason = "run_not_completed"
    elif record.conclusion is None:
        reason = "conclusion_missing"
    elif record.conclusion == "success":
        condition, reason = "supported", "check_succeeded"
    elif record.conclusion == "failure":
        condition, reason = "contradicted", "check_failed"
    else:
        reason = "non_success_conclusion"
    return CheckResult(
        request=request,
        source_kind=batch.source_kind,
        source_id=batch.source_id,
        batch_digest=digest,
        verifier=assessment.verifier if assessment is not None else None,
        condition=condition,
        source_verification=source,
        completeness="complete" if batch.complete else "incomplete",
        evidence_match=match,
        run_state=record.state if record is not None else None,
        conclusion=record.conclusion if record is not None else None,
        reason=reason,
        evidence_ids=tuple(sorted({item.record_id for item in selected})),
    )
