from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from evagix.model import RepoFacts
from evagix.scanner_utils import _has_files, _is_ignored_path, _is_safe_repo_path, _iter_files, _safe_read
from evagix.scanning.base import _is_available, _read_toml
from evagix.scanning.shared import (
    _add_unique,
    _set_command,
    has_python_package_metadata,
    setup_cfg_has_package_metadata,
)
from evagix.signatures import (
    BACKEND_PACKAGES,
    DB_PACKAGES,
    DEV_PACKAGES,
    FRAMEWORK_PACKAGES,
    LLM_PACKAGES,
    ML_DATA_PACKAGES,
    QUEUE_PACKAGES,
)


def _scan_python(root: Path, facts: RepoFacts, ignored_paths: set[str]) -> None:
    pyproject = root / "pyproject.toml"
    requirements_files = sorted(
        path
        for path in root.glob("requirements*.txt")
        if _is_safe_repo_path(root, path) and not _is_ignored_path(root, path, ignored_paths)
    )
    setup_py = root / "setup.py"
    setup_cfg = root / "setup.cfg"
    uv_lock = root / "uv.lock"
    poetry_lock = root / "poetry.lock"
    pyproject_exists = (
        pyproject.exists()
        and _is_safe_repo_path(root, pyproject)
        and not _is_ignored_path(root, pyproject, ignored_paths)
    )
    setup_py_exists = (
        setup_py.exists() and _is_safe_repo_path(root, setup_py) and not _is_ignored_path(root, setup_py, ignored_paths)
    )
    setup_cfg_exists = (
        setup_cfg.exists()
        and _is_safe_repo_path(root, setup_cfg)
        and not _is_ignored_path(root, setup_cfg, ignored_paths)
    )
    uv_lock_exists = (
        uv_lock.exists() and _is_safe_repo_path(root, uv_lock) and not _is_ignored_path(root, uv_lock, ignored_paths)
    )
    poetry_lock_exists = (
        poetry_lock.exists()
        and _is_safe_repo_path(root, poetry_lock)
        and not _is_ignored_path(root, poetry_lock, ignored_paths)
    )

    pyproject_data = _read_toml(pyproject, facts.warnings, root) if pyproject_exists else {}
    setup_cfg_package = setup_cfg_exists and setup_cfg_has_package_metadata(_safe_read(setup_cfg))
    package_metadata = has_python_package_metadata(pyproject_data) or setup_py_exists or setup_cfg_package
    has_python_sources = _has_files(root, {".py", ".ipynb"}, ignored_paths)

    python_project = bool(package_metadata or requirements_files or has_python_sources)
    if python_project:
        _add_unique(facts.languages, "python")
    project = pyproject_data.get("project", {}) if isinstance(pyproject_data.get("project"), dict) else {}
    if _has_explicit_python_runtime(root, project, ignored_paths, include_ci=python_project):
        _add_unique(facts.runtimes, "python")

    if uv_lock_exists:
        _add_unique(facts.package_managers, "uv")
    if poetry_lock_exists:
        _add_unique(facts.package_managers, "poetry")
    if requirements_files:
        _add_unique(facts.package_managers, "pip")
    if package_metadata and not any(pm in facts.package_managers for pm in ["uv", "poetry", "pip"]):
        _add_unique(facts.package_managers, "pip")

    dependency_names = _collect_python_dependency_names(pyproject_data, requirements_files)
    _classify_python_dependencies(dependency_names, facts)

    tool_section = pyproject_data.get("tool", {}) if isinstance(pyproject_data.get("tool"), dict) else {}
    _detect_python_tools_from_config(root, facts, dependency_names, tool_section, ignored_paths)

    if pyproject_exists and package_metadata:
        if "uv" in facts.package_managers:
            _set_command(facts, "install", "uv sync --all-extras --dev", "uv.lock", "uv lockfile detected", "high")
        else:
            install_command, install_detail, install_source, install_confidence = _python_editable_install_command(
                pyproject_data,
                requirements_files,
            )
            _set_command(
                facts,
                "install",
                install_command,
                install_source,
                install_detail,
                install_confidence,
            )
    elif setup_py_exists or setup_cfg_package:
        _set_command(
            facts,
            "install",
            "python -m pip install -e .",
            "setup.py/setup.cfg",
            "editable Python project detected",
            "medium",
        )
    elif requirements_files:
        first = requirements_files[0].name
        _set_command(
            facts,
            "install",
            f"python -m pip install -r {first}",
            first,
            "requirements file detected",
            "high",
        )

    if _is_available(root, "alembic.ini", ignored_paths) or _is_available(root, "alembic", ignored_paths):
        _add_unique(facts.backend_tools, "alembic")
        _set_command(facts, "migrate", "alembic upgrade head", "alembic", "Alembic detected", "high")


def _python_editable_install_command(
    pyproject_data: dict[str, Any], requirements_files: list[Path]
) -> tuple[str, str, str, str]:
    if _has_optional_dependency_group(pyproject_data, "dev"):
        return (
            'python -m pip install -e ".[dev]"',
            "editable Python project with dev extra detected",
            "pyproject.toml",
            "high",
        )

    dev_requirements = next(
        (path for path in requirements_files if path.name in {"requirements-dev.txt", "dev-requirements.txt"}), None
    )
    if dev_requirements is not None:
        return (
            f"python -m pip install -e . -r {dev_requirements.name}",
            f"editable Python project with {dev_requirements.name} detected",
            f"pyproject.toml + {dev_requirements.name}",
            "high",
        )

    return (
        "python -m pip install -e .",
        "editable Python project detected; no dev extra or dev requirements file found",
        "pyproject.toml",
        "medium",
    )


def _has_optional_dependency_group(pyproject_data: dict[str, Any], group: str) -> bool:
    project = pyproject_data.get("project", {}) if isinstance(pyproject_data.get("project"), dict) else {}
    optional = (
        project.get("optional-dependencies", {}) if isinstance(project.get("optional-dependencies"), dict) else {}
    )
    if group in optional:
        return True

    poetry = (
        pyproject_data.get("tool", {}).get("poetry", {}) if isinstance(pyproject_data.get("tool", {}), dict) else {}
    )
    if isinstance(poetry, dict):
        poetry_extras = poetry.get("extras", {}) if isinstance(poetry.get("extras"), dict) else {}
        poetry_groups = poetry.get("group", {}) if isinstance(poetry.get("group"), dict) else {}
        if group in poetry_extras or group in poetry_groups:
            return True

    return False


def _detect_python_tools_from_config(
    root: Path,
    facts: RepoFacts,
    dependency_names: set[str],
    tool_section: dict[str, Any],
    ignored_paths: set[str],
) -> None:
    has_pytest_config = _is_available(root, "pytest.ini", ignored_paths)
    has_ruff_config = _is_available(root, "ruff.toml", ignored_paths)
    has_mypy_config = _is_available(root, "mypy.ini", ignored_paths)
    pytest_source = "pyproject.toml/pytest.ini" if has_pytest_config or "pytest" in tool_section else "dependency files"
    ruff_source = "pyproject.toml/ruff.toml" if has_ruff_config or "ruff" in tool_section else "dependency files"
    mypy_source = "pyproject.toml/mypy.ini" if has_mypy_config or "mypy" in tool_section else "dependency files"

    pytest_configured = has_pytest_config or "pytest" in tool_section
    detected_test_paths = _detect_python_test_paths(root, tool_section, ignored_paths)
    if pytest_configured or "pytest" in dependency_names:
        _add_unique(facts.dev_tools, "pytest")
    for test_path in detected_test_paths:
        _add_unique(facts.test_paths, test_path)
    if detected_test_paths and (pytest_configured or "pytest" in dependency_names):
        _set_command(
            facts,
            "test",
            "pytest",
            pytest_source if pytest_configured else detected_test_paths[0],
            "pytest configuration or test suite detected",
            "high" if pytest_configured else "medium",
            priority=60 if pytest_configured else 50,
            status="declared",
        )
    if has_ruff_config or "ruff" in tool_section or "ruff" in dependency_names:
        _add_unique(facts.dev_tools, "ruff")
        _add_unique(facts.lint_tools, "ruff")
        _set_command(
            facts,
            "lint",
            "ruff check .",
            ruff_source,
            "ruff detected",
            "high" if has_ruff_config or "ruff" in tool_section else "low",
            priority=60 if has_ruff_config or "ruff" in tool_section else 30,
            status="declared" if has_ruff_config or "ruff" in tool_section else "inferred",
        )
    if "flake8" in dependency_names:
        _add_unique(facts.dev_tools, "flake8")
        _add_unique(facts.lint_tools, "flake8")
        if "lint" not in facts.commands:
            _set_command(facts, "lint", "flake8 .", "dependency files", "flake8 detected", "medium")
    if "pylint" in dependency_names:
        _add_unique(facts.dev_tools, "pylint")
        _add_unique(facts.lint_tools, "pylint")
        if "lint" not in facts.commands:
            _set_command(facts, "lint", "pylint .", "dependency files", "pylint detected", "medium")
    if "black" in tool_section or "black" in dependency_names:
        source = "pyproject.toml" if "black" in tool_section else "dependency files"
        _add_unique(facts.dev_tools, "black")
        if "lint" not in facts.commands:
            _add_unique(facts.lint_tools, "black")
            _set_command(facts, "lint", "black --check .", source, "black detected", "medium")
        if "format" not in facts.commands:
            _set_command(facts, "format", "black .", source, "black detected", "medium")
    if "isort" in tool_section or "isort" in dependency_names:
        source = "pyproject.toml" if "isort" in tool_section else "dependency files"
        _add_unique(facts.dev_tools, "isort")
        if "format" not in facts.commands:
            _set_command(facts, "format", "isort .", source, "isort detected", "medium")
    if has_mypy_config or "mypy" in tool_section or "mypy" in dependency_names:
        _add_unique(facts.dev_tools, "mypy")
        _add_unique(facts.typecheck_tools, "mypy")
        _set_command(
            facts,
            "typecheck",
            "mypy .",
            mypy_source,
            "mypy detected",
            "high" if has_mypy_config or "mypy" in tool_section else "low",
            priority=60 if has_mypy_config or "mypy" in tool_section else 30,
            status="declared" if has_mypy_config or "mypy" in tool_section else "inferred",
        )
    if "pyright" in tool_section or "pyright" in dependency_names:
        source = "pyproject.toml" if "pyright" in tool_section else "dependency files"
        _add_unique(facts.dev_tools, "pyright")
        _add_unique(facts.typecheck_tools, "pyright")
        _set_command(facts, "typecheck", "pyright", source, "pyright detected", "high")
    for security_tool in ["bandit", "pip-audit"]:
        if security_tool in dependency_names:
            _add_unique(facts.dev_tools, security_tool)


def _has_explicit_python_runtime(
    root: Path, project: dict[str, Any], ignored_paths: set[str], *, include_ci: bool
) -> bool:
    if project.get("requires-python") or _is_available(root, ".python-version", ignored_paths):
        return True
    runtime_txt = root / "runtime.txt"
    runtime_text = _safe_read(runtime_txt, max_chars=20_000)
    if _is_available(root, "runtime.txt", ignored_paths) and re.search(r"(?im)^\s*python(?:-|\s|$)", runtime_text):
        return True
    dockerfile = root / "Dockerfile"
    docker_text = _safe_read(dockerfile, max_chars=120_000)
    if _is_available(root, "Dockerfile", ignored_paths) and re.search(
        r"(?im)^\s*FROM\s+(?:--platform=\S+\s+)?python(?=[:@\s])", docker_text
    ):
        return True
    if not include_ci:
        return False
    workflows = root / ".github" / "workflows"
    if not workflows.is_dir() or _is_ignored_path(root, workflows, ignored_paths):
        return False
    for workflow in sorted([*workflows.glob("*.yml"), *workflows.glob("*.yaml")])[:40]:
        if not _is_safe_repo_path(root, workflow) or _is_ignored_path(root, workflow, ignored_paths):
            continue
        text = _safe_read(workflow, max_chars=120_000).lower()
        if "actions/setup-python@" in text or re.search(r"(?m)^\s*python-version\s*:", text):
            return True
    return False


def _detect_python_test_paths(
    root: Path,
    tool_section: dict[str, Any],
    ignored_paths: set[str],
) -> list[str]:
    paths: list[str] = []
    pytest_options = (
        tool_section.get("pytest", {}).get("ini_options", {}) if isinstance(tool_section.get("pytest"), dict) else {}
    )
    configured = pytest_options.get("testpaths", []) if isinstance(pytest_options, dict) else []
    for value in configured if isinstance(configured, list) else []:
        relative = str(value).strip().replace("\\", "/")
        if relative and _is_available(root, relative, ignored_paths):
            _add_unique(paths, relative)
    for relative in ("tests", "test"):
        if _is_available(root, relative, ignored_paths):
            _add_unique(paths, relative)
    if paths:
        return paths
    for path in _iter_files(root, {".py"}, limit=200, ignored_paths=ignored_paths):
        if path.name.startswith("test_") or path.name.endswith("_test.py"):
            _add_unique(paths, path.parent.relative_to(root).as_posix() or ".")
            break
    return paths


def _collect_python_dependency_names(data: dict[str, Any], requirements_files: list[Path]) -> set[str]:
    names: set[str] = set()
    project = data.get("project", {}) if isinstance(data.get("project"), dict) else {}
    tool = data.get("tool", {}) if isinstance(data.get("tool"), dict) else {}
    poetry = tool.get("poetry", {}) if isinstance(tool.get("poetry"), dict) else {}

    for spec in project.get("dependencies", []) or []:
        name = _normalize_package_name(str(spec))
        if name:
            names.add(name)

    optional_deps = project.get("optional-dependencies", {})
    if isinstance(optional_deps, dict):
        for values in optional_deps.values():
            for spec in values or []:
                name = _normalize_package_name(str(spec))
                if name:
                    names.add(name)

    poetry_deps = poetry.get("dependencies", {}) if isinstance(poetry, dict) else {}
    poetry_group = poetry.get("group", {}) if isinstance(poetry.get("group", {}), dict) else {}
    poetry_dev = (
        poetry_group.get("dev", {}).get("dependencies", {}) if isinstance(poetry_group.get("dev", {}), dict) else {}
    )
    for dep_map in [poetry_deps, poetry_dev]:
        if isinstance(dep_map, dict):
            for name in dep_map:
                if name.lower() != "python":
                    names.add(_canonical_dep_key(name))

    for req_file in requirements_files:
        for line in _safe_read(req_file).splitlines():
            name = _normalize_package_name(line)
            if name:
                names.add(name)
    return names


def _normalize_package_name(spec: str) -> str:
    raw = spec.strip()
    if not raw or raw.startswith("#") or raw.startswith("-"):
        return ""
    raw = raw.split("#", 1)[0].strip()
    raw = raw.split(";", 1)[0].strip()
    raw = raw.split("[", 1)[0].strip()
    match = re.match(r"([A-Za-z0-9_.-]+)", raw)
    return _canonical_dep_key(match.group(1)) if match else ""


def _canonical_dep_key(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _classify_python_dependencies(names: set[str], facts: RepoFacts) -> None:
    for name in sorted(names):
        import_style = name.replace("-", "_")
        for key in {name, import_style}:
            if key in FRAMEWORK_PACKAGES:
                _add_unique(facts.frameworks, FRAMEWORK_PACKAGES[key])
            if key in BACKEND_PACKAGES:
                _add_unique(facts.backend_tools, BACKEND_PACKAGES[key])
            if key in LLM_PACKAGES:
                _add_unique(facts.llm_tools, LLM_PACKAGES[key])
            if key in ML_DATA_PACKAGES:
                _add_unique(facts.ml_data_tools, ML_DATA_PACKAGES[key])
            if key in DEV_PACKAGES:
                _add_unique(facts.dev_tools, DEV_PACKAGES[key])
            if key in DB_PACKAGES:
                value = DB_PACKAGES[key]
                if value == "sqlalchemy":
                    _add_unique(facts.frameworks, value)
                    _add_unique(facts.backend_tools, value)
                else:
                    _add_unique(facts.databases, value)
            if key in QUEUE_PACKAGES:
                _add_unique(facts.queues, QUEUE_PACKAGES[key])
