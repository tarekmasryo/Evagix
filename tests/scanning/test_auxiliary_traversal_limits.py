from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import evagix.scanner_utils as scanner_utils
from evagix.ecosystems.profiles import ECOSYSTEM_PROFILES
from evagix.ecosystems.utils import _detect_frameworks
from evagix.model import RepoFacts
from evagix.readme import claim_checks, claim_text_scan
from evagix.repository_intent import (
    _docs_heavy_layout,
    python_cli_entrypoint_evidence,
    python_package_evidence,
)
from evagix.scanner_utils import TraversalDiagnostics


class _StaticScandir:
    def __init__(self, entries: list[os.DirEntry[str]]) -> None:
        self._entries = iter(entries)

    def __enter__(self) -> _StaticScandir:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def __iter__(self) -> _StaticScandir:
        return self

    def __next__(self) -> os.DirEntry[str]:
        return next(self._entries)


def _force_scandir_name_order(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    real_scandir = os.scandir

    def sorted_scandir(path: Path) -> _StaticScandir:
        with real_scandir(path) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name)
        return _StaticScandir(entries)

    monkeypatch.setattr(scanner_utils.os, "scandir", sorted_scandir)


def _write_files(root: Path, names: list[str]) -> None:
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ordinary content\n", encoding="utf-8")


def test_readme_text_search_reports_exhausted_traversal(monkeypatch, tmp_path: Path) -> None:
    _force_scandir_name_order(monkeypatch)
    _write_files(tmp_path, ["a.txt", "b.txt", "z-target.txt"])
    (tmp_path / "z-target.txt").write_text("needle\n", encoding="utf-8")
    monkeypatch.setattr(claim_text_scan, "MAX_TEXT_SCAN_VISITED_ENTRIES", 2)

    diagnostics = TraversalDiagnostics(max_visited_entries=2)
    found = claim_text_scan._repo_text_contains(tmp_path, ["needle"], diagnostics=diagnostics)

    assert found is False
    assert diagnostics.truncated is True
    assert "results may be incomplete" in diagnostics.warning("README evidence search")


def test_readme_text_search_reports_candidate_limit(monkeypatch, tmp_path: Path) -> None:
    _write_files(tmp_path, [f"{index:03d}.txt" for index in range(4)])
    (tmp_path / "003.txt").write_text("needle\n", encoding="utf-8")
    monkeypatch.setattr(claim_text_scan, "MAX_TEXT_SCAN_RESULTS", 3)

    diagnostics = TraversalDiagnostics()
    found = claim_text_scan._repo_text_contains(tmp_path, ["needle"], diagnostics=diagnostics)

    assert found is False
    assert diagnostics.result_limit_reached is True
    assert "result limit was reached" in diagnostics.warning("README evidence search")


def test_named_file_limit_requires_an_additional_matching_result(tmp_path: Path) -> None:
    limit = 2
    for count, expected_limit_reached in ((limit - 1, False), (limit, False), (limit + 1, True)):
        root = tmp_path / f"named-{count}"
        _write_files(root, [f"project-{index}/package.json" for index in range(count)])
        diagnostics = TraversalDiagnostics()

        matches = scanner_utils._iter_named_files(
            root,
            {"package.json"},
            limit=limit,
            diagnostics=diagnostics,
        )

        assert len(matches) == min(count, limit)
        assert diagnostics.result_limit_reached is expected_limit_reached


def test_suffix_file_limit_requires_an_additional_matching_result(tmp_path: Path) -> None:
    limit = 2
    for count, expected_limit_reached in ((limit - 1, False), (limit, False), (limit + 1, True)):
        root = tmp_path / f"suffix-{count}"
        _write_files(root, [f"file-{index}.py" for index in range(count)])
        diagnostics = TraversalDiagnostics()

        matches = scanner_utils._iter_files(
            root,
            {".py"},
            limit=limit,
            diagnostics=diagnostics,
        )

        assert len(matches) == min(count, limit)
        assert diagnostics.result_limit_reached is expected_limit_reached


def test_python_package_evidence_reports_exhausted_traversal(monkeypatch, tmp_path: Path) -> None:
    _force_scandir_name_order(monkeypatch)
    _write_files(tmp_path, ["a.txt", "b.txt", "pyproject.toml"])
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    monkeypatch.setattr("evagix.repository_intent._MAX_SCAN_ENTRIES", 2)

    evidence, missing = python_package_evidence(tmp_path)

    assert evidence == []
    assert any("Python package evidence discovery was truncated" in item for item in missing)


def test_python_cli_evidence_reports_exhausted_traversal(monkeypatch, tmp_path: Path) -> None:
    _force_scandir_name_order(monkeypatch)
    _write_files(tmp_path, ["a.txt", "b.txt", "pyproject.toml"])
    (tmp_path / "pyproject.toml").write_text("[project.scripts]\ndemo='demo:main'\n", encoding="utf-8")
    monkeypatch.setattr("evagix.repository_intent._MAX_SCAN_ENTRIES", 2)

    evidence, missing = python_cli_entrypoint_evidence(tmp_path)

    assert evidence == []
    assert any("Python CLI entrypoint discovery was truncated" in item for item in missing)


def test_docs_layout_adds_repo_warning_when_scan_is_truncated(monkeypatch, tmp_path: Path) -> None:
    _write_files(tmp_path, ["a.md", "b.md", "c.md"])
    monkeypatch.setattr("evagix.repository_intent._MAX_DOCS_LAYOUT_ENTRIES", 2)
    facts = RepoFacts(root_name="docs")

    _docs_heavy_layout(tmp_path, facts)

    assert any("Documentation-heavy layout detection was truncated" in item for item in facts.warnings)


def test_py_typed_discovery_reports_exhausted_traversal(monkeypatch, tmp_path: Path) -> None:
    _force_scandir_name_order(monkeypatch)
    _write_files(tmp_path, ["a.txt", "b.txt", "z_package/py.typed"])
    monkeypatch.setattr(claim_checks, "MAX_PY_TYPED_SCAN_ENTRIES", 2)
    facts = RepoFacts(root_name="demo", languages=["python"], typecheck_tools=["mypy"])

    evidence, missing = claim_checks._check_typed(tmp_path, facts)

    assert "py.typed marker detected" not in evidence
    assert any("py.typed marker discovery was truncated" in item for item in missing)


def test_framework_filename_detection_does_not_enumerate_directory(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "next.config.ts").write_text("export default {}\n", encoding="utf-8")

    def fail_iterdir(self: Path):  # pragma: no cover - failure path only
        raise AssertionError(f"unexpected unbounded directory enumeration: {self}")

    monkeypatch.setattr(Path, "iterdir", fail_iterdir)

    frameworks = _detect_frameworks("node", "", tmp_path)

    assert "next.js" in frameworks
    assert ECOSYSTEM_PROFILES["node"].id == "node"
