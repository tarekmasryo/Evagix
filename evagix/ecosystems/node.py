from __future__ import annotations

from pathlib import Path
from typing import Any

from evagix.ecosystems.profiles import EcosystemDetection
from evagix.ecosystems.utils import (
    _detect_frameworks,
    _find_marker_files,
    _prefix,
    _read_json,
    _rel,
    _scope,
)
from evagix.scanning.node_policy import _node_install_command, _node_package_manager
from evagix.scanning.shared import is_node_test_placeholder


def _detect_node(
    root: Path,
    ignored: set[str],
    warnings: list[str] | None = None,
) -> list[EcosystemDetection]:
    detections: list[EcosystemDetection] = []
    for package_json in _find_marker_files(root, {"package.json"}, ignored, warnings):
        directory = package_json.parent
        rel = _rel(directory, root)
        data = _read_json(package_json)
        if not data:
            continue
        deps = {}
        for key in ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"]:
            value = data.get(key)
            if isinstance(value, dict):
                deps.update(value)
        deps_text = "\n".join(deps.keys()).lower()
        scripts = data.get("scripts", {}) if isinstance(data.get("scripts"), dict) else {}
        if "test" in scripts and is_node_test_placeholder(scripts["test"]) and warnings is not None:
            warnings.append(f"{_rel(package_json, root)} test script is a known placeholder and was ignored.")
        evidence = [_rel(package_json, root)]
        for lock in [
            "pnpm-lock.yaml",
            "yarn.lock",
            "bun.lock",
            "bun.lockb",
            "package-lock.json",
            "npm-shrinkwrap.json",
            "tsconfig.json",
        ]:
            if (directory / lock).exists():
                evidence.append(_prefix(rel, lock))
        frameworks = _detect_frameworks("node", deps_text + "\n" + "\n".join(evidence), directory)
        tools = sorted(
            {
                tool
                for tool in ["typescript", "eslint", "prettier", "jest", "vitest", "playwright", "cypress", "vite"]
                if tool in deps_text or tool in scripts
            }
        )
        root_data = data if directory == root else _read_json(root / "package.json")
        pm = _node_package_manager(directory, root, data, root_data)
        commands, command_evidence = _node_commands(directory, root, root_data, pm, scripts)
        detections.append(
            EcosystemDetection(
                id="node",
                name="Node.js / TypeScript",
                path=rel,
                language="javascript/typescript",
                support="deep",
                confidence="high",
                evidence=tuple(evidence),
                package_manager=pm,
                frameworks=tuple(frameworks),
                tools=tuple(tools),
                commands=commands,
                command_evidence=command_evidence,
            )
        )
    return detections


def _node_commands(
    directory: Path,
    root: Path,
    root_package_data: dict[str, Any],
    pm: str,
    scripts: dict[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    rel = _rel(directory, root)
    install, _detail, _confidence = _node_install_command(directory, pm, root, root_package_data)
    prefix = {"npm": "npm run", "pnpm": "pnpm", "yarn": "yarn", "bun": "bun run"}[pm]
    commands = {"install": _scope(rel, install)}
    aliases = {
        "test": ["test"],
        "lint": ["lint"],
        "typecheck": [
            "typecheck",
            "type-check",
            "check",
            "check-types",
            "test-types",
            "lint-typescript",
            "typescript",
            "types",
            "tsc",
        ],
        "build": ["build"],
        "dev": ["dev", "start:dev"],
        "run": ["start"],
    }
    for kind, names in aliases.items():
        for name in names:
            if name in scripts:
                if kind == "test" and is_node_test_placeholder(scripts[name]):
                    break
                commands[kind] = _scope(rel, f"{prefix} {name}")
                break
    source = _prefix(rel, "package.json")
    return commands, {key: source for key in commands}
