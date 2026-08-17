from __future__ import annotations

from pathlib import Path

from evagix.core.io import (
    PlannedFile,
    UnsafePathError,
    WriteConflictError,
    WritePlan,
    apply_write_plan,
    atomic_write_text,
    build_write_plan,
    is_safe_repo_path,
    safe_read_json_text,
    safe_read_text,
    validate_repo_path,
)
from evagix.utils import read_text, write_text

__all__ = [
    "Path",
    "PlannedFile",
    "UnsafePathError",
    "WriteConflictError",
    "WritePlan",
    "apply_write_plan",
    "atomic_write_text",
    "build_write_plan",
    "is_safe_repo_path",
    "read_text",
    "safe_read_json_text",
    "safe_read_text",
    "validate_repo_path",
    "write_text",
]
