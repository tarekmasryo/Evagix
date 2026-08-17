from __future__ import annotations

import ast
from pathlib import Path


def test_architecture_guard_cli_is_router_sized() -> None:
    cli = Path("evagix/cli.py")
    assert len(cli.read_text(encoding="utf-8").splitlines()) <= 500


def test_architecture_guard_no_direct_file_io_outside_core_io() -> None:
    allowed = {Path("evagix/core/io.py")}
    for path in Path("evagix").rglob("*.py"):
        if path in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {"read_text", "write_text"}:
                raise AssertionError(
                    f"Direct Path.{node.attr} use in {path}:{node.lineno}; use core.io helpers instead"
                )
