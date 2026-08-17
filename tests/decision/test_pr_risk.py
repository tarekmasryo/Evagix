from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from pytest import CaptureFixture

from evagix import changes as changes_module
from evagix.changes import ChangedFileRisk, ChangedReport, build_changed_report
from evagix.cli import main
from evagix.model import RepoFacts
from evagix.pr_risk import build_pr_risk_report, render_pr_risk_json, render_pr_risk_text
from evagix.scanner import scan_repo
from evagix.validators import CheckResult, DoctorFinding, DoctorReport, check_repo, doctor_repo


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(repo: Path) -> None:
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n[project.scripts]\ndemo = "demo.cli:main"\n',
        encoding="utf-8",
    )
    (repo / "demo").mkdir()
    (repo / "demo" / "cli.py").write_text("def main():\n    return 0\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "branch", "-M", "main")


def test_pr_risk_blocks_when_generated_context_is_missing(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: CI\n", encoding="utf-8")

    facts = scan_repo(tmp_path)
    doctor = doctor_repo(tmp_path, facts)
    check = check_repo(tmp_path, facts)
    report = build_pr_risk_report(tmp_path, facts, doctor, check, base="main")

    assert report.risk_level in {"high", "critical"}
    assert report.decision in {"review", "block"}
    assert report.reasons
    assert any(item.path == ".github/workflows/ci.yml" and item.risk == "HIGH" for item in report.changed.files)
    assert "human approval" in report.required_gates
    assert f"Decision: {report.decision}" in render_pr_risk_text(report)
    payload = json.loads(render_pr_risk_json(report))
    assert payload["decision"] == report.decision


def test_pr_risk_cli_outputs_github_annotations(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    _init_repo(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo2"\n', encoding="utf-8")

    assert main(["pr-risk", str(tmp_path), "--base", "main", "--format", "github-annotations"]) in {0, 1}
    output = capsys.readouterr().out
    assert "Evagix PR risk" in output
    assert "pyproject.toml" in output


def test_doctor_json_includes_split_domain_scores(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\ndependencies = ["pytest"]\n', encoding="utf-8")

    assert main(["doctor", str(tmp_path), "--format", "json"]) in {0, 1}
    payload = json.loads(capsys.readouterr().out)
    assert "domains" in payload
    assert set(payload["domains"]) >= {"repository_readiness", "agent_context_governance", "pr_risk_readiness"}


def test_changed_report_reports_missing_git_cleanly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_git(*args: object, **kwargs: object) -> object:
        raise FileNotFoundError("git")

    monkeypatch.setattr(changes_module.subprocess, "run", missing_git)

    with pytest.raises(RuntimeError, match="Git executable was not found"):
        build_changed_report(tmp_path, base="main")


def test_pr_risk_merges_clean_low_risk_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def clean_report(root: Path, base: str = "main", head: str = "HEAD") -> ChangedReport:
        return ChangedReport(base=base, head=head, files=[], required_gates=["evagix check"])

    monkeypatch.setattr("evagix.pr_risk.build_changed_report", clean_report)
    facts = RepoFacts(root_name="demo", commands={"test": "python -m pytest"})
    doctor = DoctorReport(score=95)
    check = CheckResult(ok=True)

    report = build_pr_risk_report(tmp_path, facts, doctor, check)

    assert report.risk_level == "low"
    assert report.decision == "merge"
    assert report.reasons == []
    assert "human approval" not in report.required_gates


def test_pr_risk_reviews_medium_risk_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def medium_report(root: Path, base: str = "main", head: str = "HEAD") -> ChangedReport:
        return ChangedReport(
            base=base,
            head=head,
            files=[ChangedFileRisk(path="evagix.toml", risk="MEDIUM", reason="project governance config")],
            required_gates=["evagix check"],
        )

    monkeypatch.setattr("evagix.pr_risk.build_changed_report", medium_report)
    facts = RepoFacts(root_name="demo", commands={"test": "python -m pytest", "lint": "python -m ruff check ."})
    doctor = DoctorReport(score=95)
    check = CheckResult(ok=True)

    report = build_pr_risk_report(tmp_path, facts, doctor, check)

    assert report.risk_level == "medium"
    assert report.decision == "review"
    assert any("medium-risk files changed" in reason for reason in report.reasons)
    assert "python -m ruff check ." in report.required_gates
    assert "mypy evagix" not in report.required_gates


def test_pr_risk_blocks_stale_and_tampered_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def clean_report(root: Path, base: str = "main", head: str = "HEAD") -> ChangedReport:
        return ChangedReport(base=base, head=head, files=[], required_gates=["evagix check"])

    monkeypatch.setattr("evagix.pr_risk.build_changed_report", clean_report)
    facts = RepoFacts(root_name="demo")
    doctor = DoctorReport(score=95)
    stale = CheckResult(ok=False, stale_targets=["AGENTS.md"])
    tampered = CheckResult(ok=False, tampered_targets=["CLAUDE.md"])

    stale_report = build_pr_risk_report(tmp_path, facts, doctor, stale)
    tampered_report = build_pr_risk_report(tmp_path, facts, doctor, tampered)

    assert stale_report.decision == "block"
    assert stale_report.risk_level == "critical"
    assert any("stale" in reason for reason in stale_report.reasons)
    assert tampered_report.decision == "block"
    assert any("manually modified" in reason for reason in tampered_report.reasons)


def test_pr_risk_blocks_doctor_error_findings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def clean_report(root: Path, base: str = "main", head: str = "HEAD") -> ChangedReport:
        return ChangedReport(base=base, head=head, files=[], required_gates=["evagix check"])

    monkeypatch.setattr("evagix.pr_risk.build_changed_report", clean_report)
    facts = RepoFacts(root_name="demo")
    doctor = DoctorReport(
        score=90, findings=[DoctorFinding(severity="error", code="missing-ci", message="No CI workflow detected")]
    )
    check = CheckResult(ok=True)

    report = build_pr_risk_report(tmp_path, facts, doctor, check)

    assert report.risk_level == "critical"
    assert report.decision == "block"
    assert any("doctor error findings" in reason for reason in report.reasons)


def test_pr_risk_external_python_gates_do_not_reference_evagix_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def python_report(root: Path, base: str = "main", head: str = "HEAD") -> ChangedReport:
        return ChangedReport(
            base=base,
            head=head,
            files=[ChangedFileRisk(path="app/main.py", risk="MEDIUM", reason="source")],
            required_gates=["evagix check", "ruff check .", "mypy .", "pytest"],
        )

    monkeypatch.setattr("evagix.pr_risk.build_changed_report", python_report)
    facts = RepoFacts(root_name="external-app")
    doctor = DoctorReport(score=95)
    check = CheckResult(ok=True)

    report = build_pr_risk_report(tmp_path, facts, doctor, check)

    assert "mypy evagix" not in report.required_gates
    assert "mypy ." in report.required_gates
    assert "ruff check ." in report.required_gates


def test_nested_auth_payment_paths_are_high_risk() -> None:
    from evagix.changes import _classify_changed_path

    for path in [
        "app/auth/security.py",
        "src/security/tokens.py",
        "backend/payments/service.py",
        "api/auth/routes.py",
        "services/billing/invoice.py",
    ]:
        result = _classify_changed_path(path)
        assert result.risk == "HIGH", path
        assert "security" in result.reason or "billing" in result.reason or "auth" in result.reason


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("services/api/migrations/001_init.py", "database migration path"),
        ("packages/core/alembic/versions/001.py", "database migration path"),
        ("services/api/infra/main.tf", "security, auth, billing, permissions, or deployment-sensitive path"),
        ("apps/web/deploy/k8s.yaml", "security, auth, billing, permissions, or deployment-sensitive path"),
        ("services/platform/terraform/main.tf", "security, auth, billing, permissions, or deployment-sensitive path"),
        ("apps/api/kubernetes/deployment.yaml", "security, auth, billing, permissions, or deployment-sensitive path"),
    ],
)
def test_nested_monorepo_sensitive_paths_are_high_risk(path: str, reason: str) -> None:
    from evagix.changes import _classify_changed_path

    result = _classify_changed_path(path)

    assert result.risk == "HIGH"
    assert result.reason == reason
