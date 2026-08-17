from __future__ import annotations

import json
from pathlib import Path

import pytest

from evagix.cli import main
from evagix.context.eval_engine import _collect_present_generated_targets
from evagix.context.files import _agent_context_files
from evagix.scanner import scan_repo
from evagix.scanners.agent_files import discover_agent_files
from evagix.scanners.mcp import discover_mcp_configs


def _symlink_dir(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"directory symlinks are not available in this environment: {exc}")


def test_init_ci_rejects_symlinked_github_dir(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    _symlink_dir(repo / ".github", outside)

    result = main(["init-ci", str(repo), "--force"])

    assert result != 0
    assert not (outside / "workflows" / "evagix.yml").exists()


def test_agent_context_not_read_through_symlinked_github_parent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    (outside / "copilot-instructions.md").write_text("outside context\n", encoding="utf-8")
    _symlink_dir(repo / ".github", outside)

    assert _agent_context_files(repo) == []
    assert discover_agent_files(repo) == []


def test_generated_context_not_collected_through_symlinked_evagix_parent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    (outside / "context.md").write_text("evagix:generated\nevagix:fingerprint=abc\n", encoding="utf-8")
    _symlink_dir(repo / ".evagix", outside)

    present, missing, texts = _collect_present_generated_targets(repo)

    assert ".evagix/context.md" not in present
    assert texts == []


def test_mcp_config_not_discovered_through_symlinked_parent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    (outside / "mcp.json").write_text('{"servers": {}}\n', encoding="utf-8")
    _symlink_dir(repo / ".cursor", outside)

    assert discover_mcp_configs(repo) == []


def test_symlinked_repository_root_matches_real_scan_doctor_and_check(tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.1.0"
dependencies = []

[project.optional-dependencies]
dev = ["pytest", "ruff", "mypy"]
""".strip(),
        encoding="utf-8",
    )
    (repo / "evagix.toml").write_text("[policy]\nfail_under = 0\n", encoding="utf-8")
    (workflows / "ci.yml").write_text("name: CI\njobs: {}\n", encoding="utf-8")
    link = tmp_path / "repo-link"
    _symlink_dir(link, repo)

    assert scan_repo(link).to_dict() == scan_repo(repo).to_dict()

    assert main(["doctor", str(repo), "--format", "json"]) == 0
    real_doctor = json.loads(capsys.readouterr().out)
    assert main(["doctor", str(link), "--format", "json"]) == 0
    linked_doctor = json.loads(capsys.readouterr().out)
    assert linked_doctor == real_doctor
    codes = {finding["code"] for finding in linked_doctor["findings"]}
    assert "missing-ci" not in codes
    assert "readme.read-error" not in codes

    assert main(["check", str(repo)]) == 0
    real_check = capsys.readouterr().out
    assert main(["check", str(link)]) == 0
    assert capsys.readouterr().out == real_check
