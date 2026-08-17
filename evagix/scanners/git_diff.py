from __future__ import annotations

from pathlib import Path

from evagix.changes import ChangedReport, build_changed_report


def scan_changed_files(root: Path, *, base: str = "main", head: str = "HEAD") -> ChangedReport:
    return build_changed_report(root, base=base, head=head)
