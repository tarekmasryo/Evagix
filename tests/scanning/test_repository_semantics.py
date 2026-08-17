from __future__ import annotations

from pathlib import Path

from evagix.commands.common import _facts
from evagix.scanner import scan_repo
from evagix.scanning.shared import _set_command
from evagix.validators import doctor_repo


def test_tool_only_pyproject_does_not_invent_package_commands(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n", encoding="utf-8")

    facts = scan_repo(tmp_path)

    assert "ruff" in facts.dev_tools
    assert "install" not in facts.commands
    assert "build" not in facts.commands
    assert "pip" not in facts.package_managers
    assert "python" not in facts.languages


def test_taxonomy_separates_language_runtime_ci_container_and_infrastructure(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n',
        encoding="utf-8",
    )
    (tmp_path / "Dockerfile").write_text("FROM python:3.11-slim\n", encoding="utf-8")
    (tmp_path / "main.tf").write_text('terraform { required_version = ">= 1.5" }\n', encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: CI\non: [push]\njobs: {}\n", encoding="utf-8")

    facts = scan_repo(tmp_path)

    assert facts.languages == ["python"]
    assert "python" in facts.runtimes
    assert "pip" in facts.package_managers
    assert "github-actions" in facts.ci_platforms
    assert "docker" in facts.container_platforms
    assert "terraform" in facts.infrastructure_tools
    assert "ci" not in facts.languages
    assert "docker" not in facts.languages
    assert "terraform" not in facts.languages
    assert "github-actions" not in facts.package_managers
    assert "docker" not in facts.package_managers
    assert "terraform" not in facts.package_managers
    assert not any(item.kind in {"github_actions", "docker", "terraform"} for item in facts.subprojects)


def test_command_precedence_is_explicit_and_scope_local(tmp_path: Path) -> None:
    facts = scan_repo(tmp_path)
    _set_command(facts, "test", "pytest", "dependencies", "dependency inference", "low", priority=20)
    _set_command(facts, "test", "make test", "Makefile", "explicit target", "high", priority=60)
    _set_command(facts, "test", "pytest -q", "ci.yml", "exact CI command", "high", priority=80)
    _set_command(facts, "frontend_test", "npm test", "frontend/package.json", "declared script", "high", priority=60)
    _set_command(facts, "test", "python -m pytest", "evagix.toml", "configured override", "high", priority=100)

    assert facts.commands["test"] == "python -m pytest"
    assert facts.commands["frontend_test"] == "npm test"


def test_inferred_test_command_receives_reduced_readiness_credit(tmp_path: Path) -> None:
    facts = scan_repo(tmp_path)
    _set_command(
        facts,
        "test",
        "pytest",
        "dependencies",
        "dependency inference",
        "low",
        priority=20,
        status="inferred",
    )

    findings = {item.code: item for item in doctor_repo(tmp_path, facts).findings}

    assert "missing-test" not in findings
    assert findings["inferred-test-command"].penalty == 12


def test_configured_command_has_high_consistent_confidence(tmp_path: Path) -> None:
    (tmp_path / "evagix.toml").write_text('[commands]\ntest = "python -m pytest"\n', encoding="utf-8")

    facts, _ = _facts(tmp_path)

    assert facts.command_sources["test"].confidence == "high"
    assert facts.command_sources["test"].confidence_score == 0.9
