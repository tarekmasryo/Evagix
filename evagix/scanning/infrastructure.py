from __future__ import annotations

import re
from pathlib import Path

from evagix.model import RepoFacts
from evagix.scanner_utils import (
    TraversalDiagnostics,
    _is_ignored_path,
    _is_safe_repo_path,
    _iter_named_files,
    _safe_read,
)
from evagix.scanning.shared import _add_unique, _is_available, _set_command


def _scan_infrastructure_files(root: Path, facts: RepoFacts, ignored_paths: set[str]) -> None:
    tf_files = [
        p
        for p in root.glob("*.tf")
        if _is_safe_repo_path(root, p) and p.is_file() and not _is_ignored_path(root, p, ignored_paths)
    ]
    if tf_files:
        _add_unique(facts.dev_tools, "terraform")
        _add_unique(facts.infrastructure_tools, "terraform")
        _add_unique(facts.config_files, tf_files[0].name)
        _set_command(
            facts,
            "infra_validate",
            "terraform validate",
            tf_files[0].name,
            "Terraform files detected",
            "medium",
        )
        facts.warnings.append("Terraform files detected; infrastructure edits can affect deployed resources.")
    k8s_markers = ["Chart.yaml", "kustomization.yaml", "kustomization.yml"]
    if any(_is_available(root, marker, ignored_paths) for marker in k8s_markers):
        _add_unique(facts.dev_tools, "kubernetes")
        _add_unique(facts.container_platforms, "kubernetes")
        for marker in k8s_markers:
            if _is_available(root, marker, ignored_paths):
                _add_unique(facts.config_files, marker)
        facts.warnings.append("Kubernetes/Helm config detected; runtime changes should be reviewed carefully.")


def _scan_docker(root: Path, facts: RepoFacts, ignored_paths: set[str]) -> None:
    compose_names = {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}
    diagnostics = TraversalDiagnostics()
    candidates = _iter_named_files(
        root,
        {"Dockerfile", *compose_names},
        ignored_paths,
        limit=400,
        diagnostics=diagnostics,
    )
    dockerfiles = [path for path in candidates if path.name == "Dockerfile"]
    compose_files = [path for path in candidates if path.name in compose_names]
    if diagnostics.incomplete:
        facts.warnings.append(diagnostics.warning("Docker and Compose discovery"))

    if dockerfiles:
        _add_unique(facts.container_platforms, "docker")
        _add_unique(facts.dev_tools, "docker")
        for path in dockerfiles[:5]:
            _add_unique(facts.config_files, path.relative_to(root).as_posix())
    if compose_files:
        _add_unique(facts.container_platforms, "docker-compose")
        _add_unique(facts.dev_tools, "docker-compose")
        first = compose_files[0].relative_to(root).as_posix()
        _set_command(
            facts,
            "run",
            f"docker compose -f {first} up --build",
            first,
            "Docker Compose file detected",
            "medium",
        )
        compose_text = "\n".join(_safe_read(path, max_chars=100_000).lower() for path in compose_files)
        db_markers = [
            ("postgres", "postgres"),
            ("pgvector", "postgres/pgvector"),
            ("mysql", "mysql"),
            ("mongodb", "mongodb"),
            ("mongo:", "mongodb"),
        ]
        for db_marker, label in db_markers:
            if db_marker in compose_text:
                _add_unique(facts.databases, label)
        for queue_marker, label in [("redis", "redis"), ("celery", "celery"), ("rabbitmq", "rabbitmq")]:
            if queue_marker in compose_text:
                _add_unique(facts.queues, label)
        for path in compose_files[:5]:
            _add_unique(facts.config_files, path.relative_to(root).as_posix())


def _scan_make_like(root: Path, facts: RepoFacts, ignored_paths: set[str]) -> None:
    for filename, runner in [("Makefile", "make"), ("justfile", "just")]:
        path = root / filename
        if not path.exists() or not _is_safe_repo_path(root, path) or _is_ignored_path(root, path, ignored_paths):
            continue
        _add_unique(facts.dev_tools, runner)
        text = _safe_read(path)
        targets = set(re.findall(r"^([a-zA-Z0-9_.-]+):", text, flags=re.MULTILINE))
        for name in [
            "test",
            "lint",
            "typecheck",
            "build",
            "run",
            "dev",
            "format",
            "install",
            "migrate",
            "doctor",
            "smoke",
        ]:
            if name in targets:
                _set_command(
                    facts,
                    name,
                    f"{runner} {name}",
                    filename,
                    f"target '{name}' detected",
                    "high",
                    prefer=True,
                )
                if name == "lint":
                    _add_unique(facts.lint_tools, runner)
                if name == "typecheck":
                    _add_unique(facts.typecheck_tools, runner)


def _scan_ci(root: Path, facts: RepoFacts, ignored_paths: set[str]) -> None:
    if _is_available(root, ".gitlab-ci.yml", ignored_paths):
        _add_unique(facts.dev_tools, "gitlab-ci")
        _add_unique(facts.ci_platforms, "gitlab-ci")
        facts.ci_workflows.append(".gitlab-ci.yml")
    if _is_available(root, ".circleci/config.yml", ignored_paths):
        _add_unique(facts.dev_tools, "circleci")
        _add_unique(facts.ci_platforms, "circleci")
        facts.ci_workflows.append(".circleci/config.yml")
    azure_pipeline_files = [
        root / "azure-pipelines.yml",
        root / "azure-pipelines.yaml",
    ]

    azure_pipeline_dir = root / ".azure-pipelines"
    if (
        azure_pipeline_dir.exists()
        and _is_safe_repo_path(root, azure_pipeline_dir)
        and not _is_ignored_path(root, azure_pipeline_dir, ignored_paths)
    ):
        azure_pipeline_files.extend(sorted(azure_pipeline_dir.glob("*.y*ml")))

    for azure_pipeline in azure_pipeline_files:
        if (
            azure_pipeline.exists()
            and azure_pipeline.is_file()
            and _is_safe_repo_path(root, azure_pipeline)
            and not _is_ignored_path(root, azure_pipeline, ignored_paths)
        ):
            _add_unique(facts.dev_tools, "azure-pipelines")
            _add_unique(facts.ci_platforms, "azure-pipelines")
            _add_unique(facts.ci_workflows, azure_pipeline.relative_to(root).as_posix())

    workflows = root / ".github" / "workflows"
    if (
        not workflows.exists()
        or not _is_safe_repo_path(root, workflows)
        or _is_ignored_path(root, workflows, ignored_paths)
    ):
        return
    _add_unique(facts.dev_tools, "github-actions")
    _add_unique(facts.ci_platforms, "github-actions")
    for path in sorted(
        path
        for path in workflows.glob("*.y*ml")
        if _is_safe_repo_path(root, path) and not _is_ignored_path(root, path, ignored_paths)
    ):
        rel = path.relative_to(root).as_posix()
        facts.ci_workflows.append(rel)
        raw_text = _safe_read(path)
        text = raw_text.lower()
        for command in _ci_run_commands(raw_text):
            lower_command = command.casefold()
            if "pytest" in lower_command or lower_command.startswith(("make test", "just test")):
                _set_command(
                    facts,
                    "test",
                    command,
                    rel,
                    "exact test command declared in CI",
                    "high",
                    priority=80,
                    status="declared",
                )
            if (
                "ruff check" in lower_command
                or "eslint" in lower_command
                or lower_command.startswith(("make lint", "just lint"))
            ):
                _set_command(
                    facts,
                    "lint",
                    command,
                    rel,
                    "exact lint command declared in CI",
                    "high",
                    priority=80,
                    status="declared",
                )
            if "mypy" in lower_command or "pyright" in lower_command or re.search(r"\btsc\b", lower_command):
                _set_command(
                    facts,
                    "typecheck",
                    command,
                    rel,
                    "exact typecheck command declared in CI",
                    "high",
                    priority=80,
                    status="declared",
                )
        if "pytest" in text or "make test" in text:
            _add_unique(facts.dev_tools, "pytest")
            if "test" not in facts.commands:
                _set_command(
                    facts,
                    "test",
                    "pytest",
                    rel,
                    "test tool referenced in CI; exact command was not parsed",
                    "low",
                    priority=20,
                    status="inferred",
                )
        if "ruff check" in text or "make lint" in text or "eslint" in text:
            _add_unique(facts.lint_tools, "ci-lint")
            if "lint" not in facts.commands:
                _set_command(
                    facts,
                    "lint",
                    "ruff check .",
                    rel,
                    "lint tool referenced in CI; exact command was not parsed",
                    "low",
                    priority=20,
                    status="inferred",
                )
        if "mypy" in text or "pyright" in text or "tsc" in text:
            _add_unique(facts.typecheck_tools, "ci-typecheck")
        if _ci_has_docker_evidence(text):
            _add_unique(facts.dev_tools, "docker")


def _ci_has_docker_evidence(text: str) -> bool:
    docker_actions = (
        "docker/build-push-action",
        "docker/login-action",
        "docker/metadata-action",
        "docker/setup-buildx-action",
    )
    docker_commands = (
        "docker build",
        "docker compose",
        "docker run",
        "docker login",
        "docker pull",
        "docker push",
    )
    service_markers = ("\nservices:", "\n    image:", "\n  image:", "\ncontainer:")
    return any(item in text for item in docker_actions + docker_commands + service_markers)


def _ci_run_commands(text: str) -> list[str]:
    commands: list[str] = []
    for match in re.finditer(r"(?m)^\s*(?:-\s*)?run:\s*([^|>\r\n].*)$", text):
        command = match.group(1).strip().strip(chr(34)).strip(chr(39))
        if command:
            commands.append(command)
    return commands
