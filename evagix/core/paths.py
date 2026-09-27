from __future__ import annotations

import os
import re
from pathlib import Path

from evagix.safety import EvagixSafetyError


def validate_output_path_syntax(path: str | Path) -> None:
    """Reject ambiguous Windows output components before normalization or resolution."""
    if os.name != "nt":
        return
    candidate = Path(path)
    parts = candidate.parts[1:] if candidate.anchor else candidate.parts
    for part in parts:
        if re.search(r'[<>:"|?*\x00-\x1f]|~[0-9]', part) or Path(part.rstrip(" .")).is_reserved():
            raise EvagixSafetyError(
                f"Unsafe Windows output path component {part!r}: "
                "8.3-style aliases, NTFS alternate data streams, reserved names, "
                "and invalid filename characters are not supported."
            )


def output_path_key(path: str | Path) -> str:
    """Compare output destinations using native path aliases, without filesystem writes."""
    validate_output_path_syntax(path)
    value = os.path.normpath(path)
    if os.name == "nt":
        # Win32 aliases trailing dots/spaces as well as case and separators.
        value = "\\".join(part if part in {".", ".."} else part.rstrip(" .") for part in value.split("\\"))
    return os.path.normcase(os.path.normpath(value))


def repo_relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
