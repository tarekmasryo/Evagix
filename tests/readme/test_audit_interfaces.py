from __future__ import annotations

import json
from pathlib import Path

import pytest
from pytest import CaptureFixture

from evagix.cli import main
from evagix.readme_audit import audit_readme, render_readme_audit_markdown
from evagix.scanner import scan_repo


def test_readme_audit_github_annotations_for_command_mismatch(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\n```bash\npytest\n```\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\ndependencies = ["pytest"]\n', encoding="utf-8")
    (tmp_path / "evagix.toml").write_text('[commands]\ntest = "make test"\n', encoding="utf-8")

    assert main(["readme-audit", str(tmp_path), "--format", "github-annotations"]) == 0
    output = capsys.readouterr().out
    assert "::warning file=README.md" in output
    assert "suggested replacement: make test" in output


def test_readme_audit_json_output_is_valid(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\nDocker support planned.\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM python:3.11-slim\n", encoding="utf-8")
    output = tmp_path / "audit.json"
    assert main(["readme-audit", str(tmp_path), "--format", "json", "-o", str(output.name)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["tool"] == "evagix"


def test_readme_audit_handles_missing_readme(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")
    facts = scan_repo(tmp_path)
    report = audit_readme(tmp_path, facts)
    assert report.score == 0
    assert report.claims == []
    assert "No README was found" in render_readme_audit_markdown(tmp_path, facts)


def test_readme_audit_ignore_blocks_hide_claims(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n\n<!-- evagix:audit-ignore-start -->\nDockerized secure platform.\n<!-- evagix:audit-ignore-end -->\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")
    report = audit_readme(tmp_path, scan_repo(tmp_path))
    assert report.claims == []


def test_readme_audit_supports_core_evidence_types(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n\nTested FastAPI LLM service with CI/CD, Dockerized monitoring, deployment-ready security-hardened production-ready setup.\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["fastapi", "pytest", "ruff", "langchain", "prometheus-client", "pre-commit"]\n',
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: CI\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM python:3.11\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("API_KEY=example\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("# /health /metrics auth secret token\n", encoding="utf-8")

    report = audit_readme(tmp_path, scan_repo(tmp_path))
    by_claim = {item.claim: item for item in report.claims}
    for claim in ["tested", "fastapi", "ai/llm", "ci/cd", "dockerized", "monitoring"]:
        assert by_claim[claim].verdict == "supported"
    assert by_claim["deployable"].evidence
    assert by_claim["secure"].evidence
    assert by_claim["production-ready"].evidence


def test_readme_audit_json_and_command_freshness(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\n```bash\npytest\nruff check .\n```\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["pytest", "ruff"]\n',
        encoding="utf-8",
    )
    (tmp_path / "evagix.toml").write_text('[commands]\ntest = "make test"\nlint = "make lint"\n', encoding="utf-8")
    assert main(["readme-audit", str(tmp_path), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    replacements = {
        item["phrase"]: item["suggested_replacement"] for item in payload["claims"] if item["claim"] == "readme-command"
    }
    assert replacements["pytest"] == "make test"
    assert replacements["ruff check ."] == "make lint"
