from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from evagix.core.io import (
    DEFAULT_MAX_TEXT_CHARS,
    UnsafePathError,
    atomic_write_text,
    safe_read_text,
    validate_repo_path,
)
from evagix.readme.source import ReadmeStatus, read_readme_source
from evagix.security.redaction import redact_for_output, redact_sensitive_text

GENERATED_MARKER = "evagix:generated"
FINGERPRINT_PREFIX = "evagix:fingerprint="
FINGERPRINT_RE = re.compile(rf"{re.escape(FINGERPRINT_PREFIX)}([A-Za-z0-9_-]+)")


def stable_json(data: Any, *, redact: bool = True) -> str:
    payload = redact_for_output(data) if redact else data
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def facts_fingerprint(facts: Any) -> str:
    if isinstance(facts, dict):
        facts = {key: value for key, value in facts.items() if key != "generated_targets"}
    return sha256_text(stable_json(facts, redact=False))[:16]


def read_text(path: Path, *, root: Path | None = None, max_chars: int = DEFAULT_MAX_TEXT_CHARS) -> str:
    return safe_read_text(path, root=root, max_chars=max_chars)


def write_text(path: Path, content: str) -> None:
    atomic_write_text(path, redact_sensitive_text(content))


def format_csv(items: list[str] | tuple[str, ...]) -> str:
    return ", ".join(f"`{item}`" for item in items) if items else "not detected"


def has_any_command(commands: dict[str, str], name: str) -> bool:
    return name in commands or any(key.endswith(f"_{name}") for key in commands)


def has_readme(root: Path) -> bool:
    return read_readme_source(root).status != ReadmeStatus.MISSING


def resolve_output_path(root: Path, output: str) -> Path:
    root = root.resolve(strict=False)
    try:
        return validate_repo_path(root, root / output)
    except UnsafePathError as exc:
        raise ValueError(f"Output path must stay inside repository root and avoid symlink escapes: {output}") from exc


def extract_fingerprint(content: str) -> str | None:
    for line in content.splitlines()[:5]:
        match = FINGERPRINT_RE.search(line)
        if match:
            return match.group(1)
    return None


def is_generated(content: str) -> bool:
    return any(GENERATED_MARKER in line for line in content.splitlines()[0:5])


def normalize_generated_content(content: str) -> str:
    """Normalize generated text for cross-platform drift checks.

    Evagix writes generated files with LF line endings. Repositories may be
    checked out with CRLF on Windows, so drift checks compare generated content
    after normalizing line endings while preserving all other bytes.
    """
    return content.replace("\r\n", "\n").replace("\r", "\n")
