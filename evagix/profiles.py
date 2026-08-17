from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from evagix.model import Subproject


class ProfileFacts(Protocol):
    languages: list[str]
    subprojects: list[Subproject]
    runtimes: list[str]
    infrastructure_tools: list[str]
    container_platforms: list[str]
    databases: list[str]
    queues: list[str]

    @property
    def is_backend_project(self) -> bool: ...

    @property
    def is_llm_project(self) -> bool: ...

    @property
    def is_ml_project(self) -> bool: ...

    @property
    def is_dashboard_project(self) -> bool: ...

    @property
    def is_frontend_project(self) -> bool: ...


@dataclass(frozen=True)
class ProfileDefinition:
    name: str
    title: str
    description: str
    category: str


PROFILES: dict[str, ProfileDefinition] = {
    "python-backend": ProfileDefinition(
        name="python-backend",
        title="Python Backend Service",
        description="FastAPI/Django/Flask style backend services with APIs, config, tests, and deployment runtime.",
        category="backend",
    ),
    "ai-service": ProfileDefinition(
        name="ai-service",
        title="AI / Retrieval Service",
        description="Retrieval, prompts, embeddings, vector indexes, evals, provider configuration, and grounding safety.",
        category="ai",
    ),
    "ml-dashboard": ProfileDefinition(
        name="ml-dashboard",
        title="ML / Data Dashboard",
        description="Data apps, metrics, datasets, artifacts, model pipelines, dashboards, and reproducibility.",
        category="ai",
    ),
    "frontend-app": ProfileDefinition(
        name="frontend-app",
        title="Frontend Application",
        description="React/Vue/Svelte/Next/Vite apps with build, typecheck, lint, routes, and API contracts.",
        category="frontend",
    ),
    "polyglot-monorepo": ProfileDefinition(
        name="polyglot-monorepo",
        title="Polyglot / Monorepo",
        description="Repositories with multiple languages, package managers, or nested subprojects.",
        category="platform",
    ),
    "infra-heavy": ProfileDefinition(
        name="infra-heavy",
        title="Infrastructure Heavy Repository",
        description="Docker, Compose, Terraform, Kubernetes, databases, queues, and runtime-critical configs.",
        category="platform",
    ),
}


def normalize_profiles(names: Iterable[str] | None) -> list[str]:
    normalized: list[str] = []
    for raw in names or []:
        name = raw.strip().lower()
        if not name:
            continue
        if name not in PROFILES:
            raise ValueError(f"Unknown profile: {raw}")
        if name not in normalized:
            normalized.append(name)
    return normalized


def infer_profiles(facts: ProfileFacts) -> list[str]:
    profiles: list[str] = []

    def add(name: str) -> None:
        if name not in profiles:
            profiles.append(name)

    if facts.is_backend_project and "python" in facts.languages:
        add("python-backend")
    if facts.is_llm_project:
        add("ai-service")
    if facts.is_ml_project or facts.is_dashboard_project:
        add("ml-dashboard")
    if facts.is_frontend_project:
        add("frontend-app")
    domain_languages = [language for language in facts.languages if language not in {"ci", "github-actions"}]
    real_subprojects = [
        sub
        for sub in facts.subprojects
        if sub.path != "." and sub.kind not in {"ci", "github_actions", "github-actions"}
    ]
    if len(set(domain_languages)) > 1 or len(real_subprojects) > 1:
        add("polyglot-monorepo")
    if facts.infrastructure_tools or facts.container_platforms or facts.databases or facts.queues:
        add("infra-heavy")
    return profiles


def profile_display(profiles: Iterable[str]) -> str:
    items = []
    for name in profiles:
        definition = PROFILES.get(name)
        if definition:
            items.append(f"{definition.title} (`{definition.name}`)")
    return ", ".join(items) if items else "not detected"


def profile_rules(profile: str) -> list[str]:
    rules: dict[str, list[str]] = {
        "python-backend": [
            "Keep service boundaries explicit; avoid moving business logic into HTTP handlers during quick fixes.",
            "Validate API changes with tests or a documented smoke request before claiming compatibility.",
            "Treat config/env changes as runtime-sensitive and document new required variables.",
        ],
        "ai-service": [
            "Treat retrieval quality, citation behavior, prompt changes, and model/provider defaults as product behavior changes.",
            "Prefer adding small eval fixtures or smoke cases when retrieval, chunking, embeddings, prompts, or reranking change.",
            "Do not reset vector stores, regenerate embeddings, or alter index schemas without explicit scope and rollback notes.",
        ],
        "ml-dashboard": [
            "Preserve reproducibility: seeds, splits, metrics, artifact paths, and preprocessing assumptions should remain explicit.",
            "For UI changes, keep metrics and data filters understandable to non-technical users.",
            "Treat generated reports, model artifacts, and experiment runs as audit assets unless regeneration is requested.",
        ],
        "frontend-app": [
            "Keep dependency installs scoped to the frontend subproject and respect the detected package manager/lockfile.",
            "Validate build/typecheck/lint where available after route, state, form, API-client, or dependency changes.",
            "Do not hide TypeScript/ESLint/build errors with broad ignores or suppressions.",
        ],
        "polyglot-monorepo": [
            "Scope commands to the correct subproject path; avoid running broad commands from the repository root unless intended.",
            "Mention which subproject was changed and which scoped validation commands were run.",
            "Do not switch package managers or workspace layout without explicit justification.",
        ],
        "infra-heavy": [
            "Treat Docker, Compose, Kubernetes, Terraform, and env files as deployment-critical; prefer minimal diffs.",
            "Do not delete volumes, reset databases, rotate credentials, or rewrite runtime state unless explicitly requested.",
            "Document startup, health/readiness, migration, and rollback impact for runtime changes.",
        ],
    }
    return rules.get(profile, [])


def profile_markdown(profiles: Iterable[str]) -> str:
    lines: list[str] = []
    for name in profiles:
        definition = PROFILES.get(name)
        if not definition:
            continue
        lines.append(f"### {definition.title}")
        lines.append("")
        lines.append(definition.description)
        lines.append("")
        for rule in profile_rules(name):
            lines.append(f"- {rule}")
        lines.append("")
    return "\n".join(lines).strip()
