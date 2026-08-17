from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

CONFIDENCE_SCORES = {"high": 0.9, "medium": 0.65, "low": 0.35}


@dataclass(frozen=True)
class Evidence:
    source: str
    detail: str
    confidence: str = "medium"
    confidence_score: float = -1.0
    status: str = "declared"
    reason: str = ""
    path: str = ""
    line: int | None = None

    def __post_init__(self) -> None:
        try:
            expected = CONFIDENCE_SCORES[self.confidence]
        except KeyError as exc:
            raise ValueError(f"Unsupported confidence label: {self.confidence}") from exc
        if self.confidence_score == -1.0:
            object.__setattr__(self, "confidence_score", expected)
        elif abs(self.confidence_score - expected) > 1e-9:
            raise ValueError(
                f"confidence_score {self.confidence_score} conflicts with confidence {self.confidence!r} ({expected})"
            )
        if self.status not in {"verified", "configured", "declared", "inferred"}:
            raise ValueError(f"Unsupported evidence status: {self.status}")


@dataclass(frozen=True)
class Subproject:
    path: str
    kind: str
    package_manager: str = ""
    frameworks: tuple[str, ...] = field(default_factory=tuple)
    dev_tools: tuple[str, ...] = field(default_factory=tuple)
    commands: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "frameworks", tuple(self.frameworks))
        object.__setattr__(self, "dev_tools", tuple(self.dev_tools))
        object.__setattr__(self, "commands", dict(self.commands))


@dataclass(frozen=True)
class EcosystemDetectionFact:
    id: str
    name: str
    path: str
    language: str
    support: str
    confidence: str
    evidence: tuple[str, ...] = field(default_factory=tuple)
    package_manager: str = ""
    frameworks: tuple[str, ...] = field(default_factory=tuple)
    tools: tuple[str, ...] = field(default_factory=tuple)
    commands: dict[str, str] = field(default_factory=dict)
    command_evidence: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "frameworks", tuple(self.frameworks))
        object.__setattr__(self, "tools", tuple(self.tools))
        object.__setattr__(self, "commands", dict(self.commands))
        object.__setattr__(self, "command_evidence", dict(self.command_evidence))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass
class RepoFacts:
    root_name: str
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    backend_tools: list[str] = field(default_factory=list)
    frontend_tools: list[str] = field(default_factory=list)
    llm_tools: list[str] = field(default_factory=list)
    ml_data_tools: list[str] = field(default_factory=list)
    dev_tools: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    ci_platforms: list[str] = field(default_factory=list)
    infrastructure_tools: list[str] = field(default_factory=list)
    container_platforms: list[str] = field(default_factory=list)
    databases: list[str] = field(default_factory=list)
    queues: list[str] = field(default_factory=list)
    runtimes: list[str] = field(default_factory=list)
    commands: dict[str, str] = field(default_factory=dict)
    command_sources: dict[str, Evidence] = field(default_factory=dict)
    _command_priorities: dict[str, int] = field(default_factory=dict, repr=False)
    folders: list[str] = field(default_factory=list)
    ci_workflows: list[str] = field(default_factory=list)
    test_paths: list[str] = field(default_factory=list)
    lint_tools: list[str] = field(default_factory=list)
    typecheck_tools: list[str] = field(default_factory=list)
    generated_targets: list[str] = field(default_factory=list)
    subprojects: list[Subproject] = field(default_factory=list)
    ecosystems: list[EcosystemDetectionFact] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    active_profiles: list[str] = field(default_factory=list)
    custom_rules: list[str] = field(default_factory=list)
    custom_forbidden_actions: list[str] = field(default_factory=list)
    ignored_paths: list[str] = field(default_factory=list)
    readme_ignore_claims: list[str] = field(default_factory=list)
    config_path: str = ""
    classification: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("_command_priorities", None)
        data["command_sources"] = {k: asdict(v) for k, v in self.command_sources.items()}
        data["subprojects"] = [asdict(item) for item in self.subprojects]
        data["ecosystems"] = [asdict(item) for item in self.ecosystems]
        return data

    @property
    def is_ml_project(self) -> bool:
        ml_markers = {
            "numpy",
            "pandas",
            "polars",
            "scikit-learn",
            "xgboost",
            "lightgbm",
            "catboost",
            "torch",
            "tensorflow",
            "keras",
            "transformers",
            "sentence-transformers",
            "matplotlib",
            "seaborn",
            "plotly",
            "altair",
            "jupyter",
            "joblib",
            "spacy",
            "nltk",
        }
        return bool(ml_markers.intersection(self.ml_data_tools))

    @property
    def is_dashboard_project(self) -> bool:
        return bool({"streamlit", "dash", "gradio", "panel"}.intersection(self.frameworks))

    @property
    def is_backend_project(self) -> bool:
        backend_markers = {
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
        }
        return bool(backend_markers.intersection(self.backend_tools) or backend_markers.intersection(self.frameworks))

    @property
    def is_frontend_project(self) -> bool:
        return bool(self.frontend_tools or {"react", "next.js", "vue", "svelte", "vite"}.intersection(self.frameworks))

    @property
    def is_llm_project(self) -> bool:
        return bool(self.llm_tools or {"langchain", "llama-index", "haystack"}.intersection(self.frameworks))

    @property
    def has_database_migrations(self) -> bool:
        return "alembic" in self.backend_tools or any("migration" in flag for flag in self.risk_flags)
