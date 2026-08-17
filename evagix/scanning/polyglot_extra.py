from __future__ import annotations

from pathlib import Path

from evagix.model import RepoFacts
from evagix.scanning.base import _is_available
from evagix.scanning.shared import _add_unique, _set_command


def _scan_additional_polyglot_projects(
    root: Path,
    facts: RepoFacts,
    ignored_paths: set[str],
) -> None:
    """Detect extra non-Python/Node ecosystem evidence kept out of the core scanner."""
    _scan_cmake_project(root, facts, ignored_paths)
    _scan_swift_package(root, facts, ignored_paths)
    _scan_dart_or_flutter_project(root, facts, ignored_paths)


def _scan_cmake_project(root: Path, facts: RepoFacts, ignored_paths: set[str]) -> None:
    if not _is_available(root, "CMakeLists.txt", ignored_paths):
        return

    _add_unique(facts.package_managers, "cmake")
    _set_command(
        facts,
        "build",
        "cmake -S . -B build && cmake --build build",
        "CMakeLists.txt",
        "CMake project detected",
        "medium",
    )
    if _is_available(root, "tests", ignored_paths) or _is_available(root, "test", ignored_paths):
        _set_command(
            facts,
            "test",
            "ctest --test-dir build",
            "CMakeLists.txt",
            "CMake test directory detected",
            "medium",
        )


def _scan_swift_package(root: Path, facts: RepoFacts, ignored_paths: set[str]) -> None:
    if not _is_available(root, "Package.swift", ignored_paths):
        return

    _add_unique(facts.package_managers, "swiftpm")
    _set_command(
        facts,
        "install",
        "swift package resolve",
        "Package.swift",
        "Swift package detected",
        "medium",
    )
    _set_command(
        facts,
        "test",
        "swift test",
        "Package.swift",
        "Swift package detected",
        "high",
    )
    _set_command(
        facts,
        "build",
        "swift build",
        "Package.swift",
        "Swift package detected",
        "high",
    )


def _scan_dart_or_flutter_project(
    root: Path,
    facts: RepoFacts,
    ignored_paths: set[str],
) -> None:
    if not _is_available(root, "pubspec.yaml", ignored_paths):
        return

    is_flutter_repo = (root / "bin" / "flutter").exists() or (root / "packages" / "flutter").exists()
    runner = "flutter" if is_flutter_repo else "dart"

    _add_unique(facts.package_managers, "pub")
    _add_unique(facts.typecheck_tools, "dart analyzer")
    _set_command(
        facts,
        "install",
        f"{runner} pub get",
        "pubspec.yaml",
        "Dart/Flutter pubspec detected",
        "high",
    )
    if _is_available(root, "tests", ignored_paths) or _is_available(root, "test", ignored_paths):
        _set_command(
            facts,
            "test",
            f"{runner} test",
            "pubspec.yaml",
            "Dart/Flutter test directory detected",
            "medium",
        )
    _set_command(
        facts,
        "typecheck",
        f"{runner} analyze",
        "pubspec.yaml",
        "Dart analyzer evidence detected",
        "medium",
    )
