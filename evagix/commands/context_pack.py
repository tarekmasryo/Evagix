from __future__ import annotations

from pathlib import Path

from evagix.commands.common import _facts
from evagix.reports.context_pack import render_context_pack


def run_context_pack(root: Path) -> str:
    facts, _ = _facts(root)
    return render_context_pack(root, facts)
