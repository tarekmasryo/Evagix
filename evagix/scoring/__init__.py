"""Scoring engine separated from CLI and report rendering."""

from evagix.scoring.engine import score_from_findings

__all__ = ["score_from_findings"]
