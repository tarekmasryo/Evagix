from __future__ import annotations

import sys
from pathlib import Path

from evagix.command_safety import (
    scan_command_values,
    scan_package_script_dangers,
    scan_referenced_script_dangers,
    scan_task_recipe_dangers,
)
from evagix.config import load_config
from evagix.core.io import DEFAULT_MAX_TEXT_CHARS, safe_read_text_result
from evagix.evidence import Finding
from evagix.model import RepoFacts


def reject_unsafe_generated_commands(root: Path, facts: RepoFacts) -> bool:
    """Report and reject commands that would make agent-facing output unsafe."""

    findings = unsafe_generated_command_findings(root, facts)
    if not findings:
        return False
    print(
        "ERROR: Unsafe validation commands detected; generated agent instructions would be unsafe.",
        file=sys.stderr,
    )
    for finding in findings[:10]:
        location = finding.source_file or finding.source or "detected command"
        if finding.source_line:
            location = f"{location}:{finding.source_line}"
        evidence = finding.evidence[0] if finding.evidence else finding.title
        print(f"  - {location}: {evidence}", file=sys.stderr)
    return True


def unsafe_generated_command_findings(root: Path, facts: RepoFacts) -> list[Finding]:
    """Scan every concrete command that can be emitted to generated context."""

    commands = dict(facts.commands)
    sources = {name: evidence.source for name, evidence in facts.command_sources.items()}
    for subproject in facts.subprojects:
        for name, command in subproject.commands.items():
            scoped_name = f"{subproject.path}:{name}"
            commands[scoped_name] = command
            sources[scoped_name] = subproject.path

    # RepoFacts intentionally stores redacted command text. Re-load configured
    # commands at this enforcement boundary so literal credentials are rejected
    # rather than silently converted into apparently safe generated guidance.
    config = load_config(root)
    for name, command in config.custom_validation_commands.items():
        commands[name] = command
        sources[name] = "evagix.toml"

    findings = [
        *scan_command_values(commands, sources=sources),
        *scan_package_script_dangers(root),
        *scan_task_recipe_dangers(root),
        *scan_referenced_script_dangers(root, commands, sources=sources),
    ]
    unique: dict[tuple[str, str, str], Finding] = {}
    for finding in findings:
        key = (finding.id, finding.source_file, finding.root_cause)
        unique.setdefault(key, finding)
    return list(unique.values())


class GeneratedTargetTooLarge(OSError):
    """Raised when an existing generated target exceeds the verification read limit."""


class GeneratedTargetInvalidEncoding(OSError):
    """Raised when an existing generated target is not valid UTF-8."""


def read_existing_generated_target(root: Path, path: Path) -> str:
    """Read a generated target completely or reject it when the safety limit is exceeded."""

    try:
        result = safe_read_text_result(
            path,
            root=root,
            max_chars=DEFAULT_MAX_TEXT_CHARS,
        )
    except UnicodeError as exc:
        relative_path = path.relative_to(root).as_posix()
        raise GeneratedTargetInvalidEncoding(
            f"Existing target is not valid UTF-8 and cannot be verified safely: {relative_path}"
        ) from exc
    if result.truncated:
        relative_path = path.relative_to(root).as_posix()
        raise GeneratedTargetTooLarge(
            f"Existing target exceeds the {DEFAULT_MAX_TEXT_CHARS}-character safety limit: {relative_path}"
        )
    return result.text
