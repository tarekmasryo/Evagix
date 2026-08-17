from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from evagix.config import CustomTarget
from evagix.context.eval_engine import evaluate_context
from evagix.model import RepoFacts
from evagix.security.output import redacted_text_output
from evagix.utils import stable_json


@redacted_text_output
def render_context_eval_markdown(
    root: Path,
    facts: RepoFacts,
    *,
    strict: bool = False,
    target_keys: list[str] | None = None,
    custom_targets: list[CustomTarget] | None = None,
) -> str:
    report = evaluate_context(root, facts, strict=strict, target_keys=target_keys, custom_targets=custom_targets)
    score_text = f"{report.score}/100" if report.score is not None else "N/A (unscored)"
    lines = [
        "# Evagix Quality Evaluation",
        "",
        f"- Repository: `{facts.root_name}`",
        f"- Static evidence score: `{score_text}`",
        f"- Score type: `{report.score_type}`",
        f"- Context management: `{report.management}`",
        f"- Present targets: `{report.target_count}`",
        "",
        "## Checks",
        "",
    ]
    for item in report.checks:
        lines.append(f"- **{item.status}** `{item.name}`: {item.message}")
    if report.findings:
        lines.extend(["", "## Findings", ""])
        for finding in report.findings:
            severity = finding.get("severity", "unknown")
            finding_id = finding.get("id", "context-finding")
            title = finding.get("title", "Context finding")
            lines.append(f"- **{severity}** `{finding_id}`: {title}")
    lines.extend(["", "## Missing targets", ""])
    if report.missing_targets:
        for target in report.missing_targets:
            lines.append(f"- `{target}`")
    else:
        lines.append("- None.")
    return "\n".join(lines).rstrip() + "\n"


def render_context_eval_json(
    root: Path,
    facts: RepoFacts,
    *,
    strict: bool = False,
    target_keys: list[str] | None = None,
    custom_targets: list[CustomTarget] | None = None,
) -> str:
    report = evaluate_context(root, facts, strict=strict, target_keys=target_keys, custom_targets=custom_targets)
    return (
        stable_json(
            {
                "schema_version": "1.0",
                "tool": "evagix",
                "repository": facts.root_name,
                "evaluation": {
                    "score": report.score,
                    "score_type": report.score_type,
                    "management": report.management,
                    "ok": report.ok,
                    "target_count": report.target_count,
                    "present_targets": report.present_targets,
                    "missing_targets": report.missing_targets,
                    "checks": [asdict(item) for item in report.checks],
                    "findings": report.findings or [],
                },
            }
        )
        + "\n"
    )
