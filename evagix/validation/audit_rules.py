from __future__ import annotations

from pathlib import Path

from evagix.model import RepoFacts
from evagix.report_models import AuditFinding


def audit_repo(root: Path, facts: RepoFacts) -> list[AuditFinding]:
    findings: list[AuditFinding] = []

    def add(severity: str, code: str, message: str) -> None:
        findings.append(AuditFinding(severity=severity, code=code, message=message))

    if facts.active_profiles:
        add("info", "active-profiles", "Active profiles: " + ", ".join(facts.active_profiles))
    for warning in facts.warnings:
        add("warning", "scanner-warning", warning)
    if facts.risk_flags:
        for flag in facts.risk_flags[:12]:
            add("warning", "risk-flag", flag)
    if facts.databases and not facts.has_database_migrations:
        add("warning", "database-without-migrations", "Database detected but no migration system was detected.")
    if facts.is_llm_project and not any(name in facts.commands for name in ["eval", "smoke", "doctor"]):
        add("info", "llm-eval-gap", "AI/Retrieval project has no eval/smoke/doctor command.")
    if facts.is_frontend_project and any("npm install" in cmd for cmd in facts.commands.values()):
        add(
            "info",
            "nondeterministic-node-install",
            "At least one Node install command uses npm install because no npm lockfile was detected.",
        )
    if any((root / name).exists() for name in [".env", ".env.local", ".env.production"]):
        add("warning", "local-env-present", "Local .env-style file detected; verify it is ignored and not committed.")
    if "pip-audit" not in facts.dev_tools and "python" in facts.languages:
        add("info", "python-supply-chain-audit-missing", "Python project has no detected pip-audit dependency/tool.")
    if "bandit" not in facts.dev_tools and facts.is_backend_project:
        add("info", "backend-security-scan-missing", "Backend project has no detected Bandit security scan tool.")
    if "terraform" in facts.infrastructure_tools:
        add("warning", "terraform-runtime", "Terraform files are runtime-impacting; require plan review before apply.")
    if "kubernetes" in facts.container_platforms:
        add(
            "warning",
            "kubernetes-runtime",
            "Kubernetes/Helm/Kustomize files are runtime-impacting; require rollout/rollback notes.",
        )
    return findings
