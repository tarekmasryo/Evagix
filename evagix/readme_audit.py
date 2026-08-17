"""Backward-compatible public facade for README evidence auditing."""

from __future__ import annotations

from evagix.readme.audit_engine import (
    audit_readme,
    render_readme_audit_github_annotations,
    render_readme_audit_json,
    render_readme_audit_markdown,
)
from evagix.readme.findings import ReadmeAuditReport, ReadmeClaim
from evagix.readme.source import README_MAX_CHARS, ReadmeSource, ReadmeStatus, read_readme_source

__all__ = [
    "ReadmeAuditReport",
    "ReadmeClaim",
    "ReadmeSource",
    "ReadmeStatus",
    "README_MAX_CHARS",
    "audit_readme",
    "read_readme_source",
    "render_readme_audit_github_annotations",
    "render_readme_audit_json",
    "render_readme_audit_markdown",
]
