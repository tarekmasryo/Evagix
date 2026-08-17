from __future__ import annotations

from pathlib import Path

from evagix.core.constants import PREVIEW_WARNING
from evagix.model import RepoFacts
from evagix.scanners.agent_files import discover_agent_files
from evagix.security.output import redacted_text_output


@redacted_text_output
def render_context_pack(root: Path, facts: RepoFacts) -> str:
    """Render a conservative, source-grounded context pack.

    This report is intentionally not a semantic task planner. Unknowns stay unknown.
    """
    agent_files = discover_agent_files(root)
    lines = [
        "# Evagix Context Pack",
        "",
        f"> {PREVIEW_WARNING} Source-grounded repository context only. Unknowns are not guessed.",
        "",
        "## Repository",
        "",
        f"- Name: `{facts.root_name}`",
        f"- Languages: {', '.join(facts.languages) if facts.languages else 'unknown'}",
        f"- Frameworks: {', '.join(facts.frameworks) if facts.frameworks else 'unknown'}",
        "",
        "## Detected Ecosystems",
        "",
    ]
    if facts.ecosystems:
        for ecosystem in facts.ecosystems:
            lines.append(
                f"- `{ecosystem.name}` at `{ecosystem.path}`; evidence: {', '.join(ecosystem.evidence) or 'unknown'}"
            )
    else:
        lines.append("- unknown")
    lines.extend(["", "## Commands", ""])
    if facts.commands:
        for name, command in sorted(facts.commands.items()):
            source = facts.command_sources.get(name)
            source_text = f" Source: `{source.path or source.source}`" if source else " Source: detected"
            lines.append(f"- `{name}`: `{command}`.{source_text}")
    else:
        lines.append("- unknown")
    lines.extend(["", "## Agent Context Files", ""])
    if agent_files:
        for item in agent_files:
            lines.append(f"- `{item.path}` ({item.tool})")
    else:
        lines.append("- none detected")
    lines.extend(["", "## Risk Zones", ""])
    if facts.risk_flags:
        for flag in facts.risk_flags:
            lines.append(f"- {flag}")
    else:
        lines.append("- unknown")
    lines.extend(
        [
            "",
            "## Source Policy",
            "",
            "- Evagix does not call LLM APIs.",
            "- Evagix does not upload code.",
            "- Evagix does not run project commands by default.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"
