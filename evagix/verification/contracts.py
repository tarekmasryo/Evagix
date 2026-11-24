"""Strict data boundaries for the preview check-verification contract."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

from evagix.security.redaction import redact_for_output

SubjectKind = Literal["commit", "test_merge"]
SourceKind = Literal["ci", "local"]
RunState = Literal["queued", "in_progress", "completed", "cancelled"]
Conclusion = Literal["success", "failure", "skipped", "neutral", "cancelled", "timed_out"]
Condition = Literal["supported", "contradicted", "unverified"]
SourceVerification = Literal["caller_verified", "unverified", "binding_mismatch"]
Completeness = Literal["complete", "incomplete"]
EvidenceMatch = Literal["match", "mismatch", "unknown"]
Reason = Literal[
    "source_binding_mismatch",
    "source_unverified",
    "incomplete_inventory",
    "no_evidence",
    "subject_mismatch",
    "run_mismatch",
    "inconsistent_attempt_inventory",
    "attempt_mismatch",
    "conflicting_results",
    "run_not_completed",
    "conclusion_missing",
    "check_succeeded",
    "check_failed",
    "non_success_conclusion",
]

MAX_RECORDS = 1000
MAX_ATTEMPT = 9_007_199_254_740_991
_STATES = {"queued", "in_progress", "completed", "cancelled"}
_CONCLUSIONS = {"success", "failure", "skipped", "neutral", "cancelled", "timed_out"}
_REASONS = {
    "source_binding_mismatch",
    "source_unverified",
    "incomplete_inventory",
    "no_evidence",
    "subject_mismatch",
    "run_mismatch",
    "inconsistent_attempt_inventory",
    "attempt_mismatch",
    "conflicting_results",
    "run_not_completed",
    "conclusion_missing",
    "check_succeeded",
    "check_failed",
    "non_success_conclusion",
}


class ContractError(ValueError):
    """An invalid contract input; messages never include supplied field values."""


def _text(value: object, field: str) -> None:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 256
        or value != value.strip()
        or any(unicodedata.category(char) in {"Cc", "Cs", "Zl", "Zp"} for char in value)
    ):
        raise ContractError(f"Invalid {field}")


def _choice(value: object, options: set[str], field: str) -> None:
    if type(value) is not str or value not in options:
        raise ContractError(f"Invalid {field}")


def _attempt(value: object) -> None:
    if type(value) is not int or not 1 <= value <= MAX_ATTEMPT:
        raise ContractError("Invalid attempt")


def _digest(value: object) -> None:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ContractError("Invalid batch_digest")


def _canonical(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )


@dataclass(frozen=True, repr=False)
class CheckSubject:
    repository: str
    revision: str
    subject_kind: SubjectKind
    workflow: str
    job: str

    def __post_init__(self) -> None:
        for name in ("repository", "workflow", "job"):
            _text(getattr(self, name), name)
        if type(self.revision) is not str or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", self.revision) is None:
            raise ContractError("Invalid revision")
        _choice(self.subject_kind, {"commit", "test_merge"}, "subject_kind")

    def _payload(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "revision": self.revision,
            "subject_kind": self.subject_kind,
            "workflow": self.workflow,
            "job": self.job,
        }


@dataclass(frozen=True, repr=False)
class CheckRequest:
    subject: CheckSubject
    run_id: str
    attempt: int

    def __post_init__(self) -> None:
        if not isinstance(self.subject, CheckSubject):
            raise ContractError("Invalid subject")
        _text(self.run_id, "run_id")
        _attempt(self.attempt)

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "kind": "check_succeeded",
            "subject": self.subject._payload(),
            "run_id": self.run_id,
            "attempt": self.attempt,
        }


@dataclass(frozen=True, repr=False)
class RunEvidence:
    record_id: str
    subject: CheckSubject
    run_id: str
    attempt: int
    state: RunState
    conclusion: Conclusion | None = None

    def __post_init__(self) -> None:
        _text(self.record_id, "record_id")
        CheckRequest(self.subject, self.run_id, self.attempt)
        _choice(self.state, _STATES, "state")
        if self.conclusion is not None:
            _choice(self.conclusion, _CONCLUSIONS, "conclusion")
            if self.state != "completed":
                raise ContractError("Only completed records may have a conclusion")

    def _payload(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "subject": self.subject._payload(),
            "run_id": self.run_id,
            "attempt": self.attempt,
            "state": self.state,
            "conclusion": self.conclusion,
        }


@dataclass(frozen=True, repr=False)
class EvidenceBatch:
    source_kind: SourceKind
    source_id: str
    records: tuple[RunEvidence, ...]
    complete: bool = False

    def __post_init__(self) -> None:
        _choice(self.source_kind, {"ci", "local"}, "source_kind")
        _text(self.source_id, "source_id")
        if type(self.complete) is not bool:
            raise ContractError("Invalid complete")
        if type(self.records) is not tuple or len(self.records) > MAX_RECORDS:
            raise ContractError("Invalid records")
        if not all(isinstance(record, RunEvidence) for record in self.records):
            raise ContractError("Invalid record")

    def digest(self) -> str:
        """Bind the complete batch, including metadata; this does not authenticate it."""
        records = sorted((record._payload() for record in self.records), key=_canonical)
        payload = {
            "schema_version": "1.0",
            "kind": "check_evidence",
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "complete": self.complete,
            "records": records,
        }
        return hashlib.sha256(b"evagix.check-evidence.v1\0" + _canonical(payload)).hexdigest()


@dataclass(frozen=True, repr=False)
class SourceAssessment:
    """Trusted-caller input, never inferred from or parsed out of evidence JSON."""

    batch_digest: str
    verification: Literal["verified", "unverified"]
    verifier: str

    def __post_init__(self) -> None:
        _digest(self.batch_digest)
        _choice(self.verification, {"verified", "unverified"}, "verification")
        _text(self.verifier, "verifier")


@dataclass(frozen=True, repr=False)
class CheckResult:
    request: CheckRequest
    source_kind: SourceKind
    source_id: str
    batch_digest: str
    verifier: str | None
    condition: Condition
    source_verification: SourceVerification
    completeness: Completeness
    evidence_match: EvidenceMatch
    run_state: RunState | None
    conclusion: Conclusion | None
    reason: Reason
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.request, CheckRequest):
            raise ContractError("Invalid request")
        _choice(self.source_kind, {"ci", "local"}, "source_kind")
        _text(self.source_id, "source_id")
        _digest(self.batch_digest)
        if self.verifier is not None:
            _text(self.verifier, "verifier")
        _choice(self.condition, {"supported", "contradicted", "unverified"}, "condition")
        _choice(self.source_verification, {"caller_verified", "unverified", "binding_mismatch"}, "source_verification")
        _choice(self.completeness, {"complete", "incomplete"}, "completeness")
        _choice(self.evidence_match, {"match", "mismatch", "unknown"}, "evidence_match")
        _choice(self.reason, _REASONS, "reason")
        if self.run_state is not None:
            _choice(self.run_state, _STATES, "run_state")
        if self.conclusion is not None:
            _choice(self.conclusion, _CONCLUSIONS, "conclusion")
            if self.run_state != "completed":
                raise ContractError("Invalid result conclusion")
        if type(self.evidence_ids) is not tuple or len(self.evidence_ids) > MAX_RECORDS:
            raise ContractError("Invalid evidence_ids")
        for identifier in self.evidence_ids:
            _text(identifier, "evidence_id")
        if self.source_verification != "unverified" and self.verifier is None:
            raise ContractError("Source verification requires a verifier")
        if self.condition != "unverified":
            expected = ("success", "check_succeeded") if self.condition == "supported" else ("failure", "check_failed")
            if (
                self.source_verification != "caller_verified"
                or self.completeness != "complete"
                or self.evidence_match != "match"
                or self.run_state != "completed"
                or (self.conclusion, self.reason) != expected
                or not self.evidence_ids
            ):
                raise ContractError("Invalid decisive result")
        elif self.reason in {"check_succeeded", "check_failed"}:
            raise ContractError("Invalid unverified result")

    def to_dict(self) -> dict[str, Any]:
        """Return a redacted display artifact, not replayable evidence."""
        payload = {
            "schema_version": "1.0",
            "kind": "check_verification",
            "request": self.request._payload(),
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "batch_digest": self.batch_digest,
            "verifier": self.verifier,
            "condition": self.condition,
            "source_verification": self.source_verification,
            "completeness": self.completeness,
            "evidence_match": self.evidence_match,
            "run_state": self.run_state,
            "conclusion": self.conclusion,
            "reason": self.reason,
            "evidence_ids": list(self.evidence_ids),
            "engine_status": "completed",
            "policy_decision": "not_evaluated",
        }
        return dict(redact_for_output(payload))


def _object(value: object, keys: set[str], field: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ContractError(f"Invalid {field} fields")
    return value


def _subject(value: object) -> CheckSubject:
    data = _object(value, {"repository", "revision", "subject_kind", "workflow", "job"}, "subject")
    return CheckSubject(**data)


def parse_request(payload: object) -> CheckRequest:
    data = _object(payload, {"schema_version", "kind", "subject", "run_id", "attempt"}, "request")
    _choice(data["schema_version"], {"1.0"}, "schema_version")
    _choice(data["kind"], {"check_succeeded"}, "kind")
    return CheckRequest(_subject(data["subject"]), data["run_id"], data["attempt"])


def parse_batch(payload: object) -> EvidenceBatch:
    data = _object(payload, {"schema_version", "kind", "source_kind", "source_id", "complete", "records"}, "batch")
    _choice(data["schema_version"], {"1.0"}, "schema_version")
    _choice(data["kind"], {"check_evidence"}, "kind")
    if type(data["records"]) is not list or len(data["records"]) > MAX_RECORDS:
        raise ContractError("Invalid records")
    records = []
    for item in data["records"]:
        record = _object(item, {"record_id", "subject", "run_id", "attempt", "state", "conclusion"}, "record")
        records.append(
            RunEvidence(
                record["record_id"],
                _subject(record["subject"]),
                record["run_id"],
                record["attempt"],
                record["state"],
                record["conclusion"],
            )
        )
    return EvidenceBatch(data["source_kind"], data["source_id"], tuple(records), data["complete"])
