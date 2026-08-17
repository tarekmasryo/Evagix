"""Small collection helpers shared across reporting and risk analysis."""

from __future__ import annotations

from collections.abc import Hashable, Iterable
from typing import TypeVar

T = TypeVar("T", bound=Hashable)


def unique_preserving_order(items: Iterable[T]) -> list[T]:
    """Return first occurrences in input order.

    Values must be hashable. The helper intentionally returns a list because
    callers use the result as stable CLI and JSON output.
    """

    seen: set[T] = set()
    result: list[T] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
