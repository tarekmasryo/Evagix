from __future__ import annotations

from pathlib import Path

from evagix.model import RepoFacts, Subproject
from evagix.scanner_utils import TraversalDiagnostics, _iter_named_files
from evagix.scanning.base import _read_json
from evagix.scanning.node_policy import _node_install_command, _node_package_manager
from evagix.scanning.shared import _add_unique, _set_command, is_node_test_placeholder
from evagix.signatures import NODE_DEV_TOOLS, NODE_FRAMEWORKS


def _scan_node_projects(root: Path, facts: RepoFacts, ignored_paths: set[str]) -> None:
    diagnostics = TraversalDiagnostics()
    package_files = _find_package_json_files(root, ignored_paths, diagnostics=diagnostics)
    if diagnostics.incomplete:
        facts.warnings.append(diagnostics.warning("Node package discovery"))
    for package_json in package_files:
        _scan_node_package(root, package_json, facts)


def _find_package_json_files(
    root: Path,
    ignored_paths: set[str] | None = None,
    *,
    diagnostics: TraversalDiagnostics | None = None,
) -> list[Path]:
    return _iter_named_files(
        root,
        {"package.json"},
        ignored_paths=ignored_paths,
        limit=20,
        diagnostics=diagnostics,
        max_depth=3,
    )


def _scan_node_package(root: Path, package_json: Path, facts: RepoFacts) -> None:
    project_dir = package_json.parent
    rel = project_dir.relative_to(root).as_posix() if project_dir != root else "."
    data = _read_json(package_json, facts.warnings, root)
    if not data:
        return

    _add_unique(facts.languages, "javascript/typescript")
    engines = data.get("engines", {}) if isinstance(data.get("engines"), dict) else {}
    if engines.get("node"):
        _add_unique(facts.runtimes, "node")
    scripts = data.get("scripts", {}) if isinstance(data.get("scripts"), dict) else {}
    deps = {**(data.get("dependencies", {}) or {}), **(data.get("devDependencies", {}) or {})}
    deps_text = "\n".join(deps.keys()).lower()

    root_data = data if project_dir == root else _read_json(root / "package.json")
    pm = _node_package_manager(project_dir, root, data, root_data)
    _add_unique(facts.package_managers, pm)
    frameworks: list[str] = []
    dev_tools: list[str] = []

    for package, label in NODE_FRAMEWORKS.items():
        if package in deps_text:
            _add_unique(facts.frameworks, label)
            _add_unique(frameworks, label)
            if label in {"react", "next.js", "vue", "svelte", "vite"}:
                _add_unique(facts.frontend_tools, label)
    for package, label in NODE_DEV_TOOLS.items():
        if package in deps_text:
            _add_unique(facts.dev_tools, label)
            _add_unique(dev_tools, label)
            if label in {"eslint", "prettier", "typescript", "vite", "vitest", "jest", "playwright", "cypress"}:
                _add_unique(facts.frontend_tools, label)

    prefix = {"npm": "npm run", "pnpm": "pnpm", "yarn": "yarn", "bun": "bun run"}[pm]
    install, install_detail, install_confidence = _node_install_command(project_dir, pm, root, root_data)
    cmd_prefix = f"cd {rel} && " if rel != "." else ""
    _set_command(
        facts,
        _scoped_name(rel, "install"),
        f"{cmd_prefix}{install}",
        package_json.relative_to(root).as_posix(),
        install_detail,
        install_confidence,
    )
    if pm == "npm" and install == "npm install":
        facts.warnings.append(
            f"{package_json.relative_to(root).as_posix()} has no npm lockfile; install command is not fully deterministic."
        )

    preferred = {
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
        "format": ["format"],
    }
    sub_commands: dict[str, str] = {"install": f"{cmd_prefix}{install}"}
    for command_name, candidates in preferred.items():
        for candidate in candidates:
            if candidate in scripts:
                if command_name == "test" and is_node_test_placeholder(scripts[candidate]):
                    facts.warnings.append(
                        f"{package_json.relative_to(root).as_posix()} test script is a known placeholder and was ignored."
                    )
                    break
                command = f"{cmd_prefix}{prefix} {candidate}"
                scoped = _scoped_name(rel, command_name)
                _set_command(
                    facts,
                    scoped,
                    command,
                    package_json.relative_to(root).as_posix(),
                    f"script '{candidate}' detected",
                    "high",
                    priority=70,
                    status="declared",
                )
                sub_commands[command_name] = command
                if command_name == "lint":
                    _add_unique(facts.lint_tools, "eslint" if "eslint" in facts.dev_tools else "node-lint")
                if command_name == "typecheck":
                    _add_unique(facts.typecheck_tools, "typescript")
                break

    if rel != "." or frameworks or dev_tools:
        facts.subprojects.append(
            Subproject(
                path=rel,
                kind="node",
                package_manager=pm,
                frameworks=tuple(frameworks),
                dev_tools=tuple(dev_tools),
                commands=sub_commands,
            )
        )


def _scoped_name(rel: str, command_name: str) -> str:
    if rel == ".":
        return command_name
    safe = rel.replace("/", "_").replace("-", "_")
    return f"{safe}_{command_name}"
