from __future__ import annotations

from pathlib import Path

from evagix.model import RepoFacts
from evagix.scanning.polyglot_extra import _scan_additional_polyglot_projects


def test_cmake_project_sets_build_and_test_commands(tmp_path: Path) -> None:
    (tmp_path / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    facts = RepoFacts(root_name="demo")

    _scan_additional_polyglot_projects(tmp_path, facts, set())

    assert "cmake" in facts.package_managers
    assert facts.commands["build"] == "cmake -S . -B build && cmake --build build"
    assert facts.commands["test"] == "ctest --test-dir build"


def test_swift_package_sets_swiftpm_commands(tmp_path: Path) -> None:
    (tmp_path / "Package.swift").write_text("// swift-tools-version: 6.0\n", encoding="utf-8")
    facts = RepoFacts(root_name="demo")

    _scan_additional_polyglot_projects(tmp_path, facts, set())

    assert "swiftpm" in facts.package_managers
    assert facts.commands["install"] == "swift package resolve"
    assert facts.commands["build"] == "swift build"
    assert facts.commands["test"] == "swift test"


def test_dart_project_sets_pub_and_analyzer_commands(tmp_path: Path) -> None:
    (tmp_path / "pubspec.yaml").write_text("name: demo\n", encoding="utf-8")
    (tmp_path / "test").mkdir()
    facts = RepoFacts(root_name="demo")

    _scan_additional_polyglot_projects(tmp_path, facts, set())

    assert "pub" in facts.package_managers
    assert "dart analyzer" in facts.typecheck_tools
    assert facts.commands["install"] == "dart pub get"
    assert facts.commands["test"] == "dart test"
    assert facts.commands["typecheck"] == "dart analyze"


def test_flutter_checkout_uses_flutter_runner(tmp_path: Path) -> None:
    (tmp_path / "pubspec.yaml").write_text("name: flutter_demo\n", encoding="utf-8")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "flutter").write_text("", encoding="utf-8")
    facts = RepoFacts(root_name="demo")

    _scan_additional_polyglot_projects(tmp_path, facts, set())

    assert facts.commands["install"] == "flutter pub get"
    assert facts.commands["typecheck"] == "flutter analyze"


def test_ignored_polyglot_markers_do_not_set_commands(tmp_path: Path) -> None:
    (tmp_path / "Package.swift").write_text("// ignored\n", encoding="utf-8")
    facts = RepoFacts(root_name="demo")

    _scan_additional_polyglot_projects(tmp_path, facts, {"Package.swift"})

    assert facts.package_managers == []
    assert facts.commands == {}
