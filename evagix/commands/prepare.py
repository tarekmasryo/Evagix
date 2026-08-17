from __future__ import annotations

from pathlib import Path

from evagix.reports.context_pack import render_context_pack
from evagix.scanner import scan_repo
from evagix.scanners.agent_files import discover_agent_files
from evagix.scanners.mcp import discover_mcp_configs
from evagix.security.output import redacted_text_output

SAFE_EVAGIX_WRITES = (
    ".evagix/evidence.json",
    ".evagix/context-pack.md",
    ".evagix/risk-map.json",
)
PROTECTED_PROJECT_FILES = (
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".github/copilot-instructions.md",
)


@redacted_text_output
def render_prepare_plan(root: Path) -> str:
    facts = scan_repo(root)
    agent_files = discover_agent_files(root)
    mcp_configs = discover_mcp_configs(root)
    lines = [
        "Evagix Prepare Plan",
        "",
        "Experimental: plan only. This command does not modify project files.",
        "",
        "Will create/update only after an explicit future safe apply mode:",
    ]
    for path in SAFE_EVAGIX_WRITES:
        lines.append(f"- {path}")
    lines.extend(["", "Will not touch:"])
    for path in PROTECTED_PROJECT_FILES:
        lines.append(f"- {path}")
    lines.extend(["", "Detected agent context files:"])
    if agent_files:
        for agent_file in agent_files:
            lines.append(f"- {agent_file.path} ({agent_file.tool})")
    else:
        lines.append("- none")
    lines.extend(["", "MCP configs:"])
    if mcp_configs:
        for mcp_config in mcp_configs:
            lines.append(f"- {mcp_config.path}: {mcp_config.message}")
    else:
        lines.append("- none detected")
    lines.extend(["", "Context pack preview:", "", render_context_pack(root, facts).strip()])
    return "\n".join(lines).rstrip() + "\n"
