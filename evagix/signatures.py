from __future__ import annotations

# Static detection signatures are kept outside scanner.py so detection policy can
# evolve without inflating the scanner orchestration code.

FRAMEWORK_PACKAGES = {
    "fastapi": "fastapi",
    "django": "django",
    "flask": "flask",
    "streamlit": "streamlit",
    "dash": "dash",
    "gradio": "gradio",
    "panel": "panel",
    "typer": "typer",
    "click": "click",
    "langchain": "langchain",
    "langchain-core": "langchain",
    "langchain-community": "langchain",
    "llama-index": "llama-index",
    "llama_index": "llama-index",
    "haystack": "haystack",
}

BACKEND_PACKAGES = {
    "fastapi": "fastapi",
    "django": "django",
    "flask": "flask",
    "starlette": "starlette",
    "uvicorn": "uvicorn",
    "gunicorn": "gunicorn",
    "pydantic": "pydantic",
    "sqlalchemy": "sqlalchemy",
    "alembic": "alembic",
}

LLM_PACKAGES = {
    "langchain": "langchain",
    "langchain-core": "langchain",
    "langchain-community": "langchain",
    "llama-index": "llama-index",
    "llama_index": "llama-index",
    "haystack": "haystack",
    "openai": "openai",
    "anthropic": "anthropic",
    "ollama": "ollama",
    "chromadb": "chromadb",
    "qdrant-client": "qdrant",
    "qdrant_client": "qdrant",
    "faiss-cpu": "faiss",
    "faiss-gpu": "faiss",
    "faiss": "faiss",
    "pgvector": "pgvector",
    "tiktoken": "tiktoken",
    "litellm": "litellm",
    "semantic-kernel": "semantic-kernel",
    "semantic_kernel": "semantic-kernel",
    "crewai": "crewai",
    "autogen": "autogen",
    "mcp": "mcp",
    "dspy": "dspy",
}

ML_DATA_PACKAGES = {
    "numpy": "numpy",
    "pandas": "pandas",
    "polars": "polars",
    "sklearn": "scikit-learn",
    "scikit-learn": "scikit-learn",
    "xgboost": "xgboost",
    "lightgbm": "lightgbm",
    "catboost": "catboost",
    "torch": "torch",
    "tensorflow": "tensorflow",
    "keras": "keras",
    "transformers": "transformers",
    "sentence-transformers": "sentence-transformers",
    "sentence_transformers": "sentence-transformers",
    "matplotlib": "matplotlib",
    "seaborn": "seaborn",
    "plotly": "plotly",
    "altair": "altair",
    "jupyter": "jupyter",
    "notebook": "jupyter",
    "ipykernel": "jupyter",
    "nbformat": "jupyter",
    "joblib": "joblib",
    "nltk": "nltk",
    "spacy": "spacy",
    "mlflow": "mlflow",
    "wandb": "wandb",
}

DEV_PACKAGES = {
    "pytest": "pytest",
    "ruff": "ruff",
    "mypy": "mypy",
    "pyright": "pyright",
    "black": "black",
    "isort": "isort",
    "pre-commit": "pre-commit",
    "coverage": "coverage",
    "pytest-cov": "pytest-cov",
    "tox": "tox",
    "nox": "nox",
    "bandit": "bandit",
    "pip-audit": "pip-audit",
    "flake8": "flake8",
    "pylint": "pylint",
    "pytest-asyncio": "pytest-asyncio",
}

DB_PACKAGES = {
    "sqlalchemy": "sqlalchemy",
    "psycopg": "postgres",
    "psycopg2": "postgres",
    "asyncpg": "postgres",
    "pgvector": "postgres/pgvector",
    "pymongo": "mongodb",
    "motor": "mongodb",
    "duckdb": "duckdb",
    "sqlite3": "sqlite",
}

QUEUE_PACKAGES = {
    "redis": "redis",
    "rq": "redis/rq",
    "celery": "celery",
    "dramatiq": "dramatiq",
    "arq": "arq",
}

NODE_FRAMEWORKS = {
    "next": "next.js",
    "react": "react",
    "vue": "vue",
    "svelte": "svelte",
    "vite": "vite",
    "astro": "astro",
    "remix": "remix",
    "express": "express",
    "@nestjs/core": "nestjs",
    "nestjs": "nestjs",
}

NODE_DEV_TOOLS = {
    "eslint": "eslint",
    "typescript": "typescript",
    "vitest": "vitest",
    "jest": "jest",
    "playwright": "playwright",
    "cypress": "cypress",
    "prettier": "prettier",
    "tsup": "tsup",
    "nx": "nx",
    "turbo": "turbo",
}
