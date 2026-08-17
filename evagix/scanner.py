"""Backward-compatible public facade for repository scanning."""

from __future__ import annotations

from evagix.scanning.repository import scan_repo

__all__ = ["scan_repo"]
