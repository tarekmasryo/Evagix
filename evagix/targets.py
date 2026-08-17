from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TargetAdapter:
    """A supported context export target."""

    name: str
    path: str
    label: str
    description: str
    renderer: str
    default_enabled: bool = True
    category: str = "context-export"


TARGET_ADAPTERS: dict[str, TargetAdapter] = {
    "universal_md": TargetAdapter(
        name="universal_md",
        path=".evagix/context.md",
        label="Universal Context Markdown",
        description="Portable evidence-backed repository context for any AI coding agent, model, or reviewer workflow.",
        renderer="universal_md",
        category="universal-context",
    ),
    "universal_json": TargetAdapter(
        name="universal_json",
        path=".evagix/context.json",
        label="Universal Context JSON",
        description="Machine-readable repository facts, commands, risks, and policies for custom agents and integrations.",
        renderer="universal_json",
        category="universal-context",
    ),
    "agent_brief": TargetAdapter(
        name="agent_brief",
        path=".evagix/agent-brief.md",
        label="Agent Brief",
        description="Compact task-start brief for any model or coding assistant.",
        renderer="agent_brief",
        default_enabled=False,
        category="universal-context",
    ),
    "safety_policy": TargetAdapter(
        name="safety_policy",
        path=".evagix/safety-policy.md",
        label="Safety Policy",
        description="Portable safety and forbidden-action policy for AI-assisted repository work.",
        renderer="safety_policy",
        default_enabled=False,
        category="universal-context",
    ),
    "repo_map": TargetAdapter(
        name="repo_map",
        path=".evagix/repo-map.md",
        label="Repository Map",
        description="Portable repository map, entrypoints, commands, subprojects, and important configs.",
        renderer="repo_map",
        default_enabled=False,
        category="universal-context",
    ),
    "agent_tasks": TargetAdapter(
        name="agent_tasks",
        path=".agent_tasks/README.md",
        label="Agent Task Templates",
        description="Optional task templates with allowed files, forbidden files, validation commands, stop conditions, and human review triggers.",
        renderer="agent_tasks",
        default_enabled=False,
        category="universal-context",
    ),
    "agents": TargetAdapter(
        name="agents",
        path="AGENTS.md",
        label="AGENTS.md",
        description="Compatibility export for OpenAI Codex and other AI coding agents that support the AGENTS.md convention.",
        renderer="agents",
        default_enabled=False,
        category="tool-adapter",
    ),
    "claude": TargetAdapter(
        name="claude",
        path="CLAUDE.md",
        label="Claude Code",
        description="Tool-specific adapter for Claude Code.",
        renderer="claude",
        default_enabled=False,
        category="tool-adapter",
    ),
    "gemini": TargetAdapter(
        name="gemini",
        path="GEMINI.md",
        label="Gemini CLI",
        description="Tool-specific adapter for Gemini CLI workflows.",
        renderer="gemini",
        default_enabled=False,
        category="tool-adapter",
    ),
    "cursor": TargetAdapter(
        name="cursor",
        path=".cursor/rules/project.mdc",
        label="Cursor Project Rule",
        description="Tool-specific adapter for Cursor rules.",
        renderer="cursor",
        default_enabled=False,
        category="tool-adapter",
    ),
    "copilot": TargetAdapter(
        name="copilot",
        path=".github/copilot-instructions.md",
        label="GitHub Copilot Instructions",
        description="Tool-specific adapter for GitHub Copilot repository instructions.",
        renderer="copilot",
        default_enabled=False,
        category="tool-adapter",
    ),
    "windsurf": TargetAdapter(
        name="windsurf",
        path=".windsurf/rules/evagix.md",
        label="Windsurf Rule",
        description="Tool-specific adapter for Windsurf repository rules.",
        renderer="windsurf",
        default_enabled=False,
        category="tool-adapter",
    ),
    "continue": TargetAdapter(
        name="continue",
        path=".continue/rules/evagix.md",
        label="Continue Rule",
        description="Optional Continue.dev adapter for local AI coding workflows.",
        renderer="continue",
        default_enabled=False,
        category="tool-adapter",
    ),
    "cline": TargetAdapter(
        name="cline",
        path=".clinerules",
        label="Cline Rules",
        description="Optional adapter for Cline project-specific rules.",
        renderer="cline",
        default_enabled=False,
        category="tool-adapter",
    ),
    "roo": TargetAdapter(
        name="roo",
        path=".roo/rules/evagix.md",
        label="Roo Code Rules",
        description="Optional adapter for Roo Code custom project rules.",
        renderer="roo",
        default_enabled=False,
        category="tool-adapter",
    ),
    "aider": TargetAdapter(
        name="aider",
        path="CONVENTIONS.md",
        label="Aider Conventions",
        description="Optional adapter for Aider conventions loaded with /read CONVENTIONS.md.",
        renderer="aider",
        default_enabled=False,
        category="tool-adapter",
    ),
    "openhands": TargetAdapter(
        name="openhands",
        path=".openhands/skills/repository/SKILL.md",
        label="OpenHands Repository Skill",
        description="Optional OpenHands repository skill for project-specific AI coding guidance.",
        renderer="openhands",
        default_enabled=False,
        category="tool-adapter",
    ),
    "generic": TargetAdapter(
        name="generic",
        path="GENERIC_EVAGIX.md",
        label="Generic Evagix",
        description="Optional root-level portable context file for custom agents and local LLM workflows.",
        renderer="generic",
        default_enabled=False,
        category="tool-adapter",
    ),
}

DEFAULT_TARGET_KEYS: tuple[str, ...] = tuple(
    name for name, adapter in TARGET_ADAPTERS.items() if adapter.default_enabled
)
ALL_TARGET_KEYS: tuple[str, ...] = tuple(TARGET_ADAPTERS)


def target_paths(*, default_only: bool = False) -> dict[str, str]:
    names = DEFAULT_TARGET_KEYS if default_only else ALL_TARGET_KEYS
    return {name: TARGET_ADAPTERS[name].path for name in names}


def target_adapter(name: str) -> TargetAdapter:
    return TARGET_ADAPTERS[name]


def supported_target_names() -> str:
    return ", ".join(f"{name}={adapter.path}" for name, adapter in TARGET_ADAPTERS.items())


def target_list_rows() -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for name, adapter in TARGET_ADAPTERS.items():
        status = "default" if adapter.default_enabled else "optional"
        rows.append((name, adapter.path, status, adapter.description))
    return rows
