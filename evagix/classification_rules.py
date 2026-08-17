from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class _Rule:
    name: str
    label: str
    required_any: tuple[str, ...] = ()
    supporting_any: tuple[str, ...] = ()
    path_any: tuple[str, ...] = ()
    min_required: int = 1
    primary_candidate: bool = True
    priority: int = 50


def _rules() -> tuple[_Rule, ...]:
    return (
        _Rule(
            "fullstack-ai-service",
            "Full-stack AI Service",
            required_any=("fastapi", "langchain", "qdrant", "chromadb", "faiss", "pgvector", "react", "next.js"),
            supporting_any=("docker-compose", "postgres", "redis", "vite", "typescript", "pytest"),
            min_required=3,
            priority=95,
        ),
        _Rule(
            "python-cli",
            "Python CLI Tool",
            required_any=("python",),
            path_any=("pyproject:scripts", "evagix/cli.py", "*/cli.py"),
            supporting_any=("pytest", "ruff", "mypy"),
            min_required=2,
        ),
        _Rule(
            "python-package",
            "Python Package",
            required_any=("python",),
            path_any=("pyproject.toml", "*/__init__.py"),
            supporting_any=("py.typed", "build", "twine"),
            min_required=2,
        ),
        _Rule(
            "fastapi-service",
            "FastAPI API Service",
            required_any=("fastapi",),
            supporting_any=("uvicorn", "pydantic", "pytest", "docker"),
            priority=75,
        ),
        _Rule("flask-app", "Flask App", required_any=("flask",), supporting_any=("pytest", "gunicorn", "docker")),
        _Rule(
            "django-app",
            "Django App",
            required_any=("django",),
            path_any=("manage.py",),
            supporting_any=("pytest", "postgres"),
        ),
        _Rule(
            "ml-dashboard",
            "ML Dashboard",
            required_any=("streamlit", "gradio", "dash", "panel"),
            supporting_any=("pandas", "scikit-learn", "plotly", "matplotlib"),
        ),
        _Rule(
            "rag-service",
            "RAG / Retrieval Service",
            required_any=("langchain", "llama-index", "haystack", "qdrant", "chromadb", "faiss", "pgvector"),
            supporting_any=("fastapi", "streamlit", "openai", "anthropic"),
            priority=90,
        ),
        _Rule(
            "agentic-ai-workflow",
            "Agentic AI Workflow",
            required_any=("langgraph", "crewai", "autogen", "semantic-kernel"),
            supporting_any=("openai", "anthropic", "fastapi"),
        ),
        _Rule(
            "llmops-telemetry",
            "LLMOps / Telemetry Repo",
            required_any=("langfuse", "opentelemetry", "prometheus", "grafana", "mlflow"),
            supporting_any=("fastapi", "postgres", "redis"),
        ),
        _Rule(
            "data-pipeline",
            "Data Pipeline",
            required_any=("airflow", "prefect", "dagster", "dbt", "duckdb", "polars"),
            supporting_any=("pandas", "sqlalchemy", "postgres"),
        ),
        _Rule(
            "react-frontend",
            "React Frontend",
            required_any=("react",),
            supporting_any=("vite", "next.js", "typescript"),
            priority=45,
        ),
        _Rule(
            "fullstack-app",
            "Full-stack Web App",
            required_any=("react", "next.js", "vue", "svelte"),
            supporting_any=("fastapi", "django", "flask", "express"),
            min_required=1,
            priority=80,
        ),
        _Rule(
            "dockerized-app",
            "Dockerized App",
            required_any=("docker", "docker-compose"),
            supporting_any=("ci",),
            primary_candidate=False,
        ),
        _Rule(
            "ci-enabled-repo",
            "CI-enabled Repository",
            required_any=("github-actions", "gitlab-ci", "circleci", "azure-pipelines"),
            supporting_any=("pytest", "ruff", "mypy"),
            primary_candidate=False,
        ),
        _Rule(
            "typed-python-project",
            "Typed Python Project",
            required_any=("python", "mypy", "pyright"),
            path_any=("*/py.typed",),
            supporting_any=("ruff", "pytest"),
            min_required=2,
            primary_candidate=False,
        ),
        _Rule(
            "polyglot-monorepo",
            "Polyglot / Monorepo",
            required_any=("python", "javascript/typescript", "go", "rust", "java", "dotnet"),
            supporting_any=("workspace", "package.json", "pyproject.toml"),
            min_required=2,
            priority=70,
        ),
        _Rule(
            "docs-only-repo",
            "Documentation / Knowledge Repo",
            path_any=("mkdocs.yml", "docusaurus.config.js", "docs/", "README.md"),
            supporting_any=("markdown",),
            min_required=1,
        ),
    )


def _is_primary_candidate(name: str) -> bool:
    non_primary = {"dockerized-app", "ci-enabled-repo", "typed-python-project"}
    return name not in non_primary


def _rule_priority(name: str) -> int:
    for rule in _rules():
        if rule.name == name:
            return rule.priority
    return 50
