from __future__ import annotations

import json
from pathlib import Path

from evagix.model import RepoFacts
from evagix.report_models import DoctorFinding, DoctorReport
from evagix.reports.sarif import _category_for_code, _remediation_for, render_doctor_sarif, sarif_result, sarif_rule


def _facts(**overrides: object) -> RepoFacts:
    facts = RepoFacts(root_name="demo")
    for key, value in overrides.items():
        setattr(facts, key, value)
    return facts


def test_sarif_renders_empty_findings_with_valid_shape(tmp_path: Path) -> None:
    report = DoctorReport(score=100, findings=[], maturity_level="ready")
    payload = json.loads(render_doctor_sarif(tmp_path, _facts(), report))

    run = payload["runs"][0]
    assert payload["version"] == "2.1.0"
    assert run["tool"]["driver"]["name"] == "evagix"
    assert run["tool"]["driver"]["rules"] == []
    assert run["results"] == []
    assert run["invocations"][0]["executionSuccessful"] is True
    assert run["properties"]["readinessScore"] == 100


def test_sarif_renders_multiple_findings_levels_locations_and_registry_help(tmp_path: Path) -> None:
    findings = [
        DoctorFinding("info", "missing-ci", "No CI workflow detected.", 4),
        DoctorFinding(
            "warning",
            "dangerous-command.cat-env",
            "Dangerous command detected; source: README.md:7; confidence: high",
            12,
        ),
        DoctorFinding("error", "custom-unknown-rule", "Custom issue without registry metadata.", 25),
    ]
    report = DoctorReport(score=70, findings=findings, maturity_level="needs-work")

    payload = json.loads(render_doctor_sarif(tmp_path, _facts(root_name="demo-repo"), report))
    run = payload["runs"][0]
    levels = [result["level"] for result in run["results"]]
    assert levels == ["note", "warning", "error"]
    assert run["invocations"][0]["executionSuccessful"] is False
    assert {rule["id"] for rule in run["tool"]["driver"]["rules"]} == {
        "missing-ci",
        "dangerous-command.cat-env",
        "custom-unknown-rule",
    }
    assert any("docs/rules-reference.md" in rule["helpUri"] for rule in run["tool"]["driver"]["rules"])
    dangerous_location = run["results"][1]["locations"][0]["physicalLocation"]
    assert dangerous_location["artifactLocation"]["uri"] == "README.md"
    assert dangerous_location["region"]["startLine"] == 7
    assert run["results"][2]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "."


def test_sarif_helpers_cover_fallback_categories_and_remediation() -> None:
    assert _category_for_code("README_COMMAND_UNSUPPORTED") == "readme_evidence"
    assert _category_for_code("agent-context.missing-test") == "agent_context"
    assert _category_for_code("context-poisoning.ignore-instructions") == "agent_context"
    assert _category_for_code("dangerous-command.rm-rf-root") == "safety"
    assert _category_for_code("missing-ci") == "ci"
    assert _category_for_code("missing-typecheck") == "commands"
    assert _category_for_code("custom-rule") == "repository"

    assert "README" in _remediation_for("README_COMMAND_UNSUPPORTED")
    assert "agent context" in _remediation_for("agent-context.missing-test")
    assert "dangerous command" in _remediation_for("dangerous-command.rm-rf-root")
    assert "CI" in _remediation_for("missing-ci")
    assert "Review" in _remediation_for("custom-rule")

    unknown_severity = DoctorFinding("critical", "custom-rule", "Message", 1)
    assert sarif_result(unknown_severity)["level"] == "note"
    assert sarif_rule(unknown_severity)["properties"]["category"] == "repository"
