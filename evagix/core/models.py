from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Severity = Literal["critical", "high", "medium", "low", "info"]
Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class CommandEvidence:
    """Evidence that a command is actually supported by repository files."""

    name: str
    command: str
    source_file: str = ""
    source_line: int | None = None
    confidence: Confidence = "medium"
    ecosystem: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScoreBreakdown:
    overall: int
    categories: dict[str, int] = field(default_factory=dict)
    blocking: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
