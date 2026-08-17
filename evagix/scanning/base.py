from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from evagix.agent_context_registry import generated_agent_target_paths
from evagix.model import RepoFacts
from evagix.profiles import normalize_profiles
from evagix.scanner_utils import _is_ignored_path, _is_safe_repo_path, _safe_read
from evagix.scanning.shared import _add_unique, _is_available

GENERATED_TARGETS = [
    *generated_agent_target_paths(),
    ".agent_tasks/bugfix.md",
    ".agent_tasks/refactor.md",
    ".agent_tasks/add-feature.md",
    ".agent_tasks/write-tests.md",
    ".agent_tasks/security-review.md",
]


CONFIG_FILES = [
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "uv.lock",
    "poetry.lock",
    "package.json",
    "pnpm-lock.yaml",
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "bun.lock",
    "bun.lockb",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "Makefile",
    "justfile",
    ".pre-commit-config.yaml",
    "alembic.ini",
    "nx.json",
    "turbo.json",
    "vite.config.ts",
    "vite.config.js",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "Gemfile",
    "main.tf",
    "terraform.tf",
    "Chart.yaml",
    "kustomization.yaml",
]

RISK_FOLDERS = {
    "mlruns": "mlflow artifacts directory detected; do not edit or delete experiment artifacts casually.",
    "wandb": "Weights & Biases run directory detected; avoid rewriting experiment history.",
    "checkpoints": "model checkpoints directory detected; artifact changes affect reproducibility.",
    "models": "model artifacts directory detected; artifact changes should be intentional and documented.",
    "data": "data directory detected; dataset edits are high-risk and should be documented.",
    "migrations": "database migration directory detected; schema changes need explicit review.",
    "alembic": "Alembic directory detected; migration edits are high-risk.",
}


def _infer_root_name(root: Path, warnings: list[str]) -> str:
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        data = _read_toml(pyproject, warnings, root)
        project = data.get("project", {}) if isinstance(data.get("project"), dict) else {}
        name = project.get("name") if isinstance(project, dict) else None
        if isinstance(name, str) and name.strip():
            return name.strip()

        poetry = data.get("tool", {}) if isinstance(data.get("tool"), dict) else {}
        poetry_section = poetry.get("poetry", {}) if isinstance(poetry.get("poetry"), dict) else {}
        poetry_name = poetry_section.get("name") if isinstance(poetry_section, dict) else None
        if isinstance(poetry_name, str) and poetry_name.strip():
            return poetry_name.strip()

    package_json = root / "package.json"
    if package_json.exists():
        data = _read_json(package_json, warnings, root)
        name = data.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()

    return root.name


def _apply_config_profiles(root: Path, facts: RepoFacts) -> None:
    config = root / "evagix.toml"
    if not config.exists():
        return
    data = _read_toml(config, facts.warnings, root)
    profiles_section = data.get("profiles", {}) if isinstance(data.get("profiles"), dict) else {}
    requested = profiles_section.get("profiles", []) if isinstance(profiles_section, dict) else []
    if isinstance(requested, str):
        requested = [requested]
    try:
        selected = normalize_profiles(requested)
    except ValueError as exc:
        facts.warnings.append(str(exc))
        return
    for profile in selected:
        _add_unique(facts.active_profiles, profile)


def _display_path(path: Path, root: Path | None = None) -> str:
    if root is not None:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
    return path.as_posix()


def _read_toml(path: Path, warnings: list[str] | None = None, root: Path | None = None) -> dict[str, Any]:
    text = _safe_read(path, max_chars=500_000)
    if not text:
        return {}
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        if warnings is not None:
            warnings.append(f"Invalid TOML in {_display_path(path, root)}: {getattr(exc, 'msg', str(exc))}")
        return {}


def _read_json(path: Path, warnings: list[str] | None = None, root: Path | None = None) -> dict[str, Any]:
    text = _safe_read(path, max_chars=500_000)
    if not text:
        return {}
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        if warnings is not None:
            warnings.append(f"Invalid JSON in {_display_path(path, root)}: {getattr(exc, 'msg', str(exc))}")
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _scan_top_level(root: Path, facts: RepoFacts, ignored_paths: set[str]) -> None:
    for target in GENERATED_TARGETS:
        path = root / target
        if path.exists() and _is_safe_repo_path(root, path) and not _is_ignored_path(root, path, ignored_paths):
            facts.generated_targets.append(target)
    for filename in CONFIG_FILES:
        path = root / filename
        if path.exists() and _is_safe_repo_path(root, path) and not _is_ignored_path(root, path, ignored_paths):
            _add_unique(facts.config_files, filename)
    if _is_available(root, ".pre-commit-config.yaml", ignored_paths) or _is_available(
        root, ".pre-commit-config.yml", ignored_paths
    ):
        _add_unique(facts.dev_tools, "pre-commit")
        _add_unique(facts.config_files, ".pre-commit-config.yaml")
