from __future__ import annotations

from pathlib import Path

from pytest import CaptureFixture

from evagix.cli import main


def _minimal_repo(root: Path) -> None:
    (root / "README.md").write_text("# Demo\n\nPython package.\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["pytest", "ruff"]\n',
        encoding="utf-8",
    )
    (root / "tests").mkdir()


def test_targets_list_includes_default_and_optional_targets(capsys: CaptureFixture[str]) -> None:
    assert main(["targets", "list"]) == 0
    out = capsys.readouterr().out
    assert "agents" in out
    assert "codex" not in out
    assert "claude" in out
    assert "continue" in out
    assert "openhands" in out
    assert "generic" in out
    assert "(optional)" in out


def test_agents_target_is_codex_compatible(capsys: CaptureFixture[str]) -> None:
    assert main(["targets", "show", "agents"]) == 0
    out = capsys.readouterr().out
    assert "AGENTS.md" in out
    assert "OpenAI Codex" in out


def test_targets_show_describes_target(capsys: CaptureFixture[str]) -> None:
    assert main(["targets", "show", "continue"]) == 0
    out = capsys.readouterr().out
    assert "Target: continue" in out
    assert ".continue/rules/evagix.md" in out


def test_compile_optional_target_only(tmp_path: Path) -> None:
    _minimal_repo(tmp_path)
    assert main(["compile", str(tmp_path), "--target", "continue"]) == 0
    assert (tmp_path / ".continue/rules/evagix.md").exists()
    assert not (tmp_path / "AGENTS.md").exists()


def test_default_sync_does_not_require_optional_targets(tmp_path: Path) -> None:
    _minimal_repo(tmp_path)
    assert main(["sync", str(tmp_path)]) == 0
    assert (tmp_path / ".evagix" / "context.md").exists()
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / ".continue/rules/evagix.md").exists()
    assert main(["check", str(tmp_path)]) == 0


def test_compile_openhands_target(tmp_path: Path) -> None:
    _minimal_repo(tmp_path)
    assert main(["compile", str(tmp_path), "--target", "openhands"]) == 0
    path = tmp_path / ".openhands" / "skills" / "repository" / "SKILL.md"
    assert path.exists()
    assert "OpenHands Repository Skill" in path.read_text(encoding="utf-8")
    assert not (tmp_path / "AGENTS.md").exists()
