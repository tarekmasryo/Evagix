from __future__ import annotations

import tomllib
from pathlib import Path

from evagix.cli import main


def test_basic_python_fixture_is_fresh_and_above_threshold() -> None:
    for example in ["tests/fixtures/basic-python"]:
        assert main(["check", example]) == 0
        assert main(["doctor", example, "--fail-under", "80"]) == 0


def test_ci_runs_fixture_smoke_checks() -> None:
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "python -m evagix check tests/fixtures/basic-python" in ci
    assert "python -m evagix doctor tests/fixtures/basic-python --fail-under 80" in ci


def test_pre_commit_mypy_does_not_append_filenames() -> None:
    config = Path(".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "pass_filenames: false" in config


def test_ci_matrix_covers_primary_desktop_platforms() -> None:
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "ubuntu-latest" in ci
    assert "windows-latest" in ci
    assert "macos-latest" in ci


def test_pre_commit_ruff_matches_dev_dependency() -> None:
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dev_dependencies = metadata["project"]["optional-dependencies"]["dev"]
    ruff_dependency = next(item for item in dev_dependencies if item.startswith("ruff=="))
    ruff_version = ruff_dependency.split("==", 1)[1]
    config = Path(".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "repo: local" in config
    assert f"additional_dependencies: [ruff=={ruff_version}]" in config
    assert "- id: ruff-check" in config
    assert "- id: ruff\n" not in config


def test_ci_is_strict_and_uses_focused_fixture() -> None:
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    soft_fail = "continue-on-error" + ": true"
    assert soft_fail not in ci
    assert "python -m evagix check tests/fixtures/basic-python" in ci
    assert "evagix onboard . --force" not in ci


def test_security_audit_covers_installed_dev_and_security_toolchain() -> None:
    workflow = Path(".github/workflows/security-audit.yml").read_text(encoding="utf-8")
    assert 'python -m pip install -c constraints-release.txt -e ".[dev,security]"' in workflow
    assert "python -m ruff check evagix --select S --ignore S105,S110,S112,S404,S603,S607" in workflow
    assert "run: python -m pip_audit\n" in workflow
    assert "python -m pip_audit ." not in workflow
