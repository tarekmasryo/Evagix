from __future__ import annotations

import os
import stat
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_TEXT_CHARS = 1_000_000


class UnsafePathError(OSError):
    """Raised when a repository file access would cross a trust boundary."""


class WriteConflictError(OSError):
    """Raised when a planned write would overwrite a protected file."""


@dataclass(frozen=True)
class TextReadResult:
    text: str
    truncated: bool
    max_chars: int


@dataclass(frozen=True)
class PlannedFile:
    relative_path: str
    path: Path
    content: str


@dataclass(frozen=True)
class WritePlan:
    root: Path
    files: tuple[PlannedFile, ...]
    conflicts: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.conflicts

    @property
    def relative_paths(self) -> list[str]:
        return [item.relative_path for item in self.files]


def ensure_inside_root(root: Path, path: Path) -> Path:
    root_resolved = root.resolve(strict=False)
    path_resolved = path.resolve(strict=False)
    try:
        path_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise UnsafePathError(f"Path escapes repository root: {path}") from exc
    return path_resolved


def _reject_symlink_components(root: Path, path: Path) -> None:
    root_resolved = root.resolve(strict=False)
    candidate = path if path.is_absolute() else root_resolved / path
    current = candidate
    parts: list[Path] = []
    while True:
        parts.append(current)
        if current == root_resolved or current.parent == current:
            break
        current = current.parent
    for item in reversed(parts):
        try:
            if item.exists() and item.is_symlink():
                raise UnsafePathError(f"Refusing to follow symlink inside repository boundary: {item}")
        except OSError as exc:
            if isinstance(exc, UnsafePathError):
                raise
            raise UnsafePathError(f"Unable to validate path boundary: {item}") from exc


def validate_repo_path(root: Path, path: Path) -> Path:
    """Return a resolved repository path after enforcing Evagix boundary rules.

    A path is valid only when its resolved target stays inside ``root`` and no
    existing component below ``root`` is a symlink. This protects both reads and
    writes from parent-directory symlink escapes such as ``.github -> ../out``.
    """
    _reject_symlink_components(root, path)
    return ensure_inside_root(root, path)


def is_safe_repo_path(root: Path, path: Path) -> bool:
    """Return True when ``path`` satisfies Evagix repository-boundary rules."""
    try:
        validate_repo_path(root, path)
    except OSError:
        return False
    return True


def safe_read_text_result(
    path: Path,
    *,
    root: Path | None = None,
    max_chars: int = DEFAULT_MAX_TEXT_CHARS,
    errors: str = "strict",
) -> TextReadResult:
    """Read a repository text file with an explicit memory bound.

    One extra character is read only to determine whether the result was
    truncated. Callers that make trust or completeness decisions should inspect
    ``truncated`` instead of silently treating partial content as complete.
    """
    if max_chars < 0:
        raise ValueError("max_chars must be non-negative")
    if root is not None:
        validate_repo_path(root, path)
    elif path.exists() and path.is_symlink():
        raise UnsafePathError(f"Refusing to read symlink: {path}")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8", errors=errors) as handle:
        content = handle.read(max_chars + 1)
    return TextReadResult(text=content[:max_chars], truncated=len(content) > max_chars, max_chars=max_chars)


def safe_read_text(
    path: Path,
    *,
    root: Path | None = None,
    max_chars: int = DEFAULT_MAX_TEXT_CHARS,
    errors: str = "strict",
) -> str:
    if max_chars < 0:
        raise ValueError("max_chars must be non-negative")
    if root is not None:
        validate_repo_path(root, path)
    elif path.exists() and path.is_symlink():
        raise UnsafePathError(f"Refusing to read symlink: {path}")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8", errors=errors) as handle:
        return handle.read(max_chars)


def safe_read_json_text(path: Path, *, root: Path | None = None, max_chars: int = 1_000_000) -> str:
    return safe_read_text(path, root=root, max_chars=max_chars)


def atomic_write_text(
    path: Path,
    content: str,
    *,
    new_file_mode: int = 0o600,
) -> None:
    """Atomically write UTF-8 text while preserving existing POSIX modes.

    Existing files retain their permission bits. New files default to an
    owner-only mode unless a repository-managed caller explicitly requests a
    more permissive mode. Windows keeps its existing permission semantics.
    """
    if not 0 <= new_file_mode <= 0o7777:
        raise ValueError("new_file_mode must be a valid POSIX permission mode")

    path.parent.mkdir(parents=True, exist_ok=True)
    existing_mode: int | None = None
    if os.name != "nt":
        with suppress(FileNotFoundError):
            existing_mode = stat.S_IMODE(path.stat().st_mode)

    fd = -1
    tmp_name = ""
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        if os.name != "nt" and hasattr(os, "fchmod"):
            os.fchmod(fd, existing_mode if existing_mode is not None else new_file_mode)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            fd = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        Path(tmp_name).replace(path)
    finally:
        if fd != -1:
            os.close(fd)
        if tmp_name:
            with suppress(FileNotFoundError):
                Path(tmp_name).unlink()


def build_write_plan(root: Path, outputs: dict[str, str], *, force: bool = False) -> WritePlan:
    root = root.resolve(strict=False)
    files: list[PlannedFile] = []
    conflicts: list[str] = []
    for relative_path, content in sorted(outputs.items()):
        path = validate_repo_path(root, root / relative_path)
        if path.exists() and not force:
            conflicts.append(relative_path)
            continue
        files.append(PlannedFile(relative_path=relative_path, path=path, content=content))
    return WritePlan(root=root, files=tuple(files), conflicts=tuple(conflicts))


def apply_write_plan(plan: WritePlan) -> list[str]:
    if plan.conflicts:
        raise WriteConflictError("Write plan has conflicts: " + ", ".join(plan.conflicts))
    written: list[str] = []
    for item in plan.files:
        atomic_write_text(item.path, item.content, new_file_mode=0o644)
        written.append(item.relative_path)
    return written
