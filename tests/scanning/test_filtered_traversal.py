from __future__ import annotations

from pathlib import Path

import pytest

from evagix import scanner_utils
from evagix.scanner_utils import TraversalDiagnostics


def _discover(root: Path, mode: str, diagnostics: TraversalDiagnostics) -> list[Path]:
    if mode == "name":
        return scanner_utils._iter_named_files(
            root, {"target.py", "private.key"}, ignored_paths={"ignored"}, diagnostics=diagnostics
        )
    return scanner_utils._iter_files(
        root, {".py", ".key"}, limit=200, ignored_paths={"ignored"}, diagnostics=diagnostics
    )


@pytest.mark.parametrize("mode", ["name", "suffix"])
def test_filter_retains_boundary_secret_and_directory_exclusions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    for name in (
        "target.py",
        "noise.txt",
        "private.key",
        "blocked/target.py",
        "ignored/target.py",
        "fixtures/target.py",
    ):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("data\n", encoding="utf-8")
    inspected: list[str] = []
    real_check = scanner_utils._is_safe_repo_path

    def check_boundary(root: Path, path: Path) -> bool:
        relative = path.relative_to(root).as_posix()
        inspected.append(relative)
        return relative != "blocked/target.py" and real_check(root, path)

    monkeypatch.setattr(scanner_utils, "_is_safe_repo_path", check_boundary)
    diagnostics = TraversalDiagnostics()

    assert _discover(tmp_path, mode, diagnostics) == [tmp_path / "target.py"]
    assert set(inspected) == {"target.py", "private.key", "blocked/target.py"}
    assert diagnostics.visited_files == 4  # Includes rejected and sensitive files.
    assert diagnostics.incomplete is False


@pytest.mark.parametrize("mode", ["name", "suffix"])
def test_filtered_files_still_exhaust_traversal_budget(tmp_path: Path, mode: str) -> None:
    for index in range(12):
        (tmp_path / f"noise-{index}.txt").write_text("data\n", encoding="utf-8")
    diagnostics = TraversalDiagnostics(max_visited_entries=5)

    assert _discover(tmp_path, mode, diagnostics) == []
    assert diagnostics.visited_entries == diagnostics.visited_files == 5
    assert diagnostics.truncated is True
    assert diagnostics.incomplete is True


@pytest.mark.parametrize("mode", ["name", "suffix"])
def test_filtered_discovery_preserves_directory_read_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    def deny_read(*args: object, **kwargs: object) -> object:
        raise PermissionError("unreadable directory")

    monkeypatch.setattr(scanner_utils, "_read_bounded_directory_entries", deny_read)
    diagnostics = TraversalDiagnostics()

    assert _discover(tmp_path, mode, diagnostics) == []
    assert diagnostics.read_errors == 1
    assert diagnostics.incomplete is True


@pytest.mark.parametrize("mode", ["name", "suffix"])
def test_filtered_discovery_does_not_follow_matching_symlink(tmp_path: Path, mode: str) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("data\n", encoding="utf-8")
    try:
        (repository / "target.py").symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"file symlinks unavailable: {exc}")

    assert _discover(repository, mode, TraversalDiagnostics()) == []
