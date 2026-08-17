from __future__ import annotations

from pathlib import Path
from typing import Any

from evagix.ecosystems.profiles import EcosystemDetection
from evagix.ecosystems.utils import (
    _detect_frameworks,
    _find_marker_files,
    _has_dev_extra,
    _prefix,
    _python_dependency_names,
    _read_toml,
    _rel,
    _requirements_names,
    _safe_read,
    _scope,
)
from evagix.scanning.shared import has_python_package_metadata, setup_cfg_has_package_metadata


def _detect_python(
    root: Path,
    ignored: set[str],
    warnings: list[str] | None = None,
) -> list[EcosystemDetection]:
    detections: list[EcosystemDetection] = []
    marker_names = {"pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "requirements-dev.txt"}
    candidates = [
        path
        for path in _find_marker_files(root, marker_names, ignored, warnings)
        if not _is_setuptools_generated_setup_cfg(path)
    ]
    dirs = sorted({path.parent for path in candidates})
    for directory in dirs:
        rel = _rel(directory, root)
        evidence = sorted(_rel(path, root) for path in candidates if path.parent == directory)
        lockfiles = [name for name in ("uv.lock", "poetry.lock", "pdm.lock") if (directory / name).exists()]
        evidence.extend(_prefix(rel, name) for name in lockfiles)
        pyproject = directory / "pyproject.toml"
        data = _read_toml(pyproject) if pyproject.exists() else {}
        package_metadata = (
            has_python_package_metadata(data)
            or (directory / "setup.py").exists()
            or (
                (directory / "setup.cfg").exists()
                and setup_cfg_has_package_metadata(_safe_read(directory / "setup.cfg"))
            )
        )
        has_python_source = any(directory.glob("*.py")) or any((directory / name).exists() for name in ("src", "tests"))
        has_requirements = any(path.name.startswith("requirements") for path in candidates if path.parent == directory)
        if not (package_metadata or has_python_source or has_requirements):
            continue
        deps = _python_dependency_names(data)
        for req in sorted(directory.glob("requirements*.txt"))[:5]:
            deps.update(_requirements_names(req))
        text_blob = "\n".join(sorted(deps)) + "\n" + _safe_read(pyproject).lower()
        frameworks = _detect_frameworks("python", text_blob, directory)
        tools = sorted(
            {
                tool
                for tool in ["pytest", "ruff", "mypy", "pyright", "black", "flake8"]
                if tool in text_blob or (directory / f"{tool}.ini").exists()
            }
        )
        commands, command_evidence = _python_commands(
            directory,
            root,
            data,
            deps,
            tools,
            package_metadata=package_metadata,
        )
        detections.append(
            EcosystemDetection(
                id="python",
                name="Python",
                path=rel,
                language="python",
                support="deep",
                confidence="high"
                if any(name.endswith(("pyproject.toml", "requirements.txt")) for name in evidence)
                else "medium",
                evidence=tuple(evidence),
                package_manager=_python_package_manager(directory),
                frameworks=tuple(frameworks),
                tools=tuple(tools),
                commands=commands,
                command_evidence=command_evidence,
            )
        )
    return detections


def _is_setuptools_generated_setup_cfg(path: Path) -> bool:
    if path.name != "setup.cfg":
        return False
    lines = [line.strip() for line in _safe_read(path).splitlines() if line.strip()]
    return lines == ["[egg_info]", "tag_build =", "tag_date = 0"]


def _python_commands(
    directory: Path,
    root: Path,
    data: dict[str, Any],
    deps: set[str],
    tools: list[str],
    *,
    package_metadata: bool | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    rel = _rel(directory, root)
    evidence = "pyproject.toml" if (directory / "pyproject.toml").exists() else "requirements.txt"
    evidence = _prefix(rel, evidence)
    commands: dict[str, str] = {}
    if package_metadata is None:
        package_metadata = (
            has_python_package_metadata(data)
            or (directory / "setup.py").exists()
            or (
                (directory / "setup.cfg").exists()
                and setup_cfg_has_package_metadata(_safe_read(directory / "setup.cfg"))
            )
        )
    if (directory / "uv.lock").exists():
        commands["install"] = _scope(rel, "uv sync --all-extras --dev")
    elif (directory / "pyproject.toml").exists() and package_metadata:
        commands["install"] = _scope(
            rel, 'python -m pip install -e ".[dev]"' if _has_dev_extra(data) else "python -m pip install -e ."
        )
    elif (directory / "requirements.txt").exists():
        commands["install"] = _scope(rel, "python -m pip install -r requirements.txt")
    pytest_configured = (directory / "pytest.ini").exists() or _pyproject_has_pytest_config(data)
    pytest_suite = (directory / "tests").exists() or (directory / "test").exists()
    if pytest_suite and (pytest_configured or "pytest" in deps or "pytest" in tools):
        commands["test"] = _scope(rel, "python -m pytest")
    if "ruff" in deps or "ruff" in tools or (directory / "ruff.toml").exists():
        commands["lint"] = _scope(rel, "ruff check .")
    if "mypy" in deps or "mypy" in tools or (directory / "mypy.ini").exists():
        commands["typecheck"] = _scope(rel, "mypy .")
    elif "pyright" in deps or "pyright" in tools:
        commands["typecheck"] = _scope(rel, "pyright")
    if package_metadata:
        commands["build"] = _scope(rel, "python -m build")
    return commands, {key: evidence for key in commands}


def _python_package_manager(directory: Path) -> str:
    if (directory / "uv.lock").exists():
        return "uv"
    if (directory / "poetry.lock").exists():
        return "poetry"
    if (directory / "pdm.lock").exists():
        return "pdm"
    if (directory / "requirements.txt").exists() or (directory / "requirements-dev.txt").exists():
        return "pip"
    pyproject = directory / "pyproject.toml"
    data = _read_toml(pyproject) if pyproject.exists() else {}
    setup_cfg = directory / "setup.cfg"
    if (
        has_python_package_metadata(data)
        or (directory / "setup.py").exists()
        or (setup_cfg.exists() and setup_cfg_has_package_metadata(_safe_read(setup_cfg)))
    ):
        return "pip"
    return ""


def _pyproject_has_pytest_config(data: dict[str, Any]) -> bool:
    tool = data.get("tool", {}) if isinstance(data.get("tool"), dict) else {}
    return isinstance(tool.get("pytest"), dict)
