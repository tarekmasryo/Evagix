from __future__ import annotations

import json
from pathlib import Path

import pytest

from evagix.cli import main
from evagix.scanner import scan_repo
from evagix.targets import TARGET_ADAPTERS
from evagix.validators import check_repo


def _repo(root: Path) -> None:
    (root / "README.md").write_text(
        "# Demo\n\nProduction-ready FastAPI service with Dockerized CI/CD monitoring and tests.\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["fastapi", "pytest", "ruff"]\n',
        encoding="utf-8",
    )
    (root / "tests").mkdir()


def test_compile_writes_agents_without_codex_and_check_detects_tamper(tmp_path: Path) -> None:
    _repo(tmp_path)
    assert TARGET_ADAPTERS["agents"].path == "AGENTS.md"
    assert "codex" not in TARGET_ADAPTERS

    assert main(["compile", str(tmp_path), "--target", "agents", "--target", "claude"]) == 0
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / "CODEX.md").exists()
    assert check_repo(tmp_path, scan_repo(tmp_path)).ok

    (tmp_path / "AGENTS.md").write_text(
        (tmp_path / "AGENTS.md").read_text(encoding="utf-8") + "\nmanual edit\n",
        encoding="utf-8",
    )
    result = check_repo(tmp_path, scan_repo(tmp_path))
    assert not result.ok
    assert "AGENTS.md" in result.tampered_targets
    assert not (tmp_path / "CODEX.md").exists()


def test_onboard_generates_pack(tmp_path: Path) -> None:
    _repo(tmp_path)
    assert main(["onboard", str(tmp_path)]) == 0
    expected = {
        "summary.md",
        "architecture.md",
        "commands.md",
        "environment.md",
        "testing.md",
        "risks.md",
        "first-pr.md",
        "contributor-guide.md",
        "report.json",
        "scorecard.json",
    }
    assert expected.issubset({path.name for path in (tmp_path / ".evagix").iterdir()})


def test_onboarding_pack_can_be_required_by_policy(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\nRun tests with `python -m pytest`.\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["pytest", "ruff"]\n',
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_demo.py").write_text("def test_demo():\n    assert True\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# Agent instructions\n\nUse `python -m pytest`.\n", encoding="utf-8")
    (tmp_path / "evagix.toml").write_text(
        '[policy]\nrequire_onboarding_pack = true\n\n[commands]\ntest = "python -m pytest"\nlint = "python -m ruff check ."\n',
        encoding="utf-8",
    )
    assert main(["doctor", str(tmp_path), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "missing-onboarding-pack" in {item["code"] for item in payload["findings"]}
