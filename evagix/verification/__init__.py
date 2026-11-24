"""Preview contracts for explicit check evidence; no CLI or collection adapters."""

from evagix.verification.checks import evaluate_check
from evagix.verification.contracts import (
    CheckRequest,
    CheckResult,
    CheckSubject,
    ContractError,
    EvidenceBatch,
    RunEvidence,
    SourceAssessment,
    parse_batch,
    parse_request,
)

__all__ = [
    "CheckRequest",
    "CheckResult",
    "CheckSubject",
    "ContractError",
    "EvidenceBatch",
    "RunEvidence",
    "SourceAssessment",
    "evaluate_check",
    "parse_batch",
    "parse_request",
]
