from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from evagix.core.io import safe_read_text_result

README_FILENAMES = ("README.md", "readme.md", "README.rst", "README.txt")
README_MAX_CHARS = 150_000


class ReadmeStatus(StrEnum):
    MISSING = "missing"
    EMPTY = "empty"
    COMPLETE = "complete"
    TRUNCATED = "truncated"
    INVALID_UTF8 = "invalid_utf8"
    READ_ERROR = "read_error"

    @property
    def is_complete(self) -> bool:
        return self in {ReadmeStatus.MISSING, ReadmeStatus.EMPTY, ReadmeStatus.COMPLETE}


@dataclass(frozen=True)
class ReadmeSource:
    path: str
    text: str
    status: ReadmeStatus
    chars_read: int
    max_chars: int

    @property
    def complete(self) -> bool:
        return self.status.is_complete


def read_readme_source(root: Path, *, max_chars: int = README_MAX_CHARS) -> ReadmeSource:
    for name in README_FILENAMES:
        path = root / name
        if not os.path.lexists(path):
            continue
        try:
            result = safe_read_text_result(path, root=root, max_chars=max_chars)
        except UnicodeError:
            return ReadmeSource(
                path=name,
                text="",
                status=ReadmeStatus.INVALID_UTF8,
                chars_read=0,
                max_chars=max_chars,
            )
        except OSError:
            return ReadmeSource(
                path=name,
                text="",
                status=ReadmeStatus.READ_ERROR,
                chars_read=0,
                max_chars=max_chars,
            )

        if result.truncated:
            status = ReadmeStatus.TRUNCATED
        elif result.text:
            status = ReadmeStatus.COMPLETE
        else:
            status = ReadmeStatus.EMPTY
        return ReadmeSource(
            path=name,
            text=result.text,
            status=status,
            chars_read=len(result.text),
            max_chars=max_chars,
        )

    return ReadmeSource(
        path="",
        text="",
        status=ReadmeStatus.MISSING,
        chars_read=0,
        max_chars=max_chars,
    )
