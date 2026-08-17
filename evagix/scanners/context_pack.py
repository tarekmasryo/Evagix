from __future__ import annotations

from pathlib import Path

from evagix.reports.context_pack import render_context_pack
from evagix.scanner import scan_repo


def build_context_pack(root: Path) -> str:
    return render_context_pack(root, scan_repo(root))
