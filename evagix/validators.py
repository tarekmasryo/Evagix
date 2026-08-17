"""Backward-compatible public facade for validation and readiness APIs."""

from __future__ import annotations

from evagix.validation import (
    AuditFinding,
    CheckResult,
    DoctorFinding,
    DoctorReport,
    apply_config_policy,
    audit_repo,
    check_repo,
    doctor_repo,
    render_audit_markdown,
    render_doctor_json,
    render_doctor_markdown,
    render_github_annotations,
    render_pr_comment,
    render_sarif,
    suggest_actions,
    supported_target_names,
)

__all__ = [
    "AuditFinding",
    "CheckResult",
    "DoctorFinding",
    "DoctorReport",
    "apply_config_policy",
    "audit_repo",
    "check_repo",
    "doctor_repo",
    "render_audit_markdown",
    "render_doctor_json",
    "render_doctor_markdown",
    "render_github_annotations",
    "render_pr_comment",
    "render_sarif",
    "suggest_actions",
    "supported_target_names",
]
