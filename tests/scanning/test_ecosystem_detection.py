from __future__ import annotations

import json
from pathlib import Path

from evagix.ecosystems.commands import (
    _command_kind,
    _node_command_supported,
    _python_command_supported,
    _strip_shell_prefix,
    command_supported_by_ecosystem,
    ecosystem_payload,
    support_matrix_rows,
)
from evagix.ecosystems.node import _detect_node, _node_package_manager
from evagix.ecosystems.profiles import EcosystemDetection
from evagix.ecosystems.python import _detect_python, _python_package_manager
from evagix.model import RepoFacts
from evagix.readme.evidence_matcher import _command_supported_by_stack
from evagix.scanner import scan_repo


def _facts(**overrides: object) -> RepoFacts:
    facts = RepoFacts(root_name="demo")
    for key, value in overrides.items():
        setattr(facts, key, value)
    return facts


def test_node_detection_package_managers_scripts_and_command_support(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "test": "vitest run",
                    "lint": "eslint .",
                    "check-types": "tsc --noEmit",
                    "build": "vite build",
                    "start": "node server.js",
                    "start:dev": "vite --host",
                },
                "dependencies": {"next": "latest"},
                "devDependencies": {"typescript": "latest", "eslint": "latest", "vitest": "latest", "vite": "latest"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: 9\n", encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text("{}\n", encoding="utf-8")

    detections = _detect_node(tmp_path, ignored=set())
    assert len(detections) == 1
    detection = detections[0]
    assert detection.package_manager == "pnpm"
    assert set(detection.commands) >= {"install", "test", "lint", "typecheck", "build", "dev", "run"}
    assert "next.js" in detection.frameworks
    assert "typescript" in detection.tools
    assert _node_command_supported("pnpm test", detections)[0] is True
    assert _node_command_supported("pnpm test:unit", detections)[0] is False
    assert _node_command_supported("npm install", [])[1] == "no package.json evidence"


def test_node_detection_invalid_json_empty_scripts_and_root_lockfile(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid"
    invalid.mkdir()
    (invalid / "package.json").write_text("{not-json", encoding="utf-8")
    assert _detect_node(invalid, ignored=set()) == []

    app = tmp_path / "apps" / "web"
    app.mkdir(parents=True)
    (tmp_path / "package.json").write_text(
        json.dumps({"workspaces": ["apps/*"]}),
        encoding="utf-8",
    )
    (tmp_path / "yarn.lock").write_text("# yarn\n", encoding="utf-8")
    (app / "package.json").write_text(json.dumps({"scripts": {}}), encoding="utf-8")
    detections = _detect_node(tmp_path, ignored=set())
    detection = next(item for item in detections if item.path == "apps/web")
    assert detection.package_manager == "yarn"
    assert detection.commands == {"install": "cd apps/web && yarn install --frozen-lockfile"}

    for lock_name, manager in [("bun.lockb", "bun"), ("package-lock.json", "npm")]:
        project = tmp_path / manager
        project.mkdir()
        (project / "package.json").write_text(json.dumps({}), encoding="utf-8")
        (project / lock_name).write_text("lock\n", encoding="utf-8")
        assert _node_package_manager(project, project) == manager


def test_python_detection_manifests_tools_commands_and_support(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.1.0"
dependencies = ["pytest", "ruff", "mypy", "fastapi"]
[project.optional-dependencies]
dev = ["pytest"]
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()

    detections = _detect_python(tmp_path, ignored=set())
    assert len(detections) == 1
    detection = detections[0]
    assert detection.package_manager == "uv"
    assert set(detection.commands) >= {"install", "test", "lint", "typecheck", "build"}
    assert "fastapi" in detection.frameworks
    facts = _facts(test_paths=[])
    assert _python_command_supported("python -m pytest", detections, facts)[0] is True
    assert _python_command_supported("ruff check .", detections, facts)[0] is True
    assert _python_command_supported("mypy .", detections, facts)[0] is True
    assert _python_command_supported("python -m build", detections, facts)[0] is True
    assert _python_command_supported("python app.py", detections, facts)[0] is True


def test_python_detection_requirements_setup_and_negative_support(tmp_path: Path) -> None:
    project = tmp_path / "pkg"
    project.mkdir()
    (project / "requirements.txt").write_text("flask\npyright\npytest\n", encoding="utf-8")
    (project / "test").mkdir()
    (project / "poetry.lock").write_text("# lock\n", encoding="utf-8")
    detections = _detect_python(tmp_path, ignored=set())
    assert detections[0].path == "pkg"
    assert detections[0].package_manager == "poetry"
    assert detections[0].commands["install"] == "cd pkg && python -m pip install -r requirements.txt"
    assert detections[0].commands["test"] == "cd pkg && python -m pytest"
    assert detections[0].commands["typecheck"] == "cd pkg && pyright"
    supported, message = _python_command_supported("pytest", [], _facts())
    assert supported is False
    assert message == "no Python packaging evidence"
    supported, message = _python_command_supported("pytest", detections, _facts(test_paths=[]))
    assert supported is True

    plain = tmp_path / "plain"
    plain.mkdir()
    assert _python_package_manager(plain) == ""
    (plain / "setup.py").write_text("from setuptools import setup\n", encoding="utf-8")
    assert _python_package_manager(plain) == "pip"


def test_readme_evidence_matcher_stack_commands(tmp_path: Path) -> None:
    assert _command_supported_by_stack(tmp_path, "npm install", _facts(package_managers=["npm"])) is True
    assert _command_supported_by_stack(tmp_path, "npm test", _facts(package_managers=["npm"])) is False
    assert _command_supported_by_stack(tmp_path, "python -m pip install -e .", _facts(languages=["python"])) is True
    assert _command_supported_by_stack(tmp_path, "pip install -r requirements.txt", _facts()) is False

    (tmp_path / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    assert _command_supported_by_stack(tmp_path, "docker build .", _facts()) is True
    (tmp_path / "Makefile").write_text("test:\n\tpytest\n", encoding="utf-8")
    assert _command_supported_by_stack(tmp_path, "make test", _facts()) is True
    assert _command_supported_by_stack(tmp_path, "unknown command", _facts()) is False


def test_readme_evidence_matcher_detects_repo_files_and_facts(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    assert _command_supported_by_stack(tmp_path, "yarn install", _facts()) is True
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n", encoding="utf-8")
    assert _command_supported_by_stack(tmp_path, "uv sync", _facts()) is False
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    assert _command_supported_by_stack(tmp_path, "uv sync", _facts()) is True
    (tmp_path / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    assert _command_supported_by_stack(tmp_path, "docker-compose up", _facts()) is True


def test_ecosystem_command_support_covers_polyglot_fallbacks_and_helpers(tmp_path: Path) -> None:
    detections = [
        EcosystemDetection(
            id="go",
            name="Go",
            path=".",
            language="go",
            support="basic",
            confidence="high",
            evidence=("go.mod",),
            commands={"test": "go test ./...", "lint": "go vet ./..."},
        ),
        EcosystemDetection(
            id="java_gradle",
            name="Gradle",
            path=".",
            language="java/kotlin",
            support="basic",
            confidence="medium",
            evidence=("build.gradle",),
            commands={"build": "./gradlew build"},
        ),
        EcosystemDetection(
            id="php",
            name="PHP / Composer",
            path="app",
            language="php",
            support="basic",
            confidence="medium",
            evidence=("app/composer.json",),
            commands={"test": "cd app && vendor/bin/phpunit"},
        ),
        EcosystemDetection(
            id="docker",
            name="Docker",
            path=".",
            language="container",
            support="general",
            confidence="medium",
            evidence=("compose.yaml",),
        ),
    ]
    facts = _facts(ecosystems=detections, config_files=["Makefile"], commands={"ci": "python -m pytest"})

    assert command_supported_by_ecosystem("$ python -m pytest", facts) == (
        True,
        "documented command matches detected repository command",
    )
    assert command_supported_by_ecosystem("go test ./...", facts)[0] is True
    assert command_supported_by_ecosystem("go vet ./...", facts) == (True, "Go command evidence from go.mod")
    assert command_supported_by_ecosystem("./gradlew build", facts)[0] is True
    assert command_supported_by_ecosystem("vendor/bin/phpunit", facts)[0] is True
    assert command_supported_by_ecosystem("docker compose up", facts)[0] is True
    assert command_supported_by_ecosystem("make test", facts)[0] is True
    assert command_supported_by_ecosystem("terraform validate", facts)[0] is False
    assert _command_kind("pnpm lint") == "lint"
    assert _command_kind("python -m mypy evagix") == "typecheck"
    assert _command_kind("vite dev") == "dev"
    assert _strip_shell_prefix("> cd app && npm test") == "npm test"

    rows = ecosystem_payload(detections)
    assert rows[0]["id"] == "go"
    assert any(row["ecosystem"] == "Unknown / unsupported ecosystems" for row in support_matrix_rows())


def test_go_and_rust_detection(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\nversion='0.1.0'\n", encoding="utf-8")
    facts = scan_repo(tmp_path)
    assert "go" in facts.languages
    assert "rust" in facts.languages
    assert facts.commands["test"] in {"go test ./...", "cargo test"}
    assert "cargo" in facts.dev_tools
