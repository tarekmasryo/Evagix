from __future__ import annotations

from textwrap import dedent

from evagix.model import RepoFacts


def _backend_api_rules(facts: RepoFacts) -> str:
    lines = [
        "## Backend/API Rules",
        "",
        "- Do not change public routes, request/response schemas, auth behavior, or error semantics without documenting the compatibility impact.",
        "- Keep API handlers thin; preserve service/repository boundaries when they already exist.",
        "- Validate startup/config changes against the documented runtime path before claiming the app works.",
    ]
    if "fastapi" in facts.frameworks:
        lines.append("- For FastAPI, keep Pydantic schemas explicit and avoid silently widening accepted inputs.")
    if "sqlalchemy" in facts.frameworks or "sqlalchemy" in facts.backend_tools:
        lines.append("- Keep SQLAlchemy session boundaries explicit; avoid hidden global sessions or implicit commits.")
    return "\n".join(lines)


def _database_rules(facts: RepoFacts) -> str:
    return dedent(
        """
        ## Database & Migration Rules

        - Treat schema changes and migration edits as high-risk; explain forward/backward impact before editing them.
        - Do not delete, squash, or rewrite existing migrations unless explicitly requested.
        - Keep model/schema changes aligned with migrations and tests.
        - Avoid destructive data operations and volume resets unless the task explicitly scopes them.
        """
    ).strip()


def _worker_queue_rules(facts: RepoFacts) -> str:
    return dedent(
        """
        ## Worker/Queue Rules

        - Do not change task names, queue names, payload shapes, retry behavior, or idempotency assumptions without checking producers and consumers.
        - Preserve observability around background jobs, failures, retries, and dead-letter behavior when present.
        - Treat Redis/Celery/RQ configuration as runtime-critical; avoid silent default changes.
        """
    ).strip()


def _llm_rag_rules(facts: RepoFacts) -> str:
    lines = [
        "## AI/Retrieval Rules",
        "",
        "- Do not change prompts, retrieval behavior, chunking, embeddings, reranking, or model "
        "defaults without documenting expected quality and latency impact.",
        "- Preserve citation/grounding behavior where present; do not make answers appear more certain than the evidence supports.",
        "- Keep provider keys, local model paths, and endpoint configuration out of committed files.",
        "- For behavior changes, add or update a small evaluation note, fixture, or regression check when feasible.",
    ]
    if {"chromadb", "qdrant", "faiss", "pgvector"}.intersection(facts.llm_tools):
        lines.append(
            "- Treat vector index resets or embedding-regeneration steps as destructive unless explicitly requested."
        )
    return "\n".join(lines)


def _ml_project_rules(facts: RepoFacts) -> str:
    lines = [
        "## ML/Data Project Rules",
        "",
        "- Do not change train/test splits, random seeds, labels, or evaluation metrics without documenting the reason.",
        "- Do not report model quality without naming the validation/test split and metric definition.",
        "- Watch for data leakage between preprocessing, feature engineering, training, validation, and test data.",
        "- Keep preprocessing and modeling steps reproducible; prefer deterministic seeds where supported.",
        "- Do not overwrite trained artifacts, datasets, or generated reports unless the task explicitly requires regeneration.",
    ]
    if {"pandas", "polars"}.intersection(facts.ml_data_tools):
        lines.append(
            "- Preserve schema assumptions; check column names, dtypes, missing values, and target leakage before edits."
        )
    if {"scikit-learn", "xgboost", "lightgbm", "catboost"}.intersection(facts.ml_data_tools):
        lines.append(
            "- Keep model pipelines and preprocessing aligned so inference uses the same transformations as training."
        )
    if {"mlflow", "wandb"}.intersection(facts.ml_data_tools):
        lines.append(
            "- Treat experiment tracking outputs as audit artifacts; do not rewrite experiment history casually."
        )
    return "\n".join(lines)


def _dashboard_rules(facts: RepoFacts) -> str:
    return dedent(
        """
        ## Dashboard/App Rules

        - Preserve the existing user journey before changing layout, navigation, or state handling.
        - Keep expensive data/model loading cached or explicitly scoped to avoid slow reloads.
        - Do not hard-code local machine paths, private datasets, or secrets into the app.
        - Validate that app run commands still work after UI or dependency changes.
        """
    ).strip()


def _frontend_rules(facts: RepoFacts) -> str:
    return dedent(
        """
        ## Frontend Rules

        - Keep package-manager commands scoped to the detected subproject path.
        - Prefer lockfile-respecting installs; do not switch package managers without explicit justification.
        - Preserve routing, state management, forms, and API contracts unless the task explicitly changes them.
        - Do not suppress TypeScript, ESLint, or build errors without fixing the underlying issue or documenting the tradeoff.
        - Validate production build commands after dependency or UI structure changes when available.
        """
    ).strip()


def _runtime_rules(facts: RepoFacts) -> str:
    lines = ["## Runtime/Infrastructure Rules", ""]
    if "docker" in facts.runtimes or "docker-compose" in facts.runtimes:
        lines.extend(
            [
                "- Treat Dockerfiles, Compose files, and runtime env vars as deployment-critical.",
                "- Do not delete Docker volumes, reset databases, or clean containers broadly unless explicitly requested.",
                "- Keep health/readiness behavior stable when changing service startup paths.",
            ]
        )
    if "terraform" in facts.runtimes:
        lines.append(
            "- Treat Terraform plans/applies as deployment-impacting; review plans before applying infrastructure changes."
        )
    if "kubernetes" in facts.runtimes:
        lines.append(
            "- Treat Kubernetes manifests, Helm charts, and Kustomize overlays as runtime-critical configuration."
        )
    return "\n".join(lines)
