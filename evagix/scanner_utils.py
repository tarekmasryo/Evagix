from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import islice
from pathlib import Path

from evagix.core.io import is_safe_repo_path, safe_read_text

DEFAULT_MAX_VISITED_ENTRIES = 50_000

DEFAULT_SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "dist",
        "build",
        "site-packages",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".coverage",
        ".coverage.*",
        ".cursor",
        ".tox",
        ".nox",
        ".next",
        ".turbo",
        "coverage",
        "htmlcov",
        "pytest-cache-files",
        "fixtures",
        "fixture",
        "examples",
        "example",
        "samples",
        "sample",
        "demos",
        "demo",
    }
)

SENSITIVE_FILE_NAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.development",
        ".env.production",
        ".env.test",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
    }
)

SENSITIVE_SUFFIXES = frozenset(
    {
        ".key",
        ".pem",
        ".p12",
        ".pfx",
    }
)

TRANSIENT_SKIP_PREFIXES = ("pytest-cache-files-", ".coverage", "coverage-")


@dataclass
class TraversalDiagnostics:
    """Mutable diagnostics for one bounded repository traversal."""

    max_visited_entries: int = DEFAULT_MAX_VISITED_ENTRIES
    visited_entries: int = 0
    visited_directories: int = 0
    visited_files: int = 0
    truncated: bool = False
    result_limit_reached: bool = False
    read_errors: int = 0

    @property
    def incomplete(self) -> bool:
        return self.truncated or self.result_limit_reached or self.read_errors > 0

    def warning(self, scope: str) -> str:
        reasons: list[str] = []
        if self.truncated:
            reasons.append(f"the {self.max_visited_entries}-entry traversal budget was reached")
        if self.result_limit_reached:
            reasons.append("the result limit was reached")
        if self.read_errors:
            reasons.append(
                f"{self.read_errors} filesystem entr{'y' if self.read_errors == 1 else 'ies'} could not be inspected"
            )
        reason = " and ".join(reasons) or "a configured scan limit was reached"
        state = "incomplete" if self.read_errors else "truncated"
        return (
            f"{scope} was {state} because {reason} after {self.visited_entries} filesystem entries "
            f"({self.visited_directories} directories, {self.visited_files} files); results may be incomplete."
        )


def is_skipped_dir_name(name: str) -> bool:
    """Return True for generated, vendor, cache, or fixture directories Evagix should not traverse."""
    if name in DEFAULT_SKIP_DIRS or name.endswith(".egg-info"):
        return True
    return name.startswith(TRANSIENT_SKIP_PREFIXES)


def is_sensitive_file_name(name: str) -> bool:
    """Return True for local secret-bearing filenames that should not be read."""
    lowered = name.lower()
    return lowered in SENSITIVE_FILE_NAMES or any(lowered.endswith(suffix) for suffix in SENSITIVE_SUFFIXES)


def _is_skipped_dir_name(name: str) -> bool:
    return is_skipped_dir_name(name)


def _is_sensitive_file_name(name: str) -> bool:
    return is_sensitive_file_name(name)


def _is_safe_repo_path(root: Path, path: Path) -> bool:
    return not _is_sensitive_file_name(path.name) and is_safe_repo_path(root, path)


def _safe_read(path: Path, max_chars: int = 120_000) -> str:
    try:
        if path.is_symlink() or _is_sensitive_file_name(path.name):
            return ""
        return safe_read_text(path, max_chars=max_chars)
    except (OSError, UnicodeError):
        return ""


def _read_bounded_directory_entries(
    directory: Path,
    *,
    remaining_budget: int,
) -> tuple[list[os.DirEntry[str]], bool]:
    """Read at most the remaining entry budget plus one truncation probe.

    The extra probe distinguishes an exactly exhausted directory from a
    directory whose remaining entries were not inspected. Only entries inside
    the budget are returned for processing.
    """
    bounded_budget = max(remaining_budget, 0)
    with os.scandir(directory) as iterator:
        sampled = list(islice(iterator, bounded_budget + 1))

    truncated = len(sampled) > bounded_budget
    entries = sampled[:bounded_budget]
    entries.sort(key=lambda item: item.name)
    return entries, truncated


def _iter_repo_files(
    root: Path,
    *,
    ignored_paths: set[str] | None = None,
    diagnostics: TraversalDiagnostics | None = None,
    max_visited_entries: int | None = None,
    start: Path | None = None,
    allow_skipped_start: bool = False,
    max_depth: int | None = None,
    extra_skip_dir_names: set[str] | None = None,
    allow_package_dirs_in_skipped_paths: bool = False,
) -> Iterator[Path]:
    """Yield safe repository files with hard traversal bounds.

    Fully inspected directories are processed in deterministic name order. A
    directory truncated by the remaining budget uses a bounded filesystem-order
    subset and emits incomplete-scan diagnostics through ``state``.

    ``allow_package_dirs_in_skipped_paths`` is reserved for package metadata
    discovery that must inspect importable packages even when a parent folder
    would normally be treated as low-signal fixture/example content.
    """
    ignored = ignored_paths or set()
    if max_visited_entries is not None:
        effective_limit = max_visited_entries
    elif diagnostics is not None:
        effective_limit = diagnostics.max_visited_entries
    else:
        effective_limit = DEFAULT_MAX_VISITED_ENTRIES
    state = diagnostics or TraversalDiagnostics(max_visited_entries=effective_limit)
    state.max_visited_entries = effective_limit
    traversal_root = start or root
    extra_skips = extra_skip_dir_names or set()
    try:
        allowed_prefix = traversal_root.relative_to(root).parts if allow_skipped_start else ()
    except ValueError:
        return

    def has_disallowed_skip(path: Path) -> bool:
        try:
            parts = path.relative_to(root).parts
        except ValueError:
            return True
        for index, part in enumerate(parts):
            if not (_is_skipped_dir_name(part) or part in extra_skips):
                continue
            if index < len(allowed_prefix) and part == allowed_prefix[index]:
                continue
            if allow_package_dirs_in_skipped_paths:
                candidate = root.joinpath(*parts[: index + 1])
                try:
                    if (candidate / "__init__.py").is_file():
                        continue
                except (OSError, UnicodeError):
                    state.read_errors += 1
            return True
        return False

    stack = [traversal_root]
    while stack:
        current = stack.pop()
        if _is_ignored_path(root, current, ignored):
            continue
        try:
            rel_parts = current.relative_to(root).parts
        except ValueError:
            continue
        current_depth = len(rel_parts)
        if max_depth is not None and current_depth > max_depth:
            continue
        if has_disallowed_skip(current):
            continue
        state.visited_directories += 1
        remaining_budget = state.max_visited_entries - state.visited_entries
        try:
            entries, directory_truncated = _read_bounded_directory_entries(
                current,
                remaining_budget=remaining_budget,
            )
        except (OSError, UnicodeError):
            state.read_errors += 1
            continue

        child_directories: list[Path] = []
        for entry in entries:
            state.visited_entries += 1
            path = Path(entry.path)
            try:
                if entry.is_dir(follow_symlinks=False):
                    if (
                        (max_depth is None or current_depth < max_depth)
                        and not has_disallowed_skip(path)
                        and not _is_ignored_path(root, path, ignored)
                    ):
                        child_directories.append(path)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
            except (OSError, UnicodeError):
                state.read_errors += 1
                continue
            state.visited_files += 1
            if _is_safe_repo_path(root, path) and not _is_ignored_path(root, path, ignored):
                yield path
        if directory_truncated:
            state.truncated = True
            return
        stack.extend(reversed(child_directories))


def _iter_named_files(
    root: Path,
    names: set[str],
    ignored_paths: set[str] | None = None,
    limit: int = 200,
    *,
    diagnostics: TraversalDiagnostics | None = None,
    max_visited_entries: int | None = None,
    max_depth: int | None = None,
    extra_skip_dir_names: set[str] | None = None,
) -> list[Path]:
    results: list[Path] = []
    for path in _iter_repo_files(
        root,
        ignored_paths=ignored_paths,
        diagnostics=diagnostics,
        max_visited_entries=max_visited_entries,
        max_depth=max_depth,
        extra_skip_dir_names=extra_skip_dir_names,
    ):
        if path.name not in names:
            continue
        if len(results) >= limit:
            if diagnostics is not None:
                diagnostics.result_limit_reached = True
            break
        results.append(path)
    return results


def _iter_files(
    root: Path,
    suffixes: set[str],
    limit: int,
    ignored_paths: set[str] | None = None,
    *,
    diagnostics: TraversalDiagnostics | None = None,
    max_visited_entries: int | None = None,
    max_depth: int | None = None,
    extra_skip_dir_names: set[str] | None = None,
) -> list[Path]:
    results: list[Path] = []
    for path in _iter_repo_files(
        root,
        ignored_paths=ignored_paths,
        diagnostics=diagnostics,
        max_visited_entries=max_visited_entries,
        max_depth=max_depth,
        extra_skip_dir_names=extra_skip_dir_names,
    ):
        if path.suffix not in suffixes:
            continue
        if len(results) >= limit:
            if diagnostics is not None:
                diagnostics.result_limit_reached = True
            break
        results.append(path)
    return results


def _has_files(root: Path, suffixes: set[str], ignored_paths: set[str] | None = None) -> bool:
    return bool(_iter_files(root, suffixes, limit=1, ignored_paths=ignored_paths))


def _normalize_ignored_paths(ignored_paths: list[str] | None) -> set[str]:
    normalized: set[str] = set()
    for item in ignored_paths or []:
        value = item.strip().replace("\\", "/").strip("/")
        if value:
            normalized.add(value)
    return normalized


def _is_ignored_path(root: Path, path: Path, ignored_paths: set[str]) -> bool:
    if not ignored_paths:
        return False
    try:
        rel = path.relative_to(root).as_posix().strip("/")
    except ValueError:
        return False
    parts = rel.split("/") if rel else []
    for ignored in ignored_paths:
        ignored_clean = ignored.rstrip("/")
        if rel == ignored_clean or rel.startswith(ignored_clean + "/"):
            return True
        if "/" not in ignored_clean and ignored_clean in parts:
            return True
    return False
