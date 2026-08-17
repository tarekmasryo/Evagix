from __future__ import annotations

from pathlib import Path

from evagix.scanner import scan_repo
from evagix.scoped import scoped_outputs
from evagix.validators import doctor_repo

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_fastapi_fixture_detects_backend_and_typecheck():
    facts = scan_repo(FIXTURES / "python_fastapi_postgres")
    assert "python" in facts.languages
    assert "fastapi" in facts.frameworks
    assert "postgres" in facts.databases
    assert "test" not in facts.commands
    assert facts.commands["lint"] == "ruff check ."
    assert facts.commands["typecheck"] == "mypy ."


def test_ml_dashboard_fixture_detects_streamlit_rules_context():
    facts = scan_repo(FIXTURES / "ml_streamlit_dashboard")
    assert "streamlit" in facts.frameworks
    assert "pandas" in facts.ml_data_tools
    assert facts.commands["run"] == "make run"
    report = doctor_repo(FIXTURES / "ml_streamlit_dashboard", facts)
    assert report.score >= 70


def test_polyglot_fixture_detects_frontend_and_scoped_outputs():
    facts = scan_repo(FIXTURES / "polyglot_monorepo")
    assert "javascript/typescript" in facts.languages
    assert "frontend" in {sub.path for sub in facts.subprojects}
    assert "qdrant" in facts.llm_tools
    scoped = scoped_outputs(facts)
    assert "frontend/AGENTS.md" in scoped
    assert "app/AGENTS.md" in scoped
