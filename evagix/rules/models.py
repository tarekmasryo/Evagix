from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

Severity = Literal["critical", "high", "medium", "low", "info"]
Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class RuleDefinition:
    id: str
    title: str
    category: str
    severity: Severity
    confidence: Confidence
    description: str
    remediation: str
    can_fail_ci: bool = True
    docs_anchor: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuleAlias:
    old_id: str
    new_id: str
    deprecated: bool = True
    note: str = "Legacy compatibility alias retained for v0.1.x outputs."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
