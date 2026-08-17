from __future__ import annotations

from pathlib import Path

from evagix import __version__
from evagix.core.text import escape_github_command_value
from evagix.model import RepoFacts
from evagix.renderers import DEFAULT_TARGETS
from evagix.report_models import DoctorReport
from evagix.reports.locations import location_from_finding
from evagix.reports.pr_comment import render_doctor_pr_comment
from evagix.reports.sarif import render_doctor_sarif
from evagix.security.redaction import redact_sensitive_text
from evagix.utils import format_csv, stable_json
from evagix.validation.scoring import score_explanations

_escape_github_annotation = escape_github_command_value


def render_doctor_markdown(root: Path, facts: RepoFacts, report: DoctorReport) -> str:
    lines = [
        "# Evagix Readiness Report",
        "",
        f"- Repository: `{facts.root_name}`",
        f"- Static evidence score: `{report.score}/100`",
        f"- Static evidence tier: `{report.maturity_level}`",
        f"- Status: `{'pass' if report.ok else 'needs-attention'}`",
        "",
        "## Score Breakdown",
        "",
    ]
    for name, domain in report.domain_scores.items():
        lines.append(f"- `{name}`: `{domain.score}/100` ({domain.status})")
    lines.extend(["", "## Category Breakdown", ""])
    for name, category in report.categories.items():
        lines.append(f"- `{name}`: `{category.score}/100` ({category.status})")
    lines.extend(
        [
            "",
            "## Detected Context",
            "",
            f"- Languages: {format_csv(facts.languages)}",
            f"- Frameworks: {format_csv(facts.frameworks)}",
            f"- Backend tools: {format_csv(facts.backend_tools)}",
            f"- Frontend tools: {format_csv(facts.frontend_tools)}",
            f"- AI/Retrieval tools: {format_csv(facts.llm_tools)}",
            f"- ML/data tools: {format_csv(facts.ml_data_tools)}",
            f"- Dev tools: {format_csv(facts.dev_tools)}",
            f"- Runtimes: {format_csv(facts.runtimes)}",
            f"- CI platforms: {format_csv(facts.ci_platforms)}",
            f"- Infrastructure tools: {format_csv(facts.infrastructure_tools)}",
            f"- Container platforms: {format_csv(facts.container_platforms)}",
            f"- Databases: {format_csv(facts.databases)}",
            f"- Queues/caches: {format_csv(facts.queues)}",
            "",
            "## Common Commands",
            "",
        ]
    )
    if facts.commands:
        for name, command in facts.commands.items():
            evidence = facts.command_sources.get(name)
            detail = f" ({evidence.source}, {evidence.confidence})" if evidence else ""
            lines.append(f"- `{name}`: `{command}`{detail}")
    else:
        lines.append("- No commands detected.")
    lines.extend(["", "## Findings", ""])
    if report.findings:
        for item in report.findings:
            lines.append(f"- **{item.severity}** `{item.code}`: {item.message}")
    else:
        lines.append("- No issues found.")
    lines.extend(["", "## Evagix Targets", ""])
    for target in DEFAULT_TARGETS.values():
        state = "present" if (root / target).exists() else "missing"
        lines.append(f"- `{target}`: {state}")
    if facts.warnings:
        lines.extend(["", "## Scanner Warnings", ""])
        for warning in facts.warnings:
            lines.append(f"- {warning}")
    lines.append("")
    return redact_sensitive_text("\n".join(lines))


def render_doctor_json(facts: RepoFacts, report: DoctorReport, fail_under: int | None = None) -> str:
    return stable_json(
        {
            "schema_version": "1.0",
            "tool": "evagix",
            "tool_version": __version__,
            "repository": facts.root_name,
            "score": report.score,
            "maturity_level": report.maturity_level,
            "ok": report.ok and (fail_under is None or report.score >= fail_under),
            "fail_under": fail_under,
            "profiles": facts.active_profiles,
            "domains": {
                name: {"score": item.score, "status": item.status, "findings": item.findings}
                for name, item in report.domain_scores.items()
            },
            "categories": {
                name: {"score": item.score, "status": item.status, "findings": item.findings}
                for name, item in report.categories.items()
            },
            "score_explanations": score_explanations(report),
            "findings": [item.__dict__ for item in report.findings],
        }
    )


def render_sarif(root: Path, facts: RepoFacts, report: DoctorReport) -> str:
    return render_doctor_sarif(root, facts, report)


def render_github_annotations(report: DoctorReport) -> str:
    if not report.findings:
        return "::notice title=Evagix readiness::No readiness findings detected\n"
    lines = []
    for item in report.findings:
        level = {"info": "notice", "warning": "warning", "error": "error"}.get(item.severity, "notice")
        location = location_from_finding(item.code, item.message)
        message = _escape_github_annotation(f"{item.code}: {item.message}")
        lines.append(f"::{level} file={location.uri},line={location.start_line},title=Evagix readiness::{message}")
    return "\n".join(lines) + "\n"


def render_pr_comment(facts: RepoFacts, report: DoctorReport) -> str:
    return render_doctor_pr_comment(facts, report)
