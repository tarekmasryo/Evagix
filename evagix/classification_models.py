from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProjectTypeMatch:
    """Evidence-backed project type or capability match."""

    name: str
    label: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProjectClassification:
    """Primary project shape plus secondary capabilities inferred from repository evidence."""

    primary: ProjectTypeMatch | None
    secondary: list[ProjectTypeMatch] = field(default_factory=list)
    detected_signals: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
