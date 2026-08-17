import json
from pathlib import Path

import pytest

from evagix.scanner import scan_repo


def test_scan_detects_python_pytest_ruff(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.1.0"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.6"]
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()

    facts = scan_repo(tmp_path)

    assert "python" in facts.languages
    assert facts.commands["test"] == "pytest"
    assert facts.commands["lint"] == "ruff check ."
    assert "tests" in facts.test_paths


def test_python_install_uses_dev_requirements_when_no_dev_extra(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.1.0"
dependencies = []
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "requirements-dev.txt").write_text("pytest\nruff\n", encoding="utf-8")

    facts = scan_repo(tmp_path)

    assert facts.commands["install"] == "python -m pip install -e . -r requirements-dev.txt"


def test_python_install_supports_setup_project(tmp_path: Path) -> None:
    (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup(name='demo')\n", encoding="utf-8")

    facts = scan_repo(tmp_path)

    assert facts.commands["install"] == "python -m pip install -e ."


def test_scan_uses_package_metadata_for_stable_root_name(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "stable-demo"
version = "0.1.0"
""".strip(),
        encoding="utf-8",
    )

    facts = scan_repo(tmp_path)

    assert facts.root_name == "stable-demo"


def test_scan_uses_poetry_metadata_for_stable_root_name(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.poetry]
name = "poetry-demo"
version = "0.1.0"
""".strip(),
        encoding="utf-8",
    )

    facts = scan_repo(tmp_path)

    assert facts.root_name == "poetry-demo"


def test_scan_uses_package_json_name_when_python_metadata_is_absent(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"name": "node-demo"}), encoding="utf-8")

    facts = scan_repo(tmp_path)

    assert facts.root_name == "node-demo"


def test_scan_detects_nested_frontend_package(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "build": "vite build",
                    "lint": "eslint .",
                    "typecheck": "tsc --noEmit",
                },
                "dependencies": {"react": "latest", "vite": "latest"},
                "devDependencies": {"typescript": "latest", "eslint": "latest"},
            }
        ),
        encoding="utf-8",
    )
    (frontend / "package-lock.json").write_text("{}", encoding="utf-8")

    facts = scan_repo(tmp_path)

    assert "javascript/typescript" in facts.languages
    assert "react" in facts.frontend_tools
    assert "vite" in facts.frontend_tools
    assert facts.commands["frontend_build"] == "cd frontend && npm run build"
    assert facts.commands["frontend_lint"] == "cd frontend && npm run lint"
    assert facts.commands["frontend_typecheck"] == "cd frontend && npm run typecheck"


def test_scan_detects_backend_llm_database_queue_and_risk_rules(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        "\n".join(
            [
                "fastapi",
                "sqlalchemy",
                "alembic",
                "celery",
                "redis",
                "langchain",
                "sentence-transformers",
                "torch",
                "numpy",
                "black",
                "pytest",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "alembic").mkdir()
    (tmp_path / "mlruns").mkdir()
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  postgres:\n    image: postgres:16\n  redis:\n    image: redis:7\n",
        encoding="utf-8",
    )

    facts = scan_repo(tmp_path)

    assert "fastapi" in facts.frameworks
    assert "sqlalchemy" in facts.frameworks
    assert "alembic" in facts.backend_tools
    assert "langchain" in facts.llm_tools
    assert "sentence-transformers" in facts.ml_data_tools
    assert "postgres" in facts.databases
    assert "redis" in facts.queues
    assert facts.commands["migrate"] == "alembic upgrade head"
    assert any("mlflow artifacts" in flag for flag in facts.risk_flags)


def test_makefile_commands_prefer_repo_entrypoints(tmp_path: Path) -> None:
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
    (tmp_path / "Makefile").write_text("test:\n\tpytest -q\nrun:\n\tstreamlit run app.py\n", encoding="utf-8")

    facts = scan_repo(tmp_path)

    assert facts.commands["test"] == "make test"
    assert facts.commands["run"] == "make run"


def test_scan_skips_symlinked_paths_outside_repo(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside_js_project"
    outside.mkdir(exist_ok=True)
    (outside / "package.json").write_text(json.dumps({"dependencies": {"react": "latest"}}), encoding="utf-8")
    link = tmp_path / "linked-outside"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not available in this environment")

    facts = scan_repo(tmp_path)

    assert "javascript/typescript" not in facts.languages
    assert "react" not in facts.frontend_tools


def test_scan_does_not_read_sensitive_env_like_files(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("FASTAPI_SECRET=fastapi\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")

    facts = scan_repo(tmp_path)

    assert "fastapi" not in facts.frameworks
    assert "python" not in facts.languages


def test_scan_does_not_infer_docker_from_workflow_path_filters(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        """
name: CI
on:
  pull_request:
    paths:
      - "Dockerfile"
      - "docker-compose*.yml"
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python -m pytest
""".strip(),
        encoding="utf-8",
    )

    facts = scan_repo(tmp_path)

    assert "github-actions" in facts.dev_tools
    assert "docker" not in facts.dev_tools
    assert "docker" not in facts.runtimes


def test_scan_detects_docker_from_real_workflow_command(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        """
name: Docker
jobs:
  image:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build .
""".strip(),
        encoding="utf-8",
    )

    facts = scan_repo(tmp_path)

    assert "docker" in facts.dev_tools
