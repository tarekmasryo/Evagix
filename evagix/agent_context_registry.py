from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from evagix.scanner_utils import TraversalDiagnostics, _iter_repo_files, is_safe_repo_path
from evagix.targets import TARGET_ADAPTERS

AGENT_CONTEXT_SUFFIXES = frozenset({".md", ".mdc", ".txt", ".toml", ".json", ".yml", ".yaml"})


@dataclass(frozen=True)
class AgentContextSource:
    """One supported agent-context file or directory family."""

    path: str
    tool: str
    kind: str = "file"
    confidence: str = "high"


_STATIC_FILE_SOURCES: tuple[AgentContextSource, ...] = (
    AgentContextSource("AGENTS.override.md", "generic agents override"),
    AgentContextSource(".claude/CLAUDE.md", "Claude Code"),
    AgentContextSource(".cursorrules", "Cursor"),
    AgentContextSource(".windsurfrules", "Windsurf"),
)


_TOOL_OVERRIDES = {
    "AGENTS.md": "OpenAI Codex / AGENTS.md-compatible agents",
    "CLAUDE.md": "Claude Code",
    "GEMINI.md": "Gemini CLI",
    ".github/copilot-instructions.md": "GitHub Copilot",
    ".cursor/rules/project.mdc": "Cursor",
    ".windsurf/rules/evagix.md": "Windsurf",
    ".continue/rules/evagix.md": "Continue",
    ".clinerules": "Cline",
    ".roo/rules/evagix.md": "Roo Code",
    "CONVENTIONS.md": "generic conventions",
    ".openhands/skills/repository/SKILL.md": "OpenHands",
}

_DIRECTORY_SOURCES: tuple[AgentContextSource, ...] = (
    AgentContextSource(".claude/rules", "Claude Code", kind="directory", confidence="medium"),
    AgentContextSource(".github/instructions", "GitHub Copilot", kind="directory", confidence="medium"),
    AgentContextSource(".cursor/rules", "Cursor", kind="directory", confidence="medium"),
    AgentContextSource(".windsurf/rules", "Windsurf", kind="directory", confidence="medium"),
    AgentContextSource(".continue/rules", "Continue", kind="directory", confidence="medium"),
    AgentContextSource(".roo/rules", "Roo Code", kind="directory", confidence="medium"),
    AgentContextSource(".openhands/microagents", "OpenHands", kind="directory", confidence="medium"),
    AgentContextSource(".openhands/skills", "OpenHands", kind="directory", confidence="medium"),
)


def agent_context_file_sources() -> tuple[AgentContextSource, ...]:
    """Return the canonical exact-path agent-context registry."""

    target_sources = tuple(
        AgentContextSource(adapter.path, _TOOL_OVERRIDES.get(adapter.path, adapter.label))
        for adapter in TARGET_ADAPTERS.values()
        if adapter.category == "tool-adapter"
    )
    by_path = {source.path: source for source in (*target_sources, *_STATIC_FILE_SOURCES)}
    return tuple(by_path[path] for path in sorted(by_path))


def agent_context_directory_sources() -> tuple[AgentContextSource, ...]:
    return _DIRECTORY_SOURCES


def agent_context_exact_paths() -> frozenset[str]:
    return frozenset(source.path for source in agent_context_file_sources())


def generated_agent_target_paths() -> tuple[str, ...]:
    return tuple(
        sorted(
            adapter.path
            for adapter in TARGET_ADAPTERS.values()
            if adapter.category in {"tool-adapter", "universal-context"}
        )
    )


def declared_agent_context_paths(root: Path) -> tuple[Path, ...]:
    """Return every exact file, generated target, and directory trust boundary."""

    relative_paths = {source.path for source in agent_context_file_sources()}
    relative_paths.update(source.path for source in agent_context_directory_sources())
    relative_paths.update(generated_agent_target_paths())
    return tuple(root / relative for relative in sorted(relative_paths))


def unsafe_declared_agent_context_paths(root: Path) -> tuple[Path, ...]:
    """Return declared context boundaries that escape through a symlink."""

    unsafe: list[Path] = []
    for path in declared_agent_context_paths(root):
        try:
            if (path.exists() or path.is_symlink()) and not is_safe_repo_path(root, path):
                unsafe.append(path)
        except OSError:
            continue
    return tuple(unsafe)


def iter_agent_context_paths(
    root: Path,
    *,
    limit: int = 200,
    diagnostics: TraversalDiagnostics | None = None,
) -> list[tuple[Path, AgentContextSource]]:
    """Discover every supported agent-context path through one bounded registry."""

    state = diagnostics or TraversalDiagnostics()
    results: list[tuple[Path, AgentContextSource]] = []
    seen: set[str] = set()

    for source in agent_context_file_sources():
        path = root / source.path
        try:
            if path.is_file() and is_safe_repo_path(root, path):
                key = path.relative_to(root).as_posix()
                if key not in seen:
                    if len(results) >= limit:
                        state.result_limit_reached = True
                        return results
                    seen.add(key)
                    results.append((path, source))
        except OSError:
            state.read_errors += 1
            continue

    for source in agent_context_directory_sources():
        directory = root / source.path
        try:
            if not directory.is_dir() or not is_safe_repo_path(root, directory):
                continue
        except OSError:
            state.read_errors += 1
            continue
        for path in _iter_repo_files(
            root,
            start=directory,
            allow_skipped_start=True,
            diagnostics=state,
        ):
            if path.suffix.lower() not in AGENT_CONTEXT_SUFFIXES:
                continue
            key = path.relative_to(root).as_posix()
            if key in seen:
                continue
            if len(results) >= limit:
                state.result_limit_reached = True
                return results
            seen.add(key)
            results.append((path, source))
        if state.truncated:
            return results

    return sorted(results, key=lambda item: item[0].relative_to(root).as_posix())
