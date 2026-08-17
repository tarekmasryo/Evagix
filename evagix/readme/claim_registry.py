from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from evagix.model import RepoFacts
from evagix.readme.claim_checks import (
    _check_agent_instructions,
    _check_ci,
    _check_cli_tool,
    _check_deployable,
    _check_dockerized,
    _check_examples,
    _check_fastapi,
    _check_llm,
    _check_monitoring,
    _check_package_installable,
    _check_production_ready,
    _check_repo_readiness,
    _check_secure,
    _check_tested,
    _check_typed,
    _check_zero_dependencies,
)

ClaimRule = tuple[str, str, Callable[[Path, RepoFacts], tuple[list[str], list[str]]], str]


def claim_rules() -> list[tuple[str, str, Callable[[Path, RepoFacts], tuple[list[str], list[str]]], str]]:
    return [
        (
            "tested",
            r"\b(tested|test coverage|unit tests?|integration tests?)\b",
            _check_tested,
            "Say `includes test scaffolding` or add a clear test command and tests.",
        ),
        (
            "dockerized",
            r"\b(dockerized|docker-ready|containerized|docker compose|docker supported|docker support)\b",
            _check_dockerized,
            "Say `Docker support is planned` or add Dockerfile/Compose evidence.",
        ),
        (
            "ci/cd",
            r"\b(ci/cd|continuous integration|github actions|automated checks?)\b",
            _check_ci,
            "Say `manual validation documented` or add a CI workflow.",
        ),
        ("fastapi", r"\bfastapi\b", _check_fastapi, "Remove `FastAPI` or add FastAPI dependency/import evidence."),
        (
            "ai/llm",
            (
                r"\b((?:rag)(?!-)|llm app(?:s)?|llm service(?:s)?|llm tooling|llm support|"
                r"large language model(?:s)?|retrieval augmented generation|vector search|embedding model(?:s)?|vector embeddings?)\b"
            ),
            _check_llm,
            "Say `planned AI/Retrieval support` or add actual AI/Retrieval dependency/config evidence.",
        ),
        (
            "monitoring",
            (
                r"\b(monitoring|observability|prometheus|grafana|opentelemetry|structured logging|"
                r"runtime metrics|service metrics|application metrics)\b|/metrics\b"
            ),
            _check_monitoring,
            "Say `basic logging` or add metrics/observability evidence.",
        ),
        (
            "secure",
            r"\b(secure|security-hardened|hardened|production security)\b",
            _check_secure,
            "Say `security-conscious` unless scans, auth, secret handling, and CI evidence exist.",
        ),
        (
            "production-ready",
            r"\b(production-ready|production ready|enterprise-ready|enterprise ready)\b",
            _check_production_ready,
            (
                "Keep the claim only if README/docs show tests, CI, env/runtime docs, and health/observability evidence; "
                "otherwise use a narrower phrase such as `production-oriented`."
            ),
        ),
        (
            "deployable",
            r"\b(deployable|deployment-ready|ready to deploy)\b",
            _check_deployable,
            "Say `includes local run instructions` or add deployment/runtime evidence.",
        ),
        (
            "agent-instructions",
            (
                r"\b(AGENTS\.md|CLAUDE\.md|GEMINI\.md|Cursor|Copilot|Windsurf|"
                r"AI coding[- ]agent instructions?|agent instruction packs?)\b"
            ),
            _check_agent_instructions,
            "Say `AI-agent guidance planned` or add generated agent instruction targets/renderers.",
        ),
        (
            "cli-tool",
            r"\b(cli|command[- ]line|terminal command|console script)\b",
            _check_cli_tool,
            "Say `library/tooling` or add a language-appropriate CLI entry point, such as Python console_scripts or Node package.json bin.",
        ),
        (
            "package-installable",
            r"\b(pip install|installable package|python package|package installable|published package|published on pypi|available on pypi|pypi package)\b",
            _check_package_installable,
            "Add pyproject.toml/package structure evidence or soften the packaging claim.",
        ),
        (
            "examples",
            r"\b(examples?|sample project|demo repo|quickstart example)\b",
            _check_examples,
            "Add examples/ or README usage snippets that users and agents can reproduce.",
        ),
        (
            "typed",
            r"\b(typed|type[- ]checked|mypy|pyright|static typing)\b",
            _check_typed,
            "Add language-appropriate type evidence, such as py.typed for Python packages or TypeScript config/typecheck commands for TypeScript projects.",
        ),
        (
            "zero-dependencies",
            r"\b(zero runtime dependencies|no runtime dependencies|dependency[- ]free)\b",
            _check_zero_dependencies,
            "Keep dependency-free claims only when project metadata has no runtime dependencies.",
        ),
        (
            "repo-readiness",
            r"\b(repo[- ]readiness|agent readiness|readiness score|readiness report)\b",
            _check_repo_readiness,
            "Say `basic repository scan` or add doctor/readiness scoring evidence.",
        ),
    ]
