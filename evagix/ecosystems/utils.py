from __future__ import annotations

import fnmatch
import json
import re
import tomllib
from pathlib import Path
from typing import Any

from evagix.core.io import safe_read_text
from evagix.ecosystems.profiles import ECOSYSTEM_PROFILES, EcosystemDetection, EcosystemProfile
from evagix.scanner_utils import TraversalDiagnostics, _iter_repo_files

MAX_MARKER_DEPTH = 5
MAX_MARKER_RESULTS = 200
MAX_MARKER_SCAN_FILES = 12000
MAX_MARKER_VISITED_ENTRIES = 50_000


def _detect_frameworks(profile_id: str, text: str, directory: Path) -> list[str]:
    profile = ECOSYSTEM_PROFILES.get(profile_id)
    if not profile:
        return []
    found: list[str] = []
    lower = text.lower()
    file_names = _framework_file_marker_text(profile, directory)
    haystack = lower + "\n" + file_names
    for label, markers in profile.framework_markers.items():
        if any(marker.lower() in haystack for marker in markers):
            found.append(label)

    if profile_id == "node":
        wrapped_haystack = f"\n{haystack}\n"
        node_llm_markers = {
            "mastra": (
                "@mastra/",
                "\nmastra\n",
                "\ncreate-mastra\n",
                "packages/agent-builder",
                "packages/create-mastra",
                "mastracode",
            ),
            "ai-sdk": (
                "@ai-sdk/",
                "\nai\n",
                "client-sdks/ai-sdk",
            ),
            "openai": (
                "@openai/",
                "\nopenai\n",
                "agent-sdks/openai",
                "voice/openai",
                "openai-realtime-api",
            ),
            "anthropic": (
                "@anthropic-ai/",
                "\nanthropic\n",
            ),
            "mcp": (
                "@modelcontextprotocol/",
                "modelcontextprotocol",
                "packages/mcp",
            ),
            "rag": (
                "@mastra/rag",
                "packages/rag",
            ),
        }
        for label, markers in node_llm_markers.items():
            if any(marker in haystack or marker in wrapped_haystack for marker in markers):
                found.append(label)

    return sorted(set(found))


def _framework_file_marker_text(profile: EcosystemProfile, directory: Path) -> str:
    """Return deterministic framework filename evidence without enumerating a directory."""
    if not directory.exists():
        return ""
    names: set[str] = set()
    config_suffixes = ("", ".js", ".mjs", ".cjs", ".ts", ".mts", ".cts")
    for markers in profile.framework_markers.values():
        for marker in markers:
            if "/" in marker or marker.startswith("@"):  # package identifiers, not local filenames
                continue
            candidates: tuple[str, ...] = (marker,)
            if marker.endswith(".config"):
                candidates = tuple(marker + suffix for suffix in config_suffixes)
            for candidate in candidates:
                try:
                    if (directory / candidate).is_file():
                        names.add(candidate.lower())
                except (OSError, UnicodeError):
                    continue
    return "\n".join(sorted(names))


def _find_marker_files(
    root: Path,
    names: set[str],
    ignored: set[str],
    warnings: list[str] | None = None,
) -> list[Path]:
    results: list[Path] = []
    diagnostics = TraversalDiagnostics(max_visited_entries=MAX_MARKER_VISITED_ENTRIES)
    for path in _iter_bounded_files(root, ignored, diagnostics=diagnostics):
        if path.name not in names:
            continue
        if len(results) >= MAX_MARKER_RESULTS:
            diagnostics.result_limit_reached = True
            break
        results.append(path)
    _append_traversal_warning(warnings, diagnostics, "Ecosystem marker discovery")
    return sorted(set(results))


def _find_glob_markers(
    root: Path,
    pattern: str,
    ignored: set[str],
    warnings: list[str] | None = None,
) -> list[Path]:
    results: list[Path] = []
    diagnostics = TraversalDiagnostics(max_visited_entries=MAX_MARKER_VISITED_ENTRIES)
    for path in _iter_bounded_files(root, ignored, diagnostics=diagnostics):
        relative = path.relative_to(root).as_posix()
        if not fnmatch.fnmatch(relative, pattern):
            continue
        if len(results) >= 40:
            diagnostics.result_limit_reached = True
            break
        results.append(path)
    _append_traversal_warning(warnings, diagnostics, f"Ecosystem marker discovery for {pattern}")
    return sorted(set(results))


def _append_traversal_warning(
    warnings: list[str] | None,
    diagnostics: TraversalDiagnostics,
    scope: str,
) -> None:
    if warnings is None or not diagnostics.incomplete:
        return
    warning = diagnostics.warning(scope)
    if warning not in warnings:
        warnings.append(warning)


def _iter_bounded_files(
    root: Path,
    ignored: set[str],
    *,
    diagnostics: TraversalDiagnostics | None = None,
) -> list[Path]:
    files: list[Path] = []
    state = diagnostics or TraversalDiagnostics(max_visited_entries=MAX_MARKER_VISITED_ENTRIES)
    for path in _iter_repo_files(
        root,
        ignored_paths=ignored,
        diagnostics=state,
        max_visited_entries=MAX_MARKER_VISITED_ENTRIES,
        max_depth=MAX_MARKER_DEPTH,
        extra_skip_dir_names={"target"},
    ):
        if len(files) >= MAX_MARKER_SCAN_FILES:
            state.result_limit_reached = True
            break
        files.append(path)
    return files


def _dedupe_detections(items: list[EcosystemDetection]) -> list[EcosystemDetection]:
    seen: set[tuple[str, str]] = set()
    result: list[EcosystemDetection] = []
    for item in items:
        key = (item.id, item.path)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return sorted(result, key=lambda item: (item.path != ".", item.path, item.id))


def _detections_for(detections: list[EcosystemDetection], ecosystem_id: str) -> list[EcosystemDetection]:
    return [item for item in detections if item.id == ecosystem_id]


def _support_summary(profile: EcosystemProfile) -> str:
    parts = []
    if profile.marker_files:
        parts.append("markers: " + ", ".join(profile.marker_files[:3]))
    if profile.test_commands:
        parts.append("tests: " + ", ".join(profile.test_commands[:2]))
    if profile.framework_markers:
        parts.append("framework hints")
    return "; ".join(parts) or "general evidence checks"


def _strip_shell_prefix(command: str) -> str:
    return _strip_cd(command.strip().lstrip("$> -").strip())


def _strip_cd(command: str) -> str:
    return re.sub(r"^cd\s+[^&;]+\s*&&\s*", "", command.strip())


def _scope(rel: str, command: str) -> str:
    return command if rel == "." else f"cd {rel} && {command}"


def _rel(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = path.as_posix()
    return rel or "."


def _prefix(rel: str, name: str) -> str:
    return name if rel == "." else f"{rel}/{name}"


def _safe_child(root: Path, path: Path) -> bool:
    try:
        if path.is_symlink():
            return False
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _ignored(root: Path, path: Path, ignored: set[str]) -> bool:
    rel = _rel(path, root)
    return any(rel == item or rel.startswith(item.rstrip("/") + "/") for item in ignored)


def _safe_read(path: Path, max_chars: int = 300_000) -> str:
    try:
        return safe_read_text(path, max_chars=max_chars)
    except (OSError, UnicodeError):
        return ""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(_safe_read(path))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return tomllib.loads(_safe_read(path))
    except tomllib.TOMLDecodeError:
        return {}


def _python_dependency_names(data: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    project = data.get("project", {}) if isinstance(data.get("project"), dict) else {}
    for key in ["dependencies"]:
        for spec in project.get(key, []) or []:
            name = _dep_name(str(spec))
            if name:
                names.add(name)
    optional = (
        project.get("optional-dependencies", {}) if isinstance(project.get("optional-dependencies"), dict) else {}
    )
    for values in optional.values():
        for spec in values or []:
            name = _dep_name(str(spec))
            if name:
                names.add(name)
    tool = data.get("tool", {}) if isinstance(data.get("tool"), dict) else {}
    poetry = tool.get("poetry", {}) if isinstance(tool.get("poetry"), dict) else {}
    for dep_map in [poetry.get("dependencies", {}), poetry.get("dev-dependencies", {})]:
        if isinstance(dep_map, dict):
            for name in dep_map:
                if name.lower() != "python":
                    names.add(name.lower().replace("_", "-"))
    return names


def _requirements_names(path: Path) -> set[str]:
    result = set()
    for line in _safe_read(path).splitlines():
        name = _dep_name(line)
        if name:
            result.add(name)
    return result


def _dep_name(spec: str) -> str:
    spec = spec.split("#", 1)[0].split(";", 1)[0].split("[", 1)[0].strip()
    if not spec or spec.startswith("-"):
        return ""
    match = re.match(r"([A-Za-z0-9_.-]+)", spec)
    return match.group(1).lower().replace("_", "-") if match else ""


def _has_dev_extra(data: dict[str, Any]) -> bool:
    project = data.get("project", {}) if isinstance(data.get("project"), dict) else {}
    optional = (
        project.get("optional-dependencies", {}) if isinstance(project.get("optional-dependencies"), dict) else {}
    )
    return "dev" in optional or "test" in optional


def _command_kind(lower: str) -> str:
    if "install" in lower or lower.startswith(
        ("npm ci", "go mod download", "dotnet restore", "bundle install", "composer install", "terraform init")
    ):
        return "install"
    if "test" in lower or lower.endswith("pytest") or lower.startswith(("pytest", "go test", "cargo test", "mvn test")):
        return "test"
    if "lint" in lower or "clippy" in lower or "ruff" in lower:
        return "lint"
    if "type" in lower or "mypy" in lower or "pyright" in lower:
        return "typecheck"
    if "build" in lower or lower.startswith(("go build", "cargo build", "dotnet build", "docker build")):
        return "build"
    if "dev" in lower or "serve" in lower:
        return "dev"
    return "run"
