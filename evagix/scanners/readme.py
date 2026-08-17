from __future__ import annotations

from pathlib import Path

from evagix.model import RepoFacts
from evagix.readme_audit import ReadmeAuditReport, audit_readme
from evagix.scanner import scan_repo


def scan_readme_claims(root: Path, facts: RepoFacts | None = None, *, strict: bool = False) -> ReadmeAuditReport:
    return audit_readme(root, facts or scan_repo(root), strict=strict)
