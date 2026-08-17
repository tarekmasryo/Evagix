from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextCheck:
    name: str
    status: str
    message: str


@dataclass(frozen=True)
class ContextEvaluation:
    score: int | None
    score_type: str
    management: str
    target_count: int
    present_targets: list[str]
    missing_targets: list[str]
    checks: list[ContextCheck]
    findings: list[dict[str, object]] | None = None

    @property
    def ok(self) -> bool:
        return self.score is not None and self.score >= 80 and not any(item.status == "fail" for item in self.checks)
