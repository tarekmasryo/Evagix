from __future__ import annotations

import json
from pathlib import Path

from evagix.cli import main
from evagix.commands.report_audit import audit_payload, render_audit_markdown
from evagix.model import Evidence, RepoFacts
from evagix.report_models import AuditFinding, CategoryScore, DoctorFinding, DoctorReport
from evagix.reports.json import render_json
from evagix.reports.markdown import bullet_list, front_matter, table
from evagix.validation.audit import render_audit_markdown as render_validation_audit_markdown
from evagix.validation.rendering import (
    _escape_github_annotation,
    render_doctor_json,
    render_doctor_markdown,
    render_github_annotations,
)


def _facts(**overrides: object) -> RepoFacts:
    facts = RepoFacts(root_name="demo")
    for key, value in overrides.items():
        setattr(facts, key, value)
    return facts


def test_validation_rendering_outputs_json_markdown_and_annotations(tmp_path: Path) -> None:
    (tmp_path / ".evagix").mkdir()
    (tmp_path / ".evagix" / "context.md").write_text("# Context\n", encoding="utf-8")
    facts = _facts(
        root_name="demo",
        languages=["python"],
        frameworks=["fastapi"],
        backend_tools=["fastapi"],
        frontend_tools=["vite"],
        llm_tools=["langchain"],
        ml_data_tools=["pandas"],
        dev_tools=["ruff"],
        runtimes=["python"],
        databases=["postgres"],
        queues=["redis"],
        commands={"test": "python -m pytest"},
        command_sources={"test": Evidence("pyproject.toml", "pytest", "high")},
        warnings=["No CI workflow was detected."],
        active_profiles=["python-backend"],
    )
    report = DoctorReport(
        score=74,
        findings=[
            DoctorFinding("warning", "README_COMMAND_UNSUPPORTED", "Unsupported README command", 8),
            DoctorFinding("error", "custom-error", "Custom error message", 20),
        ],
        categories={"docs": CategoryScore(82, "warn", ["README_COMMAND_UNSUPPORTED"])},
        domain_scores={"context": CategoryScore(74, "fail", ["custom-error"])},
        maturity_level="needs-work",
    )

    markdown = render_doctor_markdown(tmp_path, facts, report)
    assert "Evagix Readiness Report" in markdown
    assert "`test`: `python -m pytest`" in markdown
    assert "README_COMMAND_UNSUPPORTED" in markdown
    assert "No CI workflow" in markdown
    assert "`.evagix/context.md`: present" in markdown

    payload = json.loads(render_doctor_json(facts, report, fail_under=90))
    assert payload["ok"] is False
    assert payload["fail_under"] == 90
    assert payload["domains"]["context"]["status"] == "fail"

    annotations = render_github_annotations(report)
    assert "::warning" in annotations
    assert "::error" in annotations
    assert "%3A" in _escape_github_annotation("code: value, 100%")
    assert render_github_annotations(DoctorReport(score=100, findings=[])).startswith("::notice")


def test_audit_markdown_and_json_payloads_are_structured(tmp_path: Path) -> None:
    facts = RepoFacts(root_name="demo", active_profiles=["python-cli"], commands={"test": "python -m pytest"})
    report = DoctorReport(score=91, findings=[DoctorFinding("warning", "missing-lint", "No lint command.", 8)])
    findings = [AuditFinding("warning", "risk-flag", "Risk flag")]

    payload = audit_payload(tmp_path, facts, findings, report)
    assert payload["schema_version"] == "1.0"
    assert payload["readiness"]["score"] == 91
    assert payload["readiness"]["score_type"] == "static_evidence"
    assert payload["summary"]["severity_counts"] == {"warning": 1}
    assert "evagix doctor" in " ".join(payload["recommended_next_commands"])

    markdown = render_audit_markdown(tmp_path, facts, findings, report)
    assert "# Evagix Audit" in markdown
    assert "Static evidence score" in markdown
    assert "risk-flag" in markdown
    assert "evagix eval-context" in markdown

    validation_markdown = render_validation_audit_markdown(tmp_path, facts)
    assert "Recommended Validation Commands" in validation_markdown
    assert "python -m pytest" in validation_markdown


def test_audit_format_json_has_stable_schema(tmp_path: Path, capsys) -> None:
    import json

    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    assert main(["audit", str(tmp_path), "--format", "json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1.0"
    assert payload["tool"] == "evagix"
    assert payload["governance_ok"] is True
    assert payload["readiness_ok"] is False
    assert payload["overall_ok"] is False
    assert payload["ok"] is False
    assert payload["summary"]["scope"] == "governance-summary"
    assert payload["readiness"]["score"] >= 0
    assert payload["recommended_next_commands"]
    assert isinstance(payload["findings"], list)


def test_scan_accepts_format_json_alias(tmp_path: Path, capsys) -> None:
    import json

    (tmp_path / "pyproject.toml").write_text('[project]\nname="demo"\n', encoding="utf-8")
    assert main(["scan", str(tmp_path), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1.0"
    assert payload["root_name"] == "demo"
    assert isinstance(payload["runtimes"], list)
    assert isinstance(payload["package_managers"], list)


def test_json_reports_include_summary_and_score_explanations(tmp_path: Path, capsys) -> None:
    import json

    (tmp_path / "README.md").write_text("# Demo\n\nProduction-ready Python package.\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8")

    assert main(["readme-audit", str(tmp_path), "--strict", "--format", "json"]) == 0
    readme_payload = json.loads(capsys.readouterr().out)
    assert "summary" in readme_payload
    assert "weak_evidence_claims" in readme_payload["summary"]
    assert "unsupported_claims" in readme_payload

    assert main(["doctor", str(tmp_path), "--strict", "--format", "json"]) in {0, 1}
    doctor_payload = json.loads(capsys.readouterr().out)
    assert "score_explanations" in doctor_payload
    assert isinstance(doctor_payload["score_explanations"], list)


def test_report_helpers_render_deterministic_markdown_and_json() -> None:
    assert table(["A", "B"], [["1", "2"]]) == "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
    assert bullet_list([]) == "- None.\n"
    assert bullet_list(["one", "two"]) == "- one\n- two\n"
    assert front_matter({"title": "Demo"}) == "---\ntitle: Demo\n---\n"

    rendered = render_json({"b": 2, "a": 1})
    assert json.loads(rendered) == {"a": 1, "b": 2}
    assert rendered.endswith("\n")
