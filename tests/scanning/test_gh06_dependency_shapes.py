from __future__ import annotations

import json
from pathlib import Path

import pytest

from evagix.cli import main
from evagix.ecosystems.core import detect_ecosystems
from evagix.ecosystems.utils import _python_dependency_names
from evagix.scanner import scan_repo
from evagix.scanning.python_evidence import _collect_python_dependency_names
from evagix.validators import audit_repo


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("ecosystem_only", [False, True])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dependencies", 42),
        ("dependencies", ["react"]),
        ("dependencies", "react"),
        ("dependencies", None),
        ("dependencies", False),
        ("dependencies", []),
        ("dependencies", {"react": 42}),
        ("devDependencies", 42),
        ("peerDependencies", ["react"]),
        ("optionalDependencies", False),
    ],
)
def test_invalid_node_dependency_shapes_are_diagnosed(
    tmp_path: Path, nested: bool, ecosystem_only: bool, field: str, value: object
) -> None:
    directory = tmp_path / "packages" / "web" if nested else tmp_path
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / "package.json"
    manifest.write_text(json.dumps({"name": "demo", field: value}), encoding="utf-8")

    if ecosystem_only:
        warnings: list[str] = []
        detections = detect_ecosystems(tmp_path, warnings=warnings)
        assert not detections
    else:
        facts = scan_repo(tmp_path)
        warnings = facts.warnings
        assert "react" not in facts.frameworks
        assert not facts.ecosystems

    source = manifest.relative_to(tmp_path).as_posix()
    diagnostics = [warning for warning in warnings if "Dependency inspection incomplete" in warning]
    assert len(diagnostics) == 1
    assert source in diagnostics[0]
    assert field in diagnostics[0]
    assert "expected" in diagnostics[0]


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("ecosystem_only", [False, True])
@pytest.mark.parametrize(
    ("content", "field"),
    [
        ('[project]\nname = "demo"\ndependencies = 42\n', "project.dependencies"),
        ('[project]\nname = "demo"\ndependencies = false\n', "project.dependencies"),
        ('[project]\nname = "demo"\ndependencies = "fastapi"\n', "project.dependencies"),
        ('[project]\nname = "demo"\ndependencies = {fastapi = "*"}\n', "project.dependencies"),
        ('[project]\nname = "demo"\ndependencies = ["fastapi", 42]\n', "project.dependencies"),
        ('[project]\nname = "demo"\noptional-dependencies = 42\n', "project.optional-dependencies"),
        ('[project]\nname = "demo"\noptional-dependencies = []\n', "project.optional-dependencies"),
        ("[project.optional-dependencies]\ndev = 42\n", "project.optional-dependencies.dev"),
        ('[project.optional-dependencies]\ndev = "fastapi"\n', "project.optional-dependencies.dev"),
        ('[project.optional-dependencies]\ndev = {fastapi = "*"}\n', "project.optional-dependencies.dev"),
        ('[project.optional-dependencies]\ndev = ["fastapi", false]\n', "project.optional-dependencies.dev"),
        ("[tool.poetry]\ndependencies = 42\n", "tool.poetry.dependencies"),
        ("[tool.poetry]\ndev-dependencies = false\n", "tool.poetry.dev-dependencies"),
        ("[tool.poetry.group.dev]\ndependencies = 42\n", "tool.poetry.group.dev.dependencies"),
    ],
)
def test_invalid_python_dependency_shapes_are_diagnosed(
    tmp_path: Path, nested: bool, ecosystem_only: bool, content: str, field: str
) -> None:
    directory = tmp_path / "packages" / "api" if nested else tmp_path
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / "pyproject.toml"
    manifest.write_text(content, encoding="utf-8")

    if ecosystem_only:
        warnings: list[str] = []
        detections = detect_ecosystems(tmp_path, warnings=warnings)
        assert not detections
    else:
        facts = scan_repo(tmp_path)
        warnings = facts.warnings
        assert "fastapi" not in facts.frameworks
        assert not facts.ecosystems
        findings = audit_repo(tmp_path, facts)
        assert any(item.code == "scanner-warning" and field in item.message for item in findings)

    source = manifest.relative_to(tmp_path).as_posix()
    diagnostics = [warning for warning in warnings if "Dependency inspection incomplete" in warning]
    assert len(diagnostics) == 1
    assert source in diagnostics[0]
    assert field in diagnostics[0]
    assert "expected" in diagnostics[0]


@pytest.mark.parametrize("output_format", ["text", "json"])
@pytest.mark.parametrize(
    ("filename", "content", "field"),
    [
        ("package.json", '{"dependencies": 42}', "dependencies"),
        ("pyproject.toml", "[project]\ndependencies = 42\n", "project.dependencies"),
    ],
)
def test_scan_outputs_report_invalid_dependency_shapes_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], output_format: str, filename: str, content: str, field: str
) -> None:
    (tmp_path / filename).write_text(content, encoding="utf-8")

    assert main(["scan", str(tmp_path), "--format", output_format]) == 0
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out + captured.err
    warnings = json.loads(captured.out)["warnings"] if output_format == "json" else [captured.out]
    assert any(
        "Dependency inspection incomplete" in warning and filename in warning and field in warning
        for warning in warnings
    )


def test_valid_python_dependency_extraction_paths_are_preserved() -> None:
    data = {
        "project": {"dependencies": ["FastAPI>=0.100"], "optional-dependencies": {"dev": ["pytest>=8", "ruff"]}},
        "tool": {"poetry": {"dependencies": {"python": "^3.11", "requests": {"version": "*"}}}},
    }
    expected = {"fastapi", "pytest", "ruff", "requests"}
    assert _collect_python_dependency_names(data, []) == expected
    assert _python_dependency_names(data) == expected


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("filename", ["package.json", "pyproject.toml"])
def test_valid_dependency_manifests_remain_supported(tmp_path: Path, nested: bool, filename: str) -> None:
    directory = tmp_path / "packages" / "app" if nested else tmp_path
    directory.mkdir(parents=True, exist_ok=True)
    if filename == "package.json":
        content = json.dumps(
            {
                "name": "demo",
                "dependencies": {"react": "^19"},
                "devDependencies": {"typescript": "^5"},
                "peerDependencies": {},
                "optionalDependencies": {},
                "scripts": {"test": "vitest run"},
            }
        )
        framework, tool, command = "react", "typescript", "npm run test"
    else:
        content = (
            '[project]\nname = "demo"\ndependencies = ["fastapi"]\n[project.optional-dependencies]\ndev = ["ruff"]\n'
        )
        framework, tool, command = "fastapi", "ruff", "ruff check ."
    (directory / filename).write_text(content, encoding="utf-8")

    facts = scan_repo(tmp_path)
    warnings: list[str] = []
    detections = detect_ecosystems(tmp_path, warnings=warnings)

    assert framework in facts.frameworks
    assert tool in facts.dev_tools
    assert any(item.path == ("packages/app" if nested else ".") and framework in item.frameworks for item in detections)
    assert any(value.endswith(command) for value in facts.commands.values())
    assert not any("Dependency inspection incomplete" in warning for warning in facts.warnings + warnings)
