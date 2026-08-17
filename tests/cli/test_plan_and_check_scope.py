from __future__ import annotations

from pathlib import Path

from pytest import CaptureFixture

from evagix.cli import main


def _minimal_repo(root: Path) -> None:
    (root / "README.md").write_text("# Demo\n\nPython package with tests.\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["pytest", "ruff"]\n',
        encoding="utf-8",
    )
    (root / "tests").mkdir()


def test_plan_alias_matches_decide(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    _minimal_repo(tmp_path)
    assert main(["plan", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Repo Decision Plan" in out
    assert "Next best actions" in out


def test_check_output_explains_scope(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    _minimal_repo(tmp_path)
    assert main(["check", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "generated context freshness" in out
    assert "doctor, readme-audit, and eval-context" in out
