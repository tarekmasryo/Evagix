from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from evagix.model import Evidence, RepoFacts
from evagix.scanner_utils import _is_ignored_path, _is_safe_repo_path
from evagix.security.redaction import redact_sensitive_text


def _is_available(root: Path, relative_path: str, ignored_paths: set[str]) -> bool:
    path = root / relative_path
    return path.exists() and _is_safe_repo_path(root, path) and not _is_ignored_path(root, path, ignored_paths)


def _add_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def has_python_package_metadata(data: dict[str, Any]) -> bool:
    if isinstance(data.get("project"), dict) or isinstance(data.get("build-system"), dict):
        return True
    tool = data.get("tool", {}) if isinstance(data.get("tool"), dict) else {}
    return any(isinstance(tool.get(name), dict) for name in {"poetry", "hatch", "pdm", "flit", "setuptools"})


def setup_cfg_has_package_metadata(text: str) -> bool:
    section = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line.casefold()
            continue
        if section == "[metadata]" and line.casefold().startswith("name") and "=" in line:
            return bool(line.split("=", 1)[1].strip())
    return False


def is_node_test_placeholder(script: object) -> bool:
    value = " ".join(str(script).casefold().split())
    if not value:
        return True
    if "error: no test specified" in value:
        return True
    if re.search(r"\btests?\s+(?:is\s+|are\s+)?not\s+implemented\b", value):
        return True
    placeholder_message = bool(
        re.search(r"\bno\s+tests?(?:\s+(?:configured|specified|defined|available))?\b", value)
        or re.search(r"\btests?\s+placeholder\b|\bplaceholder\s+tests?\b", value)
    )
    known_runner = re.search(r"\b(?:jest|vitest|pytest|mocha|ava|tap|playwright|cypress)\b", value)
    return placeholder_message and known_runner is None and bool(re.search(r"\b(?:echo|printf|throw|exit)\b", value))


def _set_command(
    facts: RepoFacts,
    name: str,
    command: str,
    source: str,
    detail: str,
    confidence: str,
    *,
    prefer: bool = False,
    priority: int = 50,
    status: str = "declared",
) -> None:
    effective_priority = max(priority, 75) if prefer else priority
    current_priority = facts._command_priorities.get(name, -1)
    if effective_priority > current_priority:
        reason = f"{detail}; source={source}; confidence={confidence}; status={status}"
        facts.commands[name] = redact_sensitive_text(command)
        facts._command_priorities[name] = effective_priority
        facts.command_sources[name] = Evidence(
            source=source,
            detail=detail,
            confidence=confidence,
            status=status,
            reason=reason,
            path=source if source not in {"dependency files", "alembic"} else "",
        )
