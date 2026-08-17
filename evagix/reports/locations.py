from __future__ import annotations

import re
from dataclasses import dataclass

SOURCE_PATTERN = re.compile(r"source:\s*([^;]+)")

CODE_LOCATION_FALLBACKS = {
    "missing-ci": ".github/workflows/",
    "stale-target": ".evagix/context.md",
    "generated-context-drift": ".evagix/context.md",
    "missing-target": ".evagix/context.md",
    "tampered-target": ".evagix/context.md",
    "missing-lint": "pyproject.toml",
    "missing-typecheck": "pyproject.toml",
    "missing-llm-eval": "evagix.toml",
    "frontend-install-not-deterministic": "package.json",
    "env-file-present": ".env",
    "risk-flags-detected": ".",
    "readme-command-gap": "README.md",
}

NON_FILE_SOURCES = {
    "agent context files",
    "repository facts",
    "repository",
    "scan facts",
}


@dataclass(frozen=True)
class FindingLocation:
    uri: str
    start_line: int = 1


def location_from_finding(code: str, message: str = "") -> FindingLocation:
    """Resolve the best user-facing source location for a finding.

    Evidence-backed findings often include a `source: path:line` fragment in the
    message. We prefer that exact source, then fall back to stable rule defaults.
    """

    parsed = _parse_message_source(message)
    if parsed is not None:
        return parsed
    return FindingLocation(uri=finding_location(code), start_line=1)


def finding_location(code: str) -> str:
    if code.startswith("readme") or code.startswith("README"):
        return "README.md"
    if code.startswith("agent-context") or code.startswith("context-poisoning"):
        return "AGENTS.md"
    if code.startswith("dangerous-command"):
        return "README.md"
    return CODE_LOCATION_FALLBACKS.get(code, ".")


def _parse_message_source(message: str) -> FindingLocation | None:
    match = SOURCE_PATTERN.search(message)
    if not match:
        return None
    source = match.group(1).strip().strip("`")
    if not source or source.lower() in NON_FILE_SOURCES:
        return None

    uri = source
    line = 1
    if ":" in source:
        maybe_path, maybe_line = source.rsplit(":", 1)
        if maybe_line.isdigit():
            uri = maybe_path
            line = max(1, int(maybe_line))

    uri = uri.strip().replace("\\", "/").strip("./")
    if not uri or " " in uri or uri.lower() in NON_FILE_SOURCES:
        return None
    return FindingLocation(uri=uri, start_line=line)
