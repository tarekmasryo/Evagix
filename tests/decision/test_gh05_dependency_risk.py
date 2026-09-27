from __future__ import annotations

import json
from pathlib import Path

import pytest

from evagix import changes as changes_module
from evagix.changes import _classify_changed_path, build_changed_report, render_changed_json
from evagix.model import RepoFacts
from evagix.pr_risk import build_pr_risk_report, render_pr_risk_json
from evagix.validators import CheckResult, DoctorReport

DEPENDENCY_PATHS = (
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-prod.txt",
    "requirements-test.txt",
    "nested/path/to/requirements-ci.txt",
    "services/api/requirements.txt",
    "services/api/requirements-dev.txt",
    r"services\api\REQUIREMENTS.TXT",
)


@pytest.mark.parametrize("path", DEPENDENCY_PATHS)
def test_dependency_changes_require_high_risk_gates(path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(changes_module, "_git_changed_files", lambda *args, **kwargs: [path])

    report = build_changed_report(tmp_path)
    payload = json.loads(render_changed_json(report))

    assert len(report.files) == 1
    assert report.files[0].path == path.replace("\\", "/")
    assert report.files[0].risk == "HIGH"
    assert report.has_high_risk is True
    assert report.required_gates == ["evagix check", "evagix doctor", "human approval"]
    assert payload["files"][0]["risk"] == "HIGH"
    assert payload["has_high_risk"] is True
    assert payload["required_gates"] == report.required_gates


@pytest.mark.parametrize(
    "path",
    (
        "notes.txt",
        "services/api/notes.txt",
        "auth/notes.txt",
        "requirements/notes.txt",
        "my-requirements-prod.txt",
        "requirements-prod.txt.md",
        "migrations/README.md",
        "docs/requirements.txt",
        "tests/requirements-dev.txt",
        "examples/service/requirements.txt",
        "docs/requirements-prod.txt",
        "tests/requirements-test.txt",
        "examples/service/requirements-ci.txt",
        "docs/security/auth.md",
        "tests/migrations/test_001.py",
        "examples/deploy/demo.yml",
    ),
)
def test_dependency_precedence_preserves_documentation_tests_and_examples(path: str) -> None:
    result = _classify_changed_path(path)

    assert result.risk == "LOW"
    assert result.reason == "documentation, tests, or examples"


@pytest.mark.parametrize(
    ("path", "risk", "decision"),
    [(path, "high", "review") for path in DEPENDENCY_PATHS] + [("notes.txt", "low", "merge")],
)
def test_dependency_risk_propagates_to_pr_report(
    path: str, risk: str, decision: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(changes_module, "_git_changed_files", lambda *args, **kwargs: [path])
    facts = RepoFacts(root_name="demo", commands={"test": "python -m pytest"})

    report = build_pr_risk_report(tmp_path, facts, DoctorReport(score=95), CheckResult(ok=True))
    payload = json.loads(render_pr_risk_json(report))

    assert report.risk_level == risk
    assert report.decision == decision
    expected_gates = ["evagix check", "evagix doctor", "python -m pytest"]
    if risk == "high":
        expected_gates.append("human approval")
        assert report.reasons == ["high-risk files changed: " + path.replace("\\", "/")]
    else:
        assert report.reasons == []
    assert report.required_gates == expected_gates
    assert payload["risk_level"] == risk
    assert payload["decision"] == decision
    assert payload["required_gates"] == expected_gates
