from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from evagix.core.io import PlannedFile, WritePlan, apply_write_plan, atomic_write_text


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission semantics only")
@pytest.mark.parametrize("mode", [0o640, 0o755])
def test_atomic_write_preserves_existing_posix_mode(tmp_path: Path, mode: int) -> None:
    target = tmp_path / "context.md"
    target.write_text("old", encoding="utf-8")
    target.chmod(mode)

    atomic_write_text(target, "new", new_file_mode=0o644)

    assert target.read_text(encoding="utf-8") == "new"
    assert stat.S_IMODE(target.stat().st_mode) == mode


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission semantics only")
def test_atomic_write_defaults_new_files_to_owner_only(tmp_path: Path) -> None:
    target = tmp_path / "report.json"

    atomic_write_text(target, "{}")

    assert stat.S_IMODE(target.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission semantics only")
def test_apply_write_plan_creates_repository_files_as_readable(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    plan = WritePlan(
        root=tmp_path,
        files=(PlannedFile(relative_path="AGENTS.md", path=target, content="# Agent guidance\n"),),
    )

    assert apply_write_plan(plan) == ["AGENTS.md"]
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


def test_atomic_write_rejects_invalid_new_file_mode(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="valid POSIX permission mode"):
        atomic_write_text(tmp_path / "bad.txt", "bad", new_file_mode=-1)


def test_atomic_write_failure_preserves_target_and_cleans_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "context.md"
    target.write_text("old", encoding="utf-8")
    original_replace = Path.replace

    def fail_replace(self: Path, destination: Path) -> Path:
        if destination == target:
            raise OSError("replace blocked")
        return original_replace(self, destination)

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError, match="replace blocked"):
        atomic_write_text(target, "new", new_file_mode=0o644)

    assert target.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob(".context.md.*.tmp")) == []
