from __future__ import annotations

import json
from pathlib import Path

import pytest

from evagix.scanner import scan_repo
from evagix.validators import doctor_repo


def _finding_codes(root: Path) -> set[str]:
    facts = scan_repo(root)
    return {item.code for item in doctor_repo(root, facts).findings}


def test_npm_install_is_lockfile_aware(tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    (app / "package.json").write_text(
        '{"scripts":{"build":"vite build"},"dependencies":{"react":"latest","vite":"latest"}}',
        encoding="utf-8",
    )

    facts = scan_repo(tmp_path)

    assert facts.commands["app_install"] == "cd app && npm install"
    assert any("no npm lockfile" in warning.lower() for warning in facts.warnings)

    (app / "package-lock.json").write_text("{}", encoding="utf-8")
    facts = scan_repo(tmp_path)

    assert facts.commands["app_install"] == "cd app && npm ci"


def test_pytest_dependency_does_not_invent_test_suite(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["pytest"]\n',
        encoding="utf-8",
    )

    facts = scan_repo(tmp_path)

    assert "pytest" in facts.dev_tools
    assert "test" not in facts.commands
    assert facts.test_paths == []
    assert "missing-test" in _finding_codes(tmp_path)


@pytest.mark.parametrize(
    "script",
    [
        'echo "Error: no test specified" && exit 1',
        'echo "No tests configured" && exit 1',
        'echo "No tests" && exit 1',
        'throw new Error("tests not implemented")',
        'echo "test placeholder"',
    ],
)
def test_known_npm_test_placeholders_do_not_count_as_tests(tmp_path: Path, script: str) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "demo", "scripts": {"test": script}}),
        encoding="utf-8",
    )

    facts = scan_repo(tmp_path)

    assert "test" not in facts.commands
    assert "test" not in facts.command_sources
    assert any("placeholder" in warning.lower() for warning in facts.warnings)
    assert "missing-test" in _finding_codes(tmp_path)


def test_non_placeholder_npm_test_with_exit_one_is_preserved(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "demo", "scripts": {"test": "vitest run || exit 1"}}),
        encoding="utf-8",
    )

    facts = scan_repo(tmp_path)

    assert facts.commands["test"] == "npm run test"


def test_test_directory_without_pytest_evidence_does_not_invent_pytest_command(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_demo.py").write_text("import unittest\n", encoding="utf-8")

    facts = scan_repo(tmp_path)

    assert facts.test_paths == ["tests"]
    assert "test" not in facts.commands


@pytest.mark.parametrize(
    ("manager", "install_command", "test_command"),
    [
        ("pnpm", "pnpm install", "pnpm test"),
        ("yarn", "yarn install", "yarn test"),
        ("bun", "bun install", "bun run test"),
    ],
)
def test_node_package_manager_declaration_controls_commands(
    tmp_path: Path,
    manager: str,
    install_command: str,
    test_command: str,
) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "demo",
                "packageManager": f"{manager}@1.2.3",
                "scripts": {"test": "vitest run"},
            }
        ),
        encoding="utf-8",
    )

    facts = scan_repo(tmp_path)
    node = next(item for item in facts.ecosystems if item.id == "node")

    assert manager in facts.package_managers
    assert "npm" not in facts.package_managers
    assert facts.commands["install"] == install_command
    assert facts.commands["test"] == test_command
    assert node.package_manager == manager
    assert node.commands["install"] == install_command
    assert node.commands["test"] == test_command


@pytest.mark.parametrize("with_root_lock", [False, True])
def test_standalone_node_package_does_not_inherit_root_package_manager(
    tmp_path: Path,
    with_root_lock: bool,
) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "root", "packageManager": "pnpm@9.1.0"}),
        encoding="utf-8",
    )
    if with_root_lock:
        (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    standalone = tmp_path / "standalone"
    standalone.mkdir()
    (standalone / "package.json").write_text(
        json.dumps({"name": "standalone", "scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )

    facts = scan_repo(tmp_path)
    node = next(item for item in facts.ecosystems if item.id == "node" and item.path == "standalone")

    assert facts.commands["standalone_install"] == "cd standalone && npm install"
    assert facts.commands["standalone_test"] == "cd standalone && npm run test"
    assert node.package_manager == "npm"
    assert node.commands["install"] == "cd standalone && npm install"
    assert node.commands["test"] == "cd standalone && npm run test"


def test_workspace_node_package_inherits_root_manager_consistently(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "root",
                "packageManager": "pnpm@9.1.0",
                "workspaces": ["packages/*", "apps/*"],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    for relative_path in ["packages/app", "apps/admin", "standalone"]:
        package = tmp_path / relative_path
        package.mkdir(parents=True)
        (package / "package.json").write_text(
            json.dumps({"name": package.name, "scripts": {"test": "vitest run"}}),
            encoding="utf-8",
        )

    facts = scan_repo(tmp_path)
    nodes = {item.path: item for item in facts.ecosystems if item.id == "node"}

    for relative_path, command_key in [("packages/app", "packages_app"), ("apps/admin", "apps_admin")]:
        assert facts.commands[f"{command_key}_install"] == (f"cd {relative_path} && pnpm install --frozen-lockfile")
        assert facts.commands[f"{command_key}_test"] == f"cd {relative_path} && pnpm test"
        assert nodes[relative_path].package_manager == "pnpm"
        assert nodes[relative_path].commands["install"] == (f"cd {relative_path} && pnpm install --frozen-lockfile")
        assert nodes[relative_path].commands["test"] == f"cd {relative_path} && pnpm test"

    assert facts.commands["standalone_install"] == "cd standalone && npm install"
    assert facts.commands["standalone_test"] == "cd standalone && npm run test"
    assert nodes["standalone"].package_manager == "npm"
    assert nodes["standalone"].commands["install"] == "cd standalone && npm install"
    assert nodes["standalone"].commands["test"] == "cd standalone && npm run test"


def test_singular_test_directory_is_not_reported_as_plural_tests(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n[project.optional-dependencies]\ndev = ["pytest"]\n',
        encoding="utf-8",
    )
    (tmp_path / "test").mkdir()
    (tmp_path / "test" / "test_demo.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    facts = scan_repo(tmp_path)

    assert "test" in facts.test_paths
    assert "tests" not in facts.test_paths


@pytest.mark.parametrize(
    ("relative_path", "content"),
    [
        (".python-version", "3.12.2\n"),
        ("runtime.txt", "python-3.12.2\n"),
        (
            ".github/workflows/ci.yml",
            'jobs:\n  test:\n    strategy:\n      matrix:\n        python-version: ["3.11", "3.12"]\n'
            "    steps:\n      - uses: actions/setup-python@v5\n",
        ),
        ("Dockerfile", "FROM python:3.12-slim\n"),
    ],
)
def test_explicit_python_runtime_markers_are_detected(
    tmp_path: Path,
    relative_path: str,
    content: str,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    marker = tmp_path / relative_path
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(content, encoding="utf-8")

    assert "python" in scan_repo(tmp_path).runtimes


def test_requires_python_is_explicit_runtime_evidence(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n',
        encoding="utf-8",
    )

    assert "python" in scan_repo(tmp_path).runtimes


def test_python_source_alone_is_not_runtime_evidence(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("print('demo')\n", encoding="utf-8")

    facts = scan_repo(tmp_path)

    assert "python" in facts.languages
    assert "python" not in facts.runtimes


def test_empty_pytest_table_does_not_inflate_readiness(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n[tool.pytest.ini_options]\n',
        encoding="utf-8",
    )

    facts = scan_repo(tmp_path)
    report = doctor_repo(tmp_path, facts)

    assert "test" not in facts.commands
    assert facts.test_paths == []
    assert "missing-test" in {item.code for item in report.findings}
    assert report.score < 80


def test_invalid_project_metadata_is_reported_as_scanner_warning(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project\n", encoding="utf-8")
    (tmp_path / "package.json").write_text("{bad json", encoding="utf-8")

    facts = scan_repo(tmp_path)

    warnings = "\n".join(facts.warnings)
    assert "Invalid TOML in pyproject.toml" in warnings
    assert "Invalid JSON in package.json" in warnings


def test_python_install_command_does_not_use_undeclared_dev_extra(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["pytest", "ruff"]\n',
        encoding="utf-8",
    )

    facts = scan_repo(tmp_path)

    assert facts.commands["install"] == "python -m pip install -e ."


def test_python_dev_extra_install_command_uses_declared_extra(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.1.0"
dependencies = []

[project.optional-dependencies]
dev = ["pytest", "ruff"]
""".strip(),
        encoding="utf-8",
    )

    facts = scan_repo(tmp_path)

    assert facts.commands["install"] == 'python -m pip install -e ".[dev]"'


def test_scanner_ignores_transient_pytest_cache_directories(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = []\n',
        encoding="utf-8",
    )
    (tmp_path / "pytest-cache-files-abc123").mkdir()
    (tmp_path / ".coverage.tmp").mkdir()

    facts = scan_repo(tmp_path)

    assert "pytest-cache-files-abc123" not in facts.folders
    assert ".coverage.tmp" not in facts.folders
