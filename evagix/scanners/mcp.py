from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from evagix.core.io import is_safe_repo_path

MCP_CONFIG_CANDIDATES = (
    "mcp.json",
    ".mcp.json",
    ".cursor/mcp.json",
    ".claude/mcp.json",
    ".vscode/mcp.json",
)


@dataclass(frozen=True)
class McpConfigFact:
    path: str
    message: str = "MCP config detected. Evagix does not audit MCP security yet. Review tool permissions manually."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def discover_mcp_configs(root: Path) -> list[McpConfigFact]:
    facts: list[McpConfigFact] = []
    for relative_path in MCP_CONFIG_CANDIDATES:
        path = root / relative_path
        if is_safe_repo_path(root, path) and path.is_file():
            facts.append(McpConfigFact(path=relative_path))
    return facts
