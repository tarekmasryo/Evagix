from __future__ import annotations

import json
import tomllib
from pathlib import Path

from evagix.core.io import is_safe_repo_path, safe_read_text
from evagix.model import RepoFacts
from evagix.readme.claim_text_scan import _repo_text_contains
from evagix.repository_intent import python_cli_entrypoint_evidence, python_package_evidence
from evagix.scanner_utils import TraversalDiagnostics, _iter_named_files, _iter_repo_files


def _repo_text_search(root: Path, needles: list[str], scope: str) -> tuple[bool, str]:
    diagnostics = TraversalDiagnostics()
    found = _repo_text_contains(root, needles, diagnostics=diagnostics)
    warning = "" if found or not diagnostics.incomplete else diagnostics.warning(scope)
    return found, warning


def _check_tested(root: Path, facts: RepoFacts) -> tuple[list[str], list[str]]:
    evidence = []
    missing = []
    if (root / "tests").exists() or (root / "test").exists() or facts.test_paths:
        evidence.append("tests directory/path detected")
    else:
        missing.append("tests directory/path")
    if "test" in facts.commands or any(key.endswith("_test") for key in facts.commands):
        evidence.append("test command detected")
    else:
        missing.append("test command")
    return evidence, missing


def _check_dockerized(root: Path, facts: RepoFacts) -> tuple[list[str], list[str]]:
    evidence = []
    if "docker" in facts.container_platforms or any("Dockerfile" in item for item in facts.config_files):
        evidence.append("Dockerfile detected")
    if "docker-compose" in facts.container_platforms:
        evidence.append("Compose file detected")
    return evidence, [] if evidence else ["Dockerfile or Compose file"]


def _check_ci(root: Path, facts: RepoFacts) -> tuple[list[str], list[str]]:
    return (["CI workflow detected"] if facts.ci_workflows else [], [] if facts.ci_workflows else ["CI workflow"])


def _check_fastapi(root: Path, facts: RepoFacts) -> tuple[list[str], list[str]]:
    ok = "fastapi" in facts.frameworks or "fastapi" in facts.backend_tools
    return (["FastAPI detected"] if ok else [], [] if ok else ["FastAPI dependency/import"])


def _check_llm(root: Path, facts: RepoFacts) -> tuple[list[str], list[str]]:
    if facts.llm_tools:
        return ["AI/Retrieval tooling detected: " + ", ".join(facts.llm_tools)], []
    return [], ["AI/Retrieval dependency or config"]


def _check_monitoring(root: Path, facts: RepoFacts) -> tuple[list[str], list[str]]:
    markers = {"prometheus", "opentelemetry", "structlog", "logging"}
    found = sorted(markers.intersection(set(facts.dev_tools) | set(facts.backend_tools) | set(facts.frameworks)))
    text_hit, text_warning = _repo_text_search(
        root,
        ["/metrics", "prometheus", "opentelemetry", "structlog"],
        "README monitoring evidence search",
    )
    evidence = []
    if found:
        evidence.append("monitoring/logging dependency detected: " + ", ".join(found))
    if text_hit:
        evidence.append("metrics/observability marker detected in source/docs")
    missing = [] if evidence else ["metrics/logging/observability evidence"]
    if not evidence and text_warning:
        missing.append(text_warning)
    return evidence, missing


def _check_secure(root: Path, facts: RepoFacts) -> tuple[list[str], list[str]]:
    evidence = []
    missing = []
    if facts.ci_workflows:
        evidence.append("CI workflow detected")
    else:
        missing.append("CI workflow")
    if any(tool in facts.dev_tools for tool in ["bandit", "pip-audit", "pre-commit"]):
        evidence.append("security/supply-chain tool detected")
    else:
        missing.append("security/supply-chain tool")
    text_hit, text_warning = _repo_text_search(
        root,
        ["api key", "auth", "secret", "token"],
        "README security evidence search",
    )
    if text_hit:
        evidence.append("auth/secret handling mentioned in source/docs")
    else:
        missing.append("auth/secret handling evidence")
        if text_warning:
            missing.append(text_warning)
    return evidence, missing


def _check_production_ready(root: Path, facts: RepoFacts) -> tuple[list[str], list[str]]:
    health_hit, health_warning = _repo_text_search(
        root,
        ["/health", "/ready", "/metrics", "healthcheck"],
        "README production-readiness evidence search",
    )
    checks = [
        (bool(facts.ci_workflows), "CI workflow"),
        ("test" in facts.commands or any(key.endswith("_test") for key in facts.commands), "test command"),
        ("lint" in facts.commands or any(key.endswith("_lint") for key in facts.commands), "lint command"),
        (any((root / name).exists() for name in [".env.example", ".env.sample", "env.example"]), "env example"),
        (
            "docker" in facts.container_platforms or "docker-compose" in facts.container_platforms,
            "Docker/runtime config",
        ),
        (health_hit, "health/readiness/metrics evidence"),
    ]
    evidence = [label for ok, label in checks if ok]
    missing = [label for ok, label in checks if not ok]
    if not health_hit and health_warning:
        missing.append(health_warning)
    return evidence, missing


def _check_deployable(root: Path, facts: RepoFacts) -> tuple[list[str], list[str]]:
    evidence = []
    deploy_targets = [*facts.runtimes, *facts.container_platforms, *facts.infrastructure_tools]
    if deploy_targets:
        evidence.append("runtime/deployment config detected: " + ", ".join(deploy_targets))
    text_hit, text_warning = _repo_text_search(
        root,
        ["deploy", "docker compose", "uvicorn", "streamlit run", "npm run build"],
        "README deployment evidence search",
    )
    if text_hit:
        evidence.append("deployment/run marker detected in docs/source")
    missing = [] if evidence else ["deployment or runtime evidence"]
    if not evidence and text_warning:
        missing.append(text_warning)
    return evidence, missing


def _check_agent_instructions(root: Path, facts: RepoFacts) -> tuple[list[str], list[str]]:
    target_files = [
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
        ".cursor/rules/project.mdc",
        ".github/copilot-instructions.md",
        ".windsurf/rules/evagix.md",
    ]
    generated = [item for item in target_files if (root / item).exists()]
    renderer_source = root / "evagix" / "renderers.py"
    renderer_evidence = False
    if renderer_source.exists():
        try:
            text = safe_read_text(renderer_source, root=root, max_chars=300_000)
            renderer_evidence = "render_agents_md" in text and "render_claude_md" in text
        except (OSError, UnicodeError):
            renderer_evidence = False
    evidence = []
    if generated:
        evidence.append("generated agent instruction files detected: " + ", ".join(generated[:4]))
    if renderer_evidence:
        evidence.append("agent instruction renderers detected")
    return evidence, [] if evidence else ["generated agent instruction files or renderer evidence"]


def _check_cli_tool(root: Path, facts: RepoFacts) -> tuple[list[str], list[str]]:
    python_evidence, python_missing = python_cli_entrypoint_evidence(root)
    node_evidence, node_missing = _node_cli_entrypoint_evidence(root, facts)

    evidence = [*python_evidence, *node_evidence]
    if evidence:
        return evidence, []

    missing = [*python_missing]
    if "javascript/typescript" in facts.languages or (root / "package.json").exists():
        missing.extend(node_missing)

    if facts.commands:
        return ["project commands detected"], missing

    return [], missing


def _node_cli_entrypoint_evidence(root: Path, facts: RepoFacts) -> tuple[list[str], list[str]]:
    if "javascript/typescript" not in facts.languages and not (root / "package.json").exists():
        return [], []

    evidence: list[str] = []
    diagnostics = TraversalDiagnostics()
    package_files = _iter_named_files(
        root,
        {"package.json"},
        limit=80,
        diagnostics=diagnostics,
    )

    for package_json in package_files:
        try:
            if package_json.is_symlink() or not is_safe_repo_path(root, package_json):
                continue
        except (OSError, UnicodeError):
            continue

        try:
            data = json.loads(safe_read_text(package_json, root=root, max_chars=500_000))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue

        bin_value = data.get("bin")
        if isinstance(bin_value, str) and bin_value.strip():
            evidence.append(f"Node package.json bin entry detected: {package_json.relative_to(root).as_posix()}")
            break
        if isinstance(bin_value, dict) and any(str(value).strip() for value in bin_value.values()):
            evidence.append(f"Node package.json bin entry detected: {package_json.relative_to(root).as_posix()}")
            break

    missing = [] if evidence else ["Python console_scripts or Node package.json bin entry"]
    if diagnostics.incomplete:
        missing.append(diagnostics.warning("Node CLI entrypoint discovery"))
    return evidence, missing


def _check_package_installable(root: Path, facts: RepoFacts) -> tuple[list[str], list[str]]:
    return python_package_evidence(root)


def _check_examples(root: Path, facts: RepoFacts) -> tuple[list[str], list[str]]:
    evidence = []
    if (root / "examples").exists():
        evidence.append("examples/ directory detected")
    text_hit, text_warning = _repo_text_search(
        root,
        ["quickstart", "usage", "example", "```bash"],
        "README example evidence search",
    )
    if text_hit:
        evidence.append("usage/example snippets detected")
    missing = [] if evidence else ["examples/ directory or reproducible usage snippet"]
    if not evidence and text_warning:
        missing.append(text_warning)
    return evidence, missing


def _check_typed(root: Path, facts: RepoFacts) -> tuple[list[str], list[str]]:
    evidence = []
    missing = []
    is_typescript = (
        "javascript/typescript" in facts.languages
        or "typescript" in facts.frontend_tools
        or "typescript" in facts.dev_tools
        or (root / "tsconfig.json").exists()
    )
    is_python = "python" in facts.languages
    is_dart = (root / "pubspec.yaml").exists() or (root / "analysis_options.yaml").exists()

    if is_typescript:
        if (root / "tsconfig.json").exists():
            evidence.append("TypeScript config detected")
        if "typescript" in facts.frontend_tools or "typescript" in facts.dev_tools:
            evidence.append("TypeScript tooling detected")
        if facts.typecheck_tools or any("type" in name for name in facts.commands):
            evidence.append("typecheck command/tool detected")
        if not evidence:
            missing.append("TypeScript config or typecheck evidence")
        return evidence, missing

    if is_dart:
        if (root / "pubspec.yaml").exists():
            evidence.append("Dart pubspec.yaml detected")
        if (root / "analysis_options.yaml").exists():
            evidence.append("Dart analyzer configuration detected")
        if "typecheck" in facts.commands or facts.typecheck_tools:
            evidence.append("Dart analyzer/typecheck command detected")
        return evidence, [] if evidence else ["Dart pubspec.yaml or analyzer evidence"]

    if is_python:
        diagnostics = TraversalDiagnostics(max_visited_entries=MAX_PY_TYPED_SCAN_ENTRIES)
        if _has_py_typed_marker(root, diagnostics=diagnostics):
            evidence.append("py.typed marker detected")
        else:
            missing.append("py.typed marker")
            if diagnostics.incomplete:
                missing.append(diagnostics.warning("py.typed marker discovery"))

    if (
        "typecheck" in facts.commands
        or facts.typecheck_tools
        or any(tool in facts.dev_tools for tool in ["mypy", "pyright"])
    ):
        evidence.append("typecheck command/tool detected")
    else:
        missing.append("typecheck command/tool")
    return evidence, missing


MAX_PY_TYPED_SCAN_ENTRIES = 12_000


def _has_py_typed_marker(
    root: Path,
    *,
    diagnostics: TraversalDiagnostics | None = None,
) -> bool:
    state = diagnostics or TraversalDiagnostics(max_visited_entries=MAX_PY_TYPED_SCAN_ENTRIES)
    for path in _iter_repo_files(
        root,
        diagnostics=state,
        max_visited_entries=MAX_PY_TYPED_SCAN_ENTRIES,
        allow_package_dirs_in_skipped_paths=True,
    ):
        if path.name == "py.typed":
            return True
    return False


def _check_zero_dependencies(root: Path, facts: RepoFacts) -> tuple[list[str], list[str]]:
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return [], ["pyproject.toml dependency metadata"]
    try:
        data = tomllib.loads(safe_read_text(pyproject, root=root, max_chars=500_000))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return [], ["readable pyproject.toml"]
    project = data.get("project") if isinstance(data, dict) else None
    if not isinstance(project, dict) or "dependencies" not in project:
        return [], ["explicit runtime dependency list"]
    dependencies = project.get("dependencies")
    if isinstance(dependencies, list) and not dependencies:
        return ["pyproject.toml declares an empty runtime dependency list"], []
    return [], ["empty runtime dependency list"]


def _check_repo_readiness(root: Path, facts: RepoFacts) -> tuple[list[str], list[str]]:
    evidence = []
    if (root / ".evagix" / "scorecard.json").exists() or (root / ".evagix" / "report.json").exists():
        evidence.append(".evagix readiness report/scorecard detected")
    validator_source = root / "evagix" / "validators.py"
    if validator_source.exists():
        try:
            text = safe_read_text(validator_source, root=root, max_chars=300_000)
            if "doctor_repo" in text and "DoctorReport" in text:
                evidence.append("doctor/readiness scoring implementation detected")
        except (OSError, UnicodeError):
            pass
    return evidence, [] if evidence else [".evagix scorecard/report or readiness scoring evidence"]
