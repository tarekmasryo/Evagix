from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

DEFAULT_SCORE_THRESHOLD = 80
MIN_SCORE_THRESHOLD = 0
MAX_SCORE_THRESHOLD = 100


class ThresholdValidationError(ValueError):
    """Raised when a score threshold is outside Evagix's valid range."""


@dataclass(frozen=True)
class ScoreThreshold:
    """Validated score threshold used by readiness gates."""

    value: int

    @classmethod
    def parse(cls, value: Any, *, field_name: str = "fail_under") -> ScoreThreshold:
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise ThresholdValidationError(f"{field_name} must be an integer between 0 and 100") from exc
        if not MIN_SCORE_THRESHOLD <= parsed <= MAX_SCORE_THRESHOLD:
            raise ThresholdValidationError(f"{field_name} must be between 0 and 100")
        return cls(parsed)


def coerce_score_threshold(
    value: Any, *, default: int = DEFAULT_SCORE_THRESHOLD, field_name: str = "fail_under"
) -> int:
    """Return a valid threshold, falling back to a safe default for config files."""

    try:
        return ScoreThreshold.parse(value, field_name=field_name).value
    except ThresholdValidationError:
        return ScoreThreshold.parse(default, field_name=field_name).value


def score_threshold_arg(value: str) -> int:
    """argparse type for --fail-under style score thresholds."""

    try:
        return ScoreThreshold.parse(value, field_name="--fail-under").value
    except ThresholdValidationError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
