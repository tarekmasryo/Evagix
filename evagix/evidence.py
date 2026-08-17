from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeAlias

from evagix.security.redaction import redact_for_output, redact_sensitive_text
from evagix.utils import resolve_output_path, stable_json, write_text

JsonLike: TypeAlias = Any
StringItems: TypeAlias = list[str] | tuple[str, ...]
IntItems: TypeAlias = list[int] | tuple[int, ...]
MetadataInput: TypeAlias = Mapping[str, JsonLike] | tuple[tuple[str, JsonLike], ...]


class FrozenDict(Mapping[str, JsonLike]):
    """Small immutable mapping for finding metadata."""

    def __init__(self, items: Mapping[str, JsonLike] | tuple[tuple[str, JsonLike], ...] | None = None) -> None:
        raw_items = dict(items or {}) if not isinstance(items, tuple) else dict(items)
        self._items = tuple(sorted((str(key), _freeze_value(value)) for key, value in raw_items.items()))
        self._dict = dict(self._items)

    def __getitem__(self, key: str) -> JsonLike:
        return self._dict[key]

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self._dict)

    def __len__(self) -> int:
        return len(self._dict)

    def __hash__(self) -> int:
        return hash(self._items)

    def to_dict(self) -> dict[str, JsonLike]:
        return {key: _unfreeze_value(value) for key, value in self._items}


def _freeze_value(value: JsonLike) -> JsonLike:
    if isinstance(value, FrozenDict):
        return value
    if isinstance(value, Mapping):
        return FrozenDict(value)
    if isinstance(value, list | tuple):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(sorted(_freeze_value(item) for item in value))
    return value


def _unfreeze_value(value: JsonLike) -> JsonLike:
    if isinstance(value, FrozenDict):
        return value.to_dict()
    if isinstance(value, tuple):
        return [_unfreeze_value(item) for item in value]
    return value


@dataclass(frozen=True)
class Finding:
    """Structured evidence finding shared by strict audits and JSON reports."""

    id: str
    title: str
    category: str
    severity: str
    status: str
    source: str = ""
    evidence: StringItems = field(default_factory=tuple)
    missing: StringItems = field(default_factory=tuple)
    risk: str = ""
    recommendation: str = ""
    source_file: str = ""
    source_line: int | None = None
    line_range: IntItems = field(default_factory=tuple)
    evidence_files: StringItems = field(default_factory=tuple)
    missing_evidence: StringItems = field(default_factory=tuple)
    confidence: str = "medium"
    root_cause: str = ""
    summary_only: bool = False
    metadata: MetadataInput = field(default_factory=FrozenDict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", redact_sensitive_text(self.title))
        object.__setattr__(self, "source", redact_sensitive_text(self.source))
        object.__setattr__(self, "risk", redact_sensitive_text(self.risk))
        object.__setattr__(self, "recommendation", redact_sensitive_text(self.recommendation))
        object.__setattr__(self, "source_file", redact_sensitive_text(self.source_file))
        object.__setattr__(self, "root_cause", redact_sensitive_text(self.root_cause))
        object.__setattr__(self, "evidence", tuple(redact_sensitive_text(item) for item in self.evidence))
        object.__setattr__(self, "missing", tuple(redact_sensitive_text(item) for item in self.missing))
        object.__setattr__(self, "line_range", tuple(self.line_range))
        object.__setattr__(self, "evidence_files", tuple(redact_sensitive_text(item) for item in self.evidence_files))
        object.__setattr__(
            self, "missing_evidence", tuple(redact_sensitive_text(item) for item in self.missing_evidence)
        )
        object.__setattr__(self, "metadata", FrozenDict(redact_for_output(dict(self.metadata))))

    def to_dict(self) -> dict[str, Any]:
        missing_evidence = list(self.missing_evidence or self.missing)
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "severity": self.severity,
            "status": self.status,
            "source": self.source,
            "evidence": list(self.evidence),
            "missing": list(self.missing),
            "risk": self.risk,
            "recommendation": self.recommendation,
            "source_file": self.source_file or self.source,
            "source_line": self.source_line,
            "line_range": list(self.line_range),
            "evidence_files": list(self.evidence_files),
            "missing_evidence": missing_evidence,
            "confidence": self.confidence,
            "root_cause": self.root_cause,
            "summary_only": self.summary_only,
            "metadata": self.metadata.to_dict() if isinstance(self.metadata, FrozenDict) else dict(self.metadata),
        }


def finding_to_doctor_message(finding: Finding) -> str:
    parts = [finding.title]
    source = finding.source_file or finding.source
    if source:
        if finding.source_line:
            parts.append(f"source: {source}:{finding.source_line}")
        else:
            parts.append(f"source: {source}")
    if finding.missing:
        parts.append("missing: " + ", ".join(finding.missing[:5]))
    if finding.confidence:
        parts.append("confidence: " + finding.confidence)
    if finding.risk:
        parts.append("risk: " + finding.risk)
    if finding.recommendation:
        parts.append("fix: " + finding.recommendation)
    return "; ".join(parts)


def evidence_summary(findings: list[Finding], claims: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    claim_items = claims or []
    claim_statuses = Counter(str(item.get("verdict") or item.get("status") or "unknown") for item in claim_items)
    finding_statuses = Counter(item.status for item in findings)
    severity_counts = Counter(item.severity for item in findings)
    return {
        "claims_checked": len(claim_items),
        "supported": claim_statuses.get("supported", 0),
        "partially_supported": claim_statuses.get("partially_supported", 0) + claim_statuses.get("partial", 0),
        "weak_evidence": claim_statuses.get("weak_evidence", 0),
        "unsupported": claim_statuses.get("unsupported", 0),
        "manual_review_required": claim_statuses.get("manual_review_required", 0),
        "waived": claim_statuses.get("waived", 0),
        "findings": len(findings),
        "high_or_critical_findings": severity_counts.get("high", 0) + severity_counts.get("critical", 0),
        "finding_statuses": dict(sorted(finding_statuses.items())),
        "severity_counts": dict(sorted(severity_counts.items())),
    }


def evidence_payload(
    repository: str,
    findings: list[Finding],
    *,
    claims: list[dict[str, Any]] | None = None,
    agent_context: list[dict[str, Any]] | None = None,
    commands: list[dict[str, Any]] | None = None,
    ecosystems: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    claims = claims or []
    return {
        "schema_version": "1.0",
        "tool": "evagix",
        "repository": repository,
        "summary": evidence_summary(findings, claims),
        "claims": claims,
        "agent_context": agent_context or [],
        "commands": commands or [],
        "ecosystems": ecosystems or [],
        "findings": [finding.to_dict() for finding in findings],
    }


def render_evidence_json(
    repository: str,
    findings: list[Finding],
    *,
    claims: list[dict[str, Any]] | None = None,
    agent_context: list[dict[str, Any]] | None = None,
    commands: list[dict[str, Any]] | None = None,
    ecosystems: list[dict[str, Any]] | None = None,
) -> str:
    return (
        stable_json(
            evidence_payload(
                repository,
                findings,
                claims=claims,
                agent_context=agent_context,
                commands=commands,
                ecosystems=ecosystems,
            )
        )
        + "\n"
    )


def render_evidence_payload(payload: dict[str, Any]) -> str:
    return stable_json(payload) + "\n"


def write_evidence_json(
    root: Path,
    repository: str,
    findings: list[Finding],
    relative_path: str = ".evagix/evidence.json",
    *,
    claims: list[dict[str, Any]] | None = None,
    agent_context: list[dict[str, Any]] | None = None,
    commands: list[dict[str, Any]] | None = None,
    ecosystems: list[dict[str, Any]] | None = None,
) -> Path:
    output_path = resolve_output_path(root, relative_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_text(
        output_path,
        render_evidence_json(
            repository, findings, claims=claims, agent_context=agent_context, commands=commands, ecosystems=ecosystems
        ),
    )
    return output_path
