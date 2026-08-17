from __future__ import annotations

from dataclasses import dataclass, field

from evagix.security.redaction import redact_sensitive_text


class _RedactedCodeMessage:
    code: str
    message: str

    def __post_init__(self) -> None:
        self.code = redact_sensitive_text(self.code)
        self.message = redact_sensitive_text(self.message)


@dataclass
class CheckResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_targets: list[str] = field(default_factory=list)
    stale_targets: list[str] = field(default_factory=list)
    tampered_targets: list[str] = field(default_factory=list)
    unmanaged_targets: list[str] = field(default_factory=list)
    truncated_targets: list[str] = field(default_factory=list)
    invalid_encoding_targets: list[str] = field(default_factory=list)


@dataclass
class DoctorFinding(_RedactedCodeMessage):
    severity: str
    code: str
    message: str
    penalty: int = 0


@dataclass
class CategoryScore:
    score: int
    status: str
    findings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.findings = [redact_sensitive_text(item) for item in self.findings]


@dataclass
class DoctorReport:
    score: int
    findings: list[DoctorFinding] = field(default_factory=list)
    categories: dict[str, CategoryScore] = field(default_factory=dict)
    domain_scores: dict[str, CategoryScore] = field(default_factory=dict)
    maturity_level: str = "unknown"

    @property
    def ok(self) -> bool:
        return self.score >= 80 and not any(item.severity == "error" for item in self.findings)


@dataclass
class AuditFinding(_RedactedCodeMessage):
    severity: str
    code: str
    message: str
