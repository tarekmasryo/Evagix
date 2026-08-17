from __future__ import annotations

from evagix.core.models import ScoreBreakdown
from evagix.evidence import Finding
from evagix.scoring.weights import STRICT_SEVERITY_WEIGHTS

DEFAULT_WEIGHTS = dict(STRICT_SEVERITY_WEIGHTS)


def score_from_findings(findings: list[Finding], *, floor: int = 0) -> ScoreBreakdown:
    penalty = 0
    categories: dict[str, int] = {}
    for finding in findings:
        finding_penalty = DEFAULT_WEIGHTS.get(finding.severity, 3)
        if finding.summary_only:
            finding_penalty = 0
        penalty += finding_penalty
        categories[finding.category] = categories.get(finding.category, 100) - finding_penalty
    overall = max(floor, min(100, 100 - penalty))
    normalized_categories = {name: max(0, min(100, value)) for name, value in categories.items()}
    return ScoreBreakdown(
        overall=overall,
        categories=normalized_categories,
        blocking=any(item.severity == "critical" for item in findings),
    )
