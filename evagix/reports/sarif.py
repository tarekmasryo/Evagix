from __future__ import annotations

from pathlib import Path

from evagix import __version__
from evagix.constants import DEFAULT_GITHUB_REPO
from evagix.model import RepoFacts
from evagix.report_models import DoctorFinding, DoctorReport
from evagix.reports.locations import location_from_finding
from evagix.rules.registry import get_rule
from evagix.utils import stable_json

SEVERITY_TO_SARIF_LEVEL = {"info": "note", "warning": "warning", "error": "error"}


def render_doctor_sarif(root: Path, facts: RepoFacts, report: DoctorReport) -> str:
    rules: dict[str, dict[str, object]] = {}
    results: list[dict[str, object]] = []
    for item in report.findings:
        rules[item.code] = sarif_rule(item)
        results.append(sarif_result(item))
    payload = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "evagix",
                        "version": __version__,
                        "informationUri": f"https://github.com/{DEFAULT_GITHUB_REPO}",
                        "rules": list(rules.values()),
                    }
                },
                "invocations": [{"executionSuccessful": report.ok, "workingDirectory": {"uri": str(root)}}],
                "properties": {"repository": facts.root_name, "readinessScore": report.score},
                "results": results,
            }
        ],
    }
    return stable_json(payload)


def sarif_rule(item: DoctorFinding) -> dict[str, object]:
    rule = get_rule(item.code)
    title = rule.title if rule else item.code.replace("-", " ").replace(".", " ")
    description = rule.description if rule else item.message
    remediation = rule.remediation if rule else _remediation_for(item.code)
    category = rule.category if rule else _category_for_code(item.code)
    help_uri = f"https://github.com/{DEFAULT_GITHUB_REPO}#evagix"
    if rule and rule.docs_anchor:
        help_uri = f"https://github.com/{DEFAULT_GITHUB_REPO}/blob/main/docs/rules-reference.md#{rule.docs_anchor}"
    return {
        "id": item.code,
        "name": item.code,
        "shortDescription": {"text": title},
        "fullDescription": {"text": description},
        "help": {"text": remediation},
        "helpUri": help_uri,
        "properties": {"category": category, "severity": item.severity},
    }


def sarif_result(item: DoctorFinding) -> dict[str, object]:
    location = location_from_finding(item.code, item.message)
    return {
        "ruleId": item.code,
        "level": SEVERITY_TO_SARIF_LEVEL.get(item.severity, "note"),
        "message": {"text": item.message},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": location.uri},
                    "region": {"startLine": location.start_line},
                }
            }
        ],
        "properties": {"penalty": item.penalty},
    }


def _category_for_code(code: str) -> str:
    if code.startswith("readme") or code.startswith("README"):
        return "readme_evidence"
    if code.startswith("agent-context") or code.startswith("context-poisoning"):
        return "agent_context"
    if code.startswith("dangerous-command"):
        return "safety"
    if code in {"missing-ci"}:
        return "ci"
    if "typecheck" in code or "lint" in code or "test" in code:
        return "commands"
    return "repository"


def _remediation_for(code: str) -> str:
    if code.startswith("readme") or code.startswith("README"):
        return "Update the README claim, add repository evidence, or mark the feature as unavailable/planned."
    if code.startswith("agent-context"):
        return "Update the agent context file so its setup, validation, and safety guidance match repository evidence."
    if code.startswith("dangerous-command"):
        return "Remove the dangerous command or rewrite it as a defensive warning."
    if code in {"missing-ci"}:
        return "Add a CI workflow or document that CI is handled externally."
    return "Review the finding and update repository evidence or Evagix configuration."
