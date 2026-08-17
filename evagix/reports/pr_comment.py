from __future__ import annotations

from evagix.model import RepoFacts
from evagix.report_models import CategoryScore, DoctorReport


def render_doctor_pr_comment(facts: RepoFacts, report: DoctorReport) -> str:
    status = "PASS" if report.ok else "NEEDS ATTENTION"
    repository = report.domain_scores.get("repository_readiness", CategoryScore(100, "pass"))
    context = report.domain_scores.get("agent_context_governance", CategoryScore(100, "pass"))
    pr_risk = report.domain_scores.get("pr_risk_readiness", CategoryScore(100, "pass"))
    lines = [
        "## Evagix Check",
        "",
        f"**Status:** `{status}`  ",
        f"**Static evidence score:** `{report.score}/100`  ",
        f"**Repository readiness:** `{repository.score}/100`  ",
        f"**Agent context governance:** `{context.score}/100`  ",
        f"**PR risk readiness:** `{pr_risk.score}/100`  ",
        f"**Repository:** `{facts.root_name}`",
        "",
    ]
    if facts.active_profiles:
        lines.append(f"**Profiles:** {', '.join(f'`{item}`' for item in facts.active_profiles)}")
        lines.append("")
    if report.findings:
        lines.append("### Findings")
        for item in report.findings[:20]:
            lines.append(f"- **{item.severity}** `{item.code}`: {item.message}")
    else:
        lines.append("No findings. Generated Evagix context looks current.")
    lines.append("")
    return "\n".join(lines)
