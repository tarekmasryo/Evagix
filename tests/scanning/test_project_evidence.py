from __future__ import annotations

import json
from pathlib import Path

import pytest

from evagix.model import RepoFacts
from evagix.scanning.project_evidence import (
    _derive_fallback_commands,
    _derive_warnings,
    _notebook_import_roots,
    _python_import_roots,
    _scan_folders,
    _scan_notebooks,
    _scan_polyglot_projects,
    _scan_source_imports,
)


def _facts(**overrides: object) -> RepoFacts:
    facts = RepoFacts(root_name="demo")
    for key, value in overrides.items():
        setattr(facts, key, value)
    return facts


def test_project_evidence_polyglot_and_import_edges(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.com/demo\n", encoding="utf-8")
    (tmp_path / ".golangci.yml").write_text("linters: {}\n", encoding="utf-8")
    (tmp_path / "build.gradle.kts").write_text("plugins {}\n", encoding="utf-8")
    (tmp_path / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
    (tmp_path / "composer.json").write_text(json.dumps({"scripts": {"test": "phpunit"}}), encoding="utf-8")
    (tmp_path / "Gemfile").write_text("gem 'rails'\n", encoding="utf-8")
    (tmp_path / "Rakefile").write_text("task :test\n", encoding="utf-8")

    facts = _facts()
    _scan_polyglot_projects(tmp_path, facts, set())
    assert facts.commands["lint"] == "golangci-lint run"
    assert facts.commands["build"] in {"./gradlew build", "go build ./..."}
    assert "gradle" in facts.package_managers
    assert "composer" in facts.package_managers
    assert "bundler" in facts.package_managers

    valid_py = tmp_path / "valid.py"
    valid_py.write_text("import pandas\nfrom sklearn.model_selection import train_test_split\n", encoding="utf-8")
    invalid_py = tmp_path / "invalid.py"
    invalid_py.write_text("def broken(:\n", encoding="utf-8")
    assert "pandas" in _python_import_roots(valid_py)
    assert _python_import_roots(invalid_py) == set()

    notebook = tmp_path / "analysis.ipynb"
    notebook.write_text(
        json.dumps(
            {
                "cells": [
                    {"cell_type": "markdown", "source": "# Notes"},
                    {"cell_type": "code", "source": ["import torch\n", "from matplotlib import pyplot\n"]},
                    {"cell_type": "code", "source": "def broken(:\n"},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert _notebook_import_roots(notebook) == {"torch", "matplotlib"}
    bad_notebook = tmp_path / "bad.ipynb"
    bad_notebook.write_text(json.dumps({"cells": "not-a-list"}), encoding="utf-8")
    assert _notebook_import_roots(bad_notebook) == set()

    scan_facts = _facts()
    _scan_source_imports(tmp_path, scan_facts, set())
    _scan_notebooks(tmp_path, scan_facts, set())
    assert "pandas" in scan_facts.ml_data_tools
    assert "jupyter" in scan_facts.ml_data_tools


def test_project_evidence_folder_warnings_and_fallback_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for folder in ["tests", "frontend", "data", "migrations", "node_modules", ".hidden"]:
        (tmp_path / folder).mkdir()
    facts = _facts(dev_tools=["black", "eslint"], frameworks=["streamlit", "react"], ml_data_tools=["pandas"])

    _scan_folders(tmp_path, facts, set())
    assert "tests" in facts.test_paths
    assert "frontend" in facts.folders
    assert any("migration" in flag.lower() for flag in facts.risk_flags)
    assert "node_modules" not in facts.folders

    _derive_fallback_commands(facts)
    assert facts.commands["lint"] == "black --check ."
    _derive_warnings(facts)
    assert "No test command was detected." in facts.warnings
    assert "No GitHub Actions workflow was detected." in facts.warnings
    assert any("ML/data project" in item for item in facts.warnings)
    assert any("Dashboard framework" in item for item in facts.warnings)
    assert any("Frontend project" in item for item in facts.warnings)

    blocked_root = tmp_path / "blocked"
    blocked_root.mkdir()
    original_iterdir = Path.iterdir

    def raise_oserror(self: Path) -> object:
        if self == blocked_root:
            raise OSError("cannot list")
        return original_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", raise_oserror)
    _scan_folders(blocked_root, _facts(), set())
