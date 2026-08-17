from __future__ import annotations

from dataclasses import dataclass, field

from evagix.evidence import Finding
from evagix.readme.source import README_MAX_CHARS, ReadmeStatus
from evagix.security.redaction import redact_sensitive_text


@dataclass(frozen=True)
class ReadmeClaim:
    claim: str
    phrase: str
    verdict: str
    evidence: list[str]
    missing_evidence: list[str]
    suggestion: str
    suggested_replacement: str = ""
    source: str = ""
    source_file: str = ""
    source_line: int | None = None
    line_range: list[int] | None = None
    confidence: str = "medium"

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim", redact_sensitive_text(self.claim))
        object.__setattr__(self, "phrase", redact_sensitive_text(self.phrase))
        object.__setattr__(self, "evidence", [redact_sensitive_text(item) for item in self.evidence])
        object.__setattr__(self, "missing_evidence", [redact_sensitive_text(item) for item in self.missing_evidence])
        object.__setattr__(self, "suggestion", redact_sensitive_text(self.suggestion))
        object.__setattr__(self, "suggested_replacement", redact_sensitive_text(self.suggested_replacement))
        object.__setattr__(self, "source", redact_sensitive_text(self.source))
        object.__setattr__(self, "source_file", redact_sensitive_text(self.source_file))
        object.__setattr__(self, "line_range", list(self.line_range) if self.line_range is not None else None)


@dataclass(frozen=True)
class ReadmeAuditReport:
    score: int
    claims: list[ReadmeClaim]
    readme_path: str = ""
    status: ReadmeStatus = ReadmeStatus.MISSING
    chars_read: int = 0
    max_chars: int = README_MAX_CHARS
    findings: list[Finding] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.status.is_complete

    @property
    def unsupported(self) -> list[ReadmeClaim]:
        return [item for item in self.claims if item.verdict == "unsupported"]

    @property
    def partial(self) -> list[ReadmeClaim]:
        return [
            item
            for item in self.claims
            if item.verdict in {"partial", "partially_supported", "weak_evidence", "manual_review_required"}
        ]

    @property
    def supported(self) -> list[ReadmeClaim]:
        return [item for item in self.claims if item.verdict == "supported"]

    @property
    def waived(self) -> list[ReadmeClaim]:
        return [item for item in self.claims if item.verdict == "waived"]
