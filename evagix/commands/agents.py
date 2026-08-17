from __future__ import annotations

from pathlib import Path

from evagix.scanners.agent_files import (
    discover_agent_files,
    render_agent_discovery_markdown,
    render_agent_discovery_text,
)
from evagix.utils import stable_json


def run_agents(root: Path, *, output_format: str = "text") -> tuple[str, int]:
    facts = discover_agent_files(root)
    if output_format == "json":
        return stable_json(
            {"schema_version": "0.1-preview", "agent_files": [item.to_dict() for item in facts]}
        ) + "\n", 0
    if output_format == "markdown":
        return render_agent_discovery_markdown(facts), 0
    return render_agent_discovery_text(facts), 0
