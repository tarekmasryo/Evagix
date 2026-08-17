from __future__ import annotations

import json
from pathlib import Path

import pytest

from evagix.cli import main
from evagix.model import RepoFacts
from evagix.validation.audit_actions import _uses_plain_npm_install
from evagix.validation.audit_rules import audit_repo


def test_validation_audit_rules_cover_profile_runtime_and_security_gaps(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SECRET=value\n", encoding="utf-8")
    facts = RepoFacts(
        root_name="demo",
        languages=["python"],
        frameworks=["fastapi"],
        infrastructure_tools=["terraform"],
        container_platforms=["kubernetes"],
        databases=["postgres"],
        llm_tools=["langchain"],
        risk_flags=["secret-like file"],
        warnings=["scanner warning"],
        active_profiles=["backend-api"],
    )
    codes = {item.code for item in audit_repo(tmp_path, facts)}
    assert {
        "active-profiles",
        "scanner-warning",
        "risk-flag",
        "database-without-migrations",
        "llm-eval-gap",
        "local-env-present",
        "python-supply-chain-audit-missing",
        "backend-security-scan-missing",
        "terraform-runtime",
        "kubernetes-runtime",
    }.issubset(codes)
    assert _uses_plain_npm_install("npm install && npm run build")
    assert not _uses_plain_npm_install("pnpm install")


def test_audit_overall_status_and_exit_follow_readiness(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")

    exit_code = main(["audit", str(tmp_path), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["governance_ok"] is True
    assert payload["readiness_ok"] is False
    assert payload["overall_ok"] is False
    assert payload["ok"] is False
    assert exit_code == 1
