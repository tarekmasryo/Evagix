from __future__ import annotations

from pathlib import Path

from evagix.cli import main


def test_onboard_conflict_does_not_leave_partial_writes(tmp_path: Path) -> None:
    (tmp_path / ".evagix").mkdir()
    (tmp_path / ".evagix" / "summary.md").write_text("manual", encoding="utf-8")
    assert main(["onboard", str(tmp_path)]) == 1
    assert not (tmp_path / ".evagix" / "architecture.md").exists()
    assert (tmp_path / ".evagix" / "summary.md").read_text(encoding="utf-8") == "manual"


def test_scoped_conflict_does_not_leave_partial_writes(tmp_path: Path) -> None:
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend").mkdir()
    (tmp_path / "backend" / "pyproject.toml").write_text(
        '[project]\nname="backend"\ndependencies=["pytest"]\n', encoding="utf-8"
    )
    (tmp_path / "frontend" / "package.json").write_text(
        '{"scripts":{"test":"vitest"},"devDependencies":{"vitest":"latest"}}', encoding="utf-8"
    )
    (tmp_path / "backend" / "AGENTS.md").write_text("manual", encoding="utf-8")
    assert main(["scoped", str(tmp_path)]) == 1
    assert not (tmp_path / "frontend" / "AGENTS.md").exists()
