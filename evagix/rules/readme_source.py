from __future__ import annotations

from evagix.rules.models import Severity

README_SOURCE_RULES: tuple[tuple[str, str, Severity, bool], ...] = (
    ("readme.empty", "README is empty", "medium", False),
    ("readme.scan-truncated", "README analysis was truncated", "high", True),
    ("readme.read-error", "README could not be read safely", "high", True),
)
