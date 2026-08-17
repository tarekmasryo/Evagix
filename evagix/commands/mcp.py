from __future__ import annotations

from pathlib import Path

from evagix.core.constants import EXPERIMENTAL_WARNING
from evagix.scanners.mcp import discover_mcp_configs
from evagix.utils import stable_json


def run_mcp(root: Path, *, output_format: str = "text") -> tuple[str, int]:
    configs = discover_mcp_configs(root)
    if output_format == "json":
        return stable_json(
            {"schema_version": "0.1-experimental", "mcp_configs": [item.to_dict() for item in configs]}
        ) + "\n", 0
    lines = [
        "Evagix MCP Config Detection",
        "",
        f"Experimental: detection only. {EXPERIMENTAL_WARNING} Evagix does not audit MCP security yet.",
        "",
    ]
    if not configs:
        lines.append("No common MCP config files were detected.")
    else:
        for item in configs:
            lines.append(f"- {item.path}: {item.message}")
    return "\n".join(lines).rstrip() + "\n", 0
