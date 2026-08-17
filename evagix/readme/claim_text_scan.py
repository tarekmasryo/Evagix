from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from evagix.core.io import safe_read_text
from evagix.scanner_utils import TraversalDiagnostics, _iter_repo_files

MAX_TEXT_SCAN_RESULTS = 250
MAX_TEXT_SCAN_VISITED_ENTRIES = 50_000
MAX_TEXT_FILE_BYTES = 500_000
MAX_TEXT_FILE_CHARS = 120_000
_TEXT_SUFFIXES = frozenset({".py", ".md", ".txt", ".toml", ".yml", ".yaml", ".json"})


def _repo_text_contains(
    root: Path,
    needles: list[str],
    *,
    diagnostics: TraversalDiagnostics | None = None,
) -> bool:
    lower_needles = [item.lower() for item in needles]
    for path in _iter_small_text_files(root, diagnostics=diagnostics):
        try:
            text = safe_read_text(path, root=root, max_chars=MAX_TEXT_FILE_CHARS).lower()
        except (OSError, UnicodeError):
            continue
        if any(needle in text for needle in lower_needles):
            return True
    return False


def _iter_small_text_files(
    root: Path,
    *,
    diagnostics: TraversalDiagnostics | None = None,
) -> Iterator[Path]:
    state = diagnostics or TraversalDiagnostics(max_visited_entries=MAX_TEXT_SCAN_VISITED_ENTRIES)
    state.max_visited_entries = MAX_TEXT_SCAN_VISITED_ENTRIES
    matched = 0
    for path in _iter_repo_files(
        root,
        diagnostics=state,
        max_visited_entries=MAX_TEXT_SCAN_VISITED_ENTRIES,
    ):
        if path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        try:
            if path.stat().st_size > MAX_TEXT_FILE_BYTES:
                continue
        except (OSError, UnicodeError):
            continue
        if matched >= MAX_TEXT_SCAN_RESULTS:
            state.result_limit_reached = True
            break
        matched += 1
        yield path


def _is_adjacent_attribution_reference(text: str, match_start: int) -> bool:
    adjacent_lines: list[str] = []
    for line in reversed(text[:match_start].splitlines()):
        stripped = line.strip()
        if not stripped:
            break
        adjacent_lines.append(stripped)
        if len(adjacent_lines) == 3:
            break
    prefix = " ".join(reversed(adjacent_lines)).casefold()
    role = r"(?:creator|co[- ]creator|founder|co[- ]founder|maintainer|author|developer)"
    return bool(re.search(rf"\b{role}\s+of(?:\s+(?:\[[*\x60_]*|[*\x60_]*))?$", prefix))


def _is_markdown_link_destination(text: str, position: int) -> bool:
    line_start = text.rfind("\n", 0, position) + 1
    line_end = text.find("\n", position)
    if line_end < 0:
        line_end = len(text)
    line = text[line_start:line_end]
    relative_position = position - line_start
    for match in re.finditer(r"!?\[[^\]\n]*\]\((?P<destination>[^)\n]*)\)", line):
        if match.start("destination") <= relative_position < match.end("destination"):
            return True
    return False
