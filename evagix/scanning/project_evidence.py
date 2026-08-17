from __future__ import annotations

import ast
from pathlib import Path

from evagix.ecosystems import detect_ecosystems
from evagix.model import EcosystemDetectionFact, RepoFacts, Subproject
from evagix.scanner_utils import (
    TraversalDiagnostics,
    _is_ignored_path,
    _is_safe_repo_path,
    _is_skipped_dir_name,
    _iter_files,
    _safe_read,
)
from evagix.scanning.base import RISK_FOLDERS, _is_available, _read_json
from evagix.scanning.command_evidence import _scoped_name
from evagix.scanning.polyglot_extra import _scan_additional_polyglot_projects
from evagix.scanning.python_evidence import _canonical_dep_key, _classify_python_dependencies
from evagix.scanning.shared import _add_unique, _set_command


def _scan_polyglot_projects(root: Path, facts: RepoFacts, ignored_paths: set[str]) -> None:
    """Detect common non-Python/Node ecosystems without trying to be a full build-system parser."""
    if _is_available(root, "go.mod", ignored_paths):
        _add_unique(facts.languages, "go")
        _add_unique(facts.package_managers, "go modules")
        _add_unique(facts.config_files, "go.mod")
        _set_command(facts, "install", "go mod download", "go.mod", "Go module detected", "high")
        _set_command(facts, "test", "go test ./...", "go.mod", "Go module detected", "high")
        _set_command(facts, "build", "go build ./...", "go.mod", "Go module detected", "medium")
        if _is_available(root, ".golangci.yml", ignored_paths) or _is_available(root, ".golangci.yaml", ignored_paths):
            _add_unique(facts.dev_tools, "golangci-lint")
            _add_unique(facts.lint_tools, "golangci-lint")
            _set_command(facts, "lint", "golangci-lint run", ".golangci.yml", "golangci-lint config detected", "high")

    if _is_available(root, "Cargo.toml", ignored_paths):
        _add_unique(facts.languages, "rust")
        _add_unique(facts.package_managers, "cargo")
        _add_unique(facts.dev_tools, "cargo")
        _add_unique(facts.config_files, "Cargo.toml")
        _set_command(facts, "test", "cargo test", "Cargo.toml", "Cargo project detected", "high")
        _set_command(facts, "build", "cargo build", "Cargo.toml", "Cargo project detected", "high")
        _set_command(facts, "format", "cargo fmt", "Cargo.toml", "Cargo formatter available", "medium")
        _set_command(
            facts,
            "lint",
            "cargo clippy --all-targets --all-features",
            "Cargo.toml",
            "Cargo clippy convention",
            "medium",
        )
        _add_unique(facts.lint_tools, "clippy")

    if _is_available(root, "pom.xml", ignored_paths):
        _add_unique(facts.languages, "java")
        _add_unique(facts.package_managers, "maven")
        _add_unique(facts.config_files, "pom.xml")
        _set_command(facts, "test", "mvn test", "pom.xml", "Maven project detected", "high")
        _set_command(facts, "build", "mvn package", "pom.xml", "Maven project detected", "medium")

    if _is_available(root, "build.gradle", ignored_paths) or _is_available(root, "build.gradle.kts", ignored_paths):
        _add_unique(facts.languages, "java/kotlin")
        _add_unique(facts.package_managers, "gradle")
        source = "build.gradle.kts" if _is_available(root, "build.gradle.kts", ignored_paths) else "build.gradle"
        _add_unique(facts.config_files, source)
        runner = "./gradlew" if _is_available(root, "gradlew", ignored_paths) else "gradle"
        _set_command(facts, "test", f"{runner} test", source, "Gradle project detected", "high")
        _set_command(facts, "build", f"{runner} build", source, "Gradle project detected", "medium")

    _scan_additional_polyglot_projects(root, facts, ignored_paths)

    csproj = sorted(
        path
        for path in root.glob("*.csproj")
        if _is_safe_repo_path(root, path) and not _is_ignored_path(root, path, ignored_paths)
    )
    if csproj:
        _add_unique(facts.languages, "csharp")
        _add_unique(facts.package_managers, "dotnet")
        _add_unique(facts.config_files, csproj[0].name)
        _set_command(facts, "install", "dotnet restore", csproj[0].name, ".NET project detected", "high")
        _set_command(facts, "test", "dotnet test", csproj[0].name, ".NET project detected", "high")
        _set_command(facts, "build", "dotnet build", csproj[0].name, ".NET project detected", "high")

    if _is_available(root, "composer.json", ignored_paths):
        _add_unique(facts.languages, "php")
        _add_unique(facts.package_managers, "composer")
        _add_unique(facts.config_files, "composer.json")
        _set_command(facts, "install", "composer install", "composer.json", "Composer project detected", "high")
        composer = _read_json(root / "composer.json")
        scripts = composer.get("scripts", {}) if isinstance(composer.get("scripts"), dict) else {}
        if "test" in scripts:
            _set_command(facts, "test", "composer test", "composer.json", "composer script 'test' detected", "high")

    if _is_available(root, "Gemfile", ignored_paths):
        _add_unique(facts.languages, "ruby")
        _add_unique(facts.package_managers, "bundler")
        _add_unique(facts.config_files, "Gemfile")
        _set_command(facts, "install", "bundle install", "Gemfile", "Bundler project detected", "high")
        if _is_available(root, "Rakefile", ignored_paths):
            _set_command(facts, "test", "bundle exec rake test", "Rakefile", "Rakefile detected", "medium")


def _scan_ecosystem_registry(root: Path, facts: RepoFacts, ignored_paths: set[str]) -> None:
    """Populate ecosystem-aware evidence without turning Evagix into a language parser."""
    detections = detect_ecosystems(root, ignored_paths, warnings=facts.warnings)
    facts.ecosystems = [
        EcosystemDetectionFact(
            id=item.id,
            name=item.name,
            path=item.path,
            language=item.language,
            support=item.support,
            confidence=item.confidence,
            evidence=item.evidence,
            package_manager=item.package_manager,
            frameworks=item.frameworks,
            tools=item.tools,
            commands=item.commands,
            command_evidence=item.command_evidence,
            metadata=item.metadata,
        )
        for item in detections
    ]
    for item in detections:
        if item.language:
            _add_unique(facts.languages, item.language)
        if item.package_manager:
            _add_unique(facts.package_managers, item.package_manager)
        category = str(item.metadata.get("category", ""))
        if category == "ci_platform":
            _add_unique(facts.ci_platforms, str(item.metadata.get("platform") or item.id.replace("_", "-")))
        elif category == "container_platform":
            _add_unique(facts.container_platforms, str(item.metadata.get("platform") or item.id))
        elif category == "infrastructure_tool":
            _add_unique(facts.infrastructure_tools, str(item.metadata.get("tool") or item.id))
        for evidence in item.evidence:
            if evidence and evidence not in {"."}:
                _add_unique(facts.config_files, evidence)
        for framework in item.frameworks:
            _add_unique(facts.frameworks, framework)
            if framework in {"react", "next.js", "vue", "svelte", "vite"}:
                _add_unique(facts.frontend_tools, framework)
            if framework in {
                "fastapi",
                "django",
                "flask",
                "express",
                "nestjs",
                "spring boot",
                "asp.net",
                "laravel",
                "symfony",
                "rails",
                "gin",
                "fiber",
                "echo",
                "axum",
                "actix",
            }:
                _add_unique(facts.backend_tools, framework)
            if framework in {
                "langchain",
                "llama-index",
                "mastra",
                "ai-sdk",
                "openai",
                "anthropic",
                "mcp",
                "rag",
            }:
                _add_unique(facts.llm_tools, framework)
            if framework in {"pandas", "scikit-learn", "torch"}:
                _add_unique(facts.ml_data_tools, framework)
        for tool in item.tools:
            _add_unique(facts.dev_tools, tool)
            if tool in {"ruff", "eslint", "golangci-lint", "clippy", "phpunit", "rspec"}:
                _add_unique(facts.lint_tools, tool)
            if tool in {"mypy", "pyright", "typescript"}:
                _add_unique(facts.typecheck_tools, tool)
        for command_name, command in item.commands.items():
            scoped_name = _scoped_name(item.path, command_name)
            source = item.command_evidence.get(command_name) or (item.evidence[0] if item.evidence else item.name)
            _set_command(
                facts,
                scoped_name,
                command,
                source,
                f"{item.name} ecosystem command evidence",
                item.confidence,
            )
        if (
            category not in {"ci_platform", "container_platform", "infrastructure_tool"}
            and (item.path != "." or item.frameworks or item.tools)
            and not any(existing.path == item.path and existing.kind == item.id for existing in facts.subprojects)
        ):
            facts.subprojects.append(
                Subproject(
                    path=item.path,
                    kind=item.id,
                    package_manager=item.package_manager,
                    frameworks=item.frameworks,
                    dev_tools=item.tools,
                    commands=item.commands,
                )
            )


def _scan_source_imports(root: Path, facts: RepoFacts, ignored_paths: set[str]) -> None:
    imports: set[str] = set()
    diagnostics = TraversalDiagnostics()
    paths = _iter_files(
        root,
        {".py"},
        limit=600,
        ignored_paths=ignored_paths,
        diagnostics=diagnostics,
    )
    for path in paths:
        imports.update(_python_import_roots(path))
    if diagnostics.incomplete:
        facts.warnings.append(diagnostics.warning("Python source import scan"))
    _classify_imports(imports, facts)


def _scan_notebooks(root: Path, facts: RepoFacts, ignored_paths: set[str]) -> None:
    imports: set[str] = set()
    diagnostics = TraversalDiagnostics()
    paths = _iter_files(
        root,
        {".ipynb"},
        limit=80,
        ignored_paths=ignored_paths,
        diagnostics=diagnostics,
    )
    for path in paths:
        imports.update(_notebook_import_roots(path))
    if diagnostics.incomplete:
        facts.warnings.append(diagnostics.warning("Notebook import scan"))
    if imports:
        _add_unique(facts.ml_data_tools, "jupyter")
    _classify_imports(imports, facts)


def _classify_imports(imports: set[str], facts: RepoFacts) -> None:
    normalized = {_canonical_dep_key(item) for item in imports}
    import_style = {name.replace("-", "_") for name in normalized}
    _classify_python_dependencies(normalized | import_style, facts)


def _scan_folders(root: Path, facts: RepoFacts, ignored_paths: set[str]) -> None:
    try:
        top_level = sorted(root.iterdir())
    except OSError:
        top_level = []
    for path in top_level:
        if (
            not path.is_symlink()
            and path.is_dir()
            and not _is_skipped_dir_name(path.name)
            and not path.name.startswith(".")
            and not _is_ignored_path(root, path, ignored_paths)
        ):
            _add_unique(facts.folders, path.name)
            if path.name in RISK_FOLDERS:
                _add_unique(facts.risk_flags, RISK_FOLDERS[path.name])
    important_folders = [
        "tests",
        "test",
        "src",
        "app",
        "backend",
        "frontend",
        "docs",
        "scripts",
        "examples",
        "notebooks",
        "assets",
        "data",
        "migrations",
        "alembic",
    ]
    for candidate in important_folders:
        candidate_path = root / candidate
        if (
            candidate_path.exists()
            and _is_safe_repo_path(root, candidate_path)
            and not _is_ignored_path(root, candidate_path, ignored_paths)
        ):
            _add_unique(facts.folders, candidate)
    for candidate in ("tests", "test"):
        if _is_available(root, candidate, ignored_paths):
            _add_unique(facts.test_paths, candidate)


def _derive_fallback_commands(facts: RepoFacts) -> None:
    if "black" in facts.dev_tools and "lint" not in facts.commands:
        _set_command(
            facts,
            "lint",
            "black --check .",
            "dependency files",
            "black dependency detected",
            "low",
            priority=10,
            status="inferred",
        )
    if "eslint" in facts.dev_tools and "lint" not in facts.commands:
        _set_command(
            facts,
            "lint",
            "npm run lint",
            "package.json",
            "eslint dependency detected",
            "low",
            priority=10,
            status="inferred",
        )


def _derive_warnings(facts: RepoFacts) -> None:
    if not facts.commands.get("test") and not any(key.endswith("_test") for key in facts.commands):
        facts.warnings.append("No test command was detected.")
    if not facts.commands.get("lint") and not any(key.endswith("_lint") for key in facts.commands):
        facts.warnings.append("No lint command was detected.")
    if not facts.ci_workflows:
        facts.warnings.append("No GitHub Actions workflow was detected.")
    if not facts.languages:
        facts.warnings.append("No primary language was detected with high confidence.")
    if (
        facts.is_ml_project
        and not facts.commands.get("test")
        and not any(key.endswith("_test") for key in facts.commands)
    ):
        facts.warnings.append("ML/data project detected, but no test command was found.")
    if facts.is_dashboard_project and not facts.commands.get("run") and not facts.commands.get("dev"):
        facts.warnings.append("Dashboard framework detected, but no run/dev command was found.")
    if facts.is_frontend_project and not any(key.endswith(("build", "_build")) for key in facts.commands):
        facts.warnings.append("Frontend project detected, but no build command was found.")
    for flag in facts.risk_flags[:5]:
        facts.warnings.append(flag)


def _python_import_roots(path: Path) -> set[str]:
    text = _safe_read(path, max_chars=120_000)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _notebook_import_roots(path: Path) -> set[str]:
    data = _read_json(path)
    roots: set[str] = set()
    cells = data.get("cells", [])
    if not isinstance(cells, list):
        return roots
    for cell in cells:
        if not isinstance(cell, dict) or cell.get("cell_type") != "code":
            continue
        source = cell.get("source", "")
        if isinstance(source, list):
            source = "".join(source)
        if isinstance(source, str):
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        roots.add(alias.name.split(".", 1)[0])
                elif isinstance(node, ast.ImportFrom) and node.module:
                    roots.add(node.module.split(".", 1)[0])
    return roots
