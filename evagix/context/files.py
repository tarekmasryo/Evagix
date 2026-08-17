from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from evagix.agent_context_registry import (
    generated_agent_target_paths,
    iter_agent_context_paths,
    unsafe_declared_agent_context_paths,
)
from evagix.core.io import UnsafePathError, safe_read_text_result
from evagix.evidence import Finding
from evagix.scanner_utils import TraversalDiagnostics
from evagix.text_diagnostics import invalid_utf8_finding

MAX_AGENT_CONTEXT_CHARS = 220_000
MAX_AGENT_CONTEXT_FILES = 200


@dataclass(frozen=True)
class LoadedAgentContextFile:
    relative_path: str
    path: Path
    text: str
    truncated: bool = False
    invalid_encoding: bool = False
    read_error: bool = False


def _candidate_paths(root: Path) -> tuple[list[Path], TraversalDiagnostics]:
    diagnostics = TraversalDiagnostics()
    paths = {
        path
        for path, _source in iter_agent_context_paths(
            root,
            limit=MAX_AGENT_CONTEXT_FILES,
            diagnostics=diagnostics,
        )
    }
    paths.update(root / relative for relative in generated_agent_target_paths())
    return sorted(paths), diagnostics


def _unsafe_context_paths(root: Path) -> list[Finding]:
    _paths, diagnostics = _candidate_paths(root)
    findings: list[Finding] = []
    for path in unsafe_declared_agent_context_paths(root):
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = path.as_posix()
        findings.append(
            Finding(
                id="agent-context.unsafe-symlink",
                title="Agent context path is a symlink and was not followed",
                category="agent_context",
                severity="high",
                status="unsafe_path",
                source=relative,
                source_file=relative,
                evidence=["symlinked agent context file was skipped"],
                risk="Following symlinked agent context can cross repository trust boundaries.",
                recommendation="Replace the symlink with a normal reviewed file inside the repository, or remove it.",
                confidence="high",
            )
        )
    if diagnostics.incomplete:
        findings.append(_traversal_finding(diagnostics))
    return findings


def _agent_context_files(root: Path) -> list[LoadedAgentContextFile]:
    paths, _diagnostics = _candidate_paths(root)
    files: list[LoadedAgentContextFile] = []
    for path in paths:
        try:
            if not path.exists() or not path.is_file():
                continue
        except OSError:
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                relative = path.name
            files.append(
                LoadedAgentContextFile(
                    relative_path=relative,
                    path=path,
                    text="",
                    read_error=True,
                )
            )
            continue
        try:
            read_result = safe_read_text_result(
                path,
                root=root,
                max_chars=MAX_AGENT_CONTEXT_CHARS,
            )
        except UnicodeError:
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                relative = path.as_posix()
            files.append(
                LoadedAgentContextFile(
                    relative_path=relative,
                    path=path,
                    text="",
                    invalid_encoding=True,
                )
            )
            continue
        except UnsafePathError:
            continue
        except OSError:
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                relative = path.name
            files.append(
                LoadedAgentContextFile(
                    relative_path=relative,
                    path=path,
                    text="",
                    read_error=True,
                )
            )
            continue
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = path.as_posix()
        files.append(
            LoadedAgentContextFile(
                relative_path=relative,
                path=path,
                text=read_result.text,
                truncated=read_result.truncated,
            )
        )
    return files


def invalid_agent_context_findings(root: Path, files: list[LoadedAgentContextFile]) -> list[Finding]:
    return [
        invalid_utf8_finding(root, item.path, scanner="Agent-context scan", category="agent_context")
        for item in files
        if item.invalid_encoding
    ]


def truncated_agent_context_findings(files: list[LoadedAgentContextFile]) -> list[Finding]:
    return [
        Finding(
            id="agent-context.scan-truncated",
            title=(
                "Agent context safety scan was incomplete"
                if item.read_error
                else "Agent context safety scan was truncated"
            ),
            category="agent_context",
            severity="high",
            status="incomplete",
            source=item.relative_path,
            source_file=item.relative_path,
            evidence=(
                ["file could not be read"] if item.read_error else [f"read limit: {MAX_AGENT_CONTEXT_CHARS} characters"]
            ),
            risk=(
                "The agent context file could not be inspected for dangerous commands or context poisoning."
                if item.read_error
                else "Content beyond the read limit was not inspected for dangerous commands or context poisoning."
            ),
            recommendation=(
                "Restore read access before relying on the agent-context safety result."
                if item.read_error
                else "Reduce or split the agent context file before relying on the safety result."
            ),
            confidence="high",
            root_cause=(
                f"agent-context-read-error:{item.relative_path}"
                if item.read_error
                else f"agent-context-truncated:{item.relative_path}"
            ),
        )
        for item in files
        if item.truncated or item.read_error
    ]


def _traversal_finding(diagnostics: TraversalDiagnostics) -> Finding:
    return Finding(
        id="agent-context.discovery-truncated",
        title="Agent context discovery was truncated",
        category="agent_context",
        severity="high",
        status="incomplete",
        source="repository agent-context paths",
        evidence=[diagnostics.warning("Agent context discovery")],
        risk="Some supported agent-context files may not have been inspected.",
        recommendation="Reduce the repository scan scope or increase the configured traversal budget.",
        confidence="high",
        root_cause="agent-context-discovery-truncated",
    )
