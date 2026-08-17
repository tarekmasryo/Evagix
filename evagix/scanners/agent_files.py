from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from evagix.agent_context_registry import iter_agent_context_paths
from evagix.core.constants import PREVIEW_WARNING
from evagix.scanner_utils import TraversalDiagnostics
from evagix.security.output import redacted_text_output

MAX_AGENT_CONTEXT_FILES = 200


@dataclass(frozen=True)
class AgentFileFact:
    path: str
    tool: str
    status: str = "detected"
    confidence: str = "medium"
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentDiscoveryResult:
    facts: tuple[AgentFileFact, ...]
    diagnostics: TraversalDiagnostics


def discover_agent_files_with_diagnostics(root: Path) -> AgentDiscoveryResult:
    """Detect supported agent-context files with bounded traversal diagnostics."""

    diagnostics = TraversalDiagnostics()
    facts: list[AgentFileFact] = []
    for path, source in iter_agent_context_paths(root, limit=MAX_AGENT_CONTEXT_FILES, diagnostics=diagnostics):
        relative = path.relative_to(root).as_posix()
        facts.append(
            AgentFileFact(
                path=relative,
                tool=source.tool,
                confidence=source.confidence,
                notes=(),
            )
        )
    return AgentDiscoveryResult(tuple(sorted(facts, key=lambda item: item.path)), diagnostics)


def discover_agent_files(root: Path) -> list[AgentFileFact]:
    """Detect common agent-context files without claiming deep compatibility."""

    return list(discover_agent_files_with_diagnostics(root).facts)


@redacted_text_output
def render_agent_discovery_text(facts: list[AgentFileFact]) -> str:
    lines = [
        "Evagix Agent Context Discovery",
        "",
        f"Preview: discovery only. {PREVIEW_WARNING}",
        "",
    ]
    if not facts:
        lines.append("No common agent-context files were detected.")
        return "\n".join(lines).rstrip() + "\n"
    lines.append("Detected agent context files:")
    for fact in facts:
        suffix = f"  {fact.tool}" if fact.tool else ""
        lines.append(f"- {fact.path}{suffix}")
    return "\n".join(lines).rstrip() + "\n"


@redacted_text_output
def render_agent_discovery_markdown(facts: list[AgentFileFact]) -> str:
    lines = [
        "# Evagix Agent Context Discovery",
        "",
        f"> Preview: discovery only. {PREVIEW_WARNING}",
        "",
    ]
    if not facts:
        lines.append("No common agent-context files were detected.")
        return "\n".join(lines).rstrip() + "\n"
    lines.extend(["| File | Tool | Confidence |", "| --- | --- | --- |"])
    for fact in facts:
        lines.append(f"| `{fact.path}` | {fact.tool} | {fact.confidence} |")
    return "\n".join(lines).rstrip() + "\n"
