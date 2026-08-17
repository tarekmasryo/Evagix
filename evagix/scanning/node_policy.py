from __future__ import annotations

from collections.abc import Mapping
from fnmatch import fnmatchcase
from pathlib import Path

from evagix.scanner_utils import _safe_read


def _node_package_manager(
    project_dir: Path,
    root: Path | None = None,
    package_data: Mapping[str, object] | None = None,
    root_package_data: Mapping[str, object] | None = None,
) -> str:
    declared = _declared_node_package_manager(package_data)
    if declared:
        return declared
    local = _node_lock_manager(project_dir)
    if local:
        return local
    if root and project_dir != root and _is_node_workspace_package(project_dir, root, root_package_data):
        root_declared = _declared_node_package_manager(root_package_data)
        if root_declared:
            return root_declared
        root_manager = _node_lock_manager(root)
        if root_manager:
            return root_manager
    return "npm"


def _node_install_command(
    project_dir: Path,
    manager: str,
    root: Path | None = None,
    root_package_data: Mapping[str, object] | None = None,
) -> tuple[str, str, str]:
    if manager == "bun":
        if _node_lock_exists(project_dir, root, root_package_data, ("bun.lock", "bun.lockb")):
            return "bun install --frozen-lockfile", "bun lockfile detected", "high"
        return "bun install", "bun package manager declared without a lockfile", "medium"
    if manager == "pnpm":
        if _node_lock_exists(project_dir, root, root_package_data, ("pnpm-lock.yaml",)):
            return "pnpm install --frozen-lockfile", "pnpm lockfile detected", "high"
        return "pnpm install", "pnpm package manager declared without a lockfile", "medium"
    if manager == "yarn":
        if _node_lock_exists(project_dir, root, root_package_data, ("yarn.lock",)):
            return "yarn install --frozen-lockfile", "yarn lockfile detected", "high"
        return "yarn install", "yarn package manager declared without a lockfile", "medium"
    if (project_dir / "package-lock.json").exists() or (project_dir / "npm-shrinkwrap.json").exists():
        return "npm ci", "npm lockfile detected", "high"
    return "npm install", "no npm lockfile detected; npm install is less deterministic than npm ci", "medium"


def _declared_node_package_manager(package_data: Mapping[str, object] | None) -> str:
    if not package_data:
        return ""
    value = package_data.get("packageManager")
    if not isinstance(value, str):
        return ""
    manager = value.strip().split("@", 1)[0].lower()
    return manager if manager in {"npm", "pnpm", "yarn", "bun"} else ""


def _node_lock_manager(directory: Path) -> str:
    if (directory / "bun.lock").exists() or (directory / "bun.lockb").exists():
        return "bun"
    if (directory / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (directory / "yarn.lock").exists():
        return "yarn"
    if (directory / "package-lock.json").exists() or (directory / "npm-shrinkwrap.json").exists():
        return "npm"
    return ""


def _node_lock_exists(
    project_dir: Path,
    root: Path | None,
    root_package_data: Mapping[str, object] | None,
    names: tuple[str, ...],
) -> bool:
    if any((project_dir / name).exists() for name in names):
        return True
    return bool(
        root
        and root != project_dir
        and _is_node_workspace_package(project_dir, root, root_package_data)
        and any((root / name).exists() for name in names)
    )


def _is_node_workspace_package(
    project_dir: Path,
    root: Path,
    root_package_data: Mapping[str, object] | None,
) -> bool:
    try:
        relative_path = project_dir.relative_to(root).as_posix()
    except ValueError:
        return False
    matched = False
    for raw_pattern in _node_workspace_patterns(root, root_package_data):
        excluded = raw_pattern.startswith("!")
        pattern = raw_pattern[1:] if excluded else raw_pattern
        if _workspace_pattern_matches(relative_path, pattern):
            matched = not excluded
    return matched


def _node_workspace_patterns(
    root: Path,
    root_package_data: Mapping[str, object] | None,
) -> list[str]:
    patterns: list[str] = []
    if root_package_data:
        workspaces = root_package_data.get("workspaces")
        if isinstance(workspaces, list):
            patterns.extend(item for item in workspaces if isinstance(item, str) and item.strip())
        elif isinstance(workspaces, dict):
            packages = workspaces.get("packages")
            if isinstance(packages, list):
                patterns.extend(item for item in packages if isinstance(item, str) and item.strip())
    patterns.extend(_pnpm_workspace_patterns(root))
    return patterns


def _pnpm_workspace_patterns(root: Path) -> list[str]:
    workspace_file = root / "pnpm-workspace.yaml"
    if not workspace_file.exists():
        return []
    patterns: list[str] = []
    in_packages = False
    packages_indent = 0
    for raw_line in _safe_read(workspace_file, max_chars=100_000).splitlines():
        content = raw_line.split("#", 1)[0].rstrip()
        stripped = content.strip()
        if not stripped:
            continue
        indent = len(content) - len(content.lstrip())
        if not in_packages:
            if stripped.casefold() == "packages:":
                in_packages = True
                packages_indent = indent
            continue
        if indent <= packages_indent and not stripped.startswith("-"):
            break
        if stripped.startswith("-"):
            pattern = stripped[1:].strip().strip("'\"")
            if pattern:
                patterns.append(pattern)
    return patterns


def _workspace_pattern_matches(relative_path: str, raw_pattern: str) -> bool:
    normalized = raw_pattern.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.rstrip("/")
    if not normalized:
        return False
    path_parts = tuple(part for part in relative_path.split("/") if part)
    pattern_parts = tuple(part for part in normalized.split("/") if part)

    def matches(pattern_index: int, path_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return path_index == len(path_parts)
        pattern_part = pattern_parts[pattern_index]
        if pattern_part == "**":
            return matches(pattern_index + 1, path_index) or (
                path_index < len(path_parts) and matches(pattern_index, path_index + 1)
            )
        return (
            path_index < len(path_parts)
            and fnmatchcase(path_parts[path_index], pattern_part)
            and matches(pattern_index + 1, path_index + 1)
        )

    return matches(0, 0)
