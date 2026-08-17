from __future__ import annotations

from pathlib import Path

from evagix.evidence import Finding
from evagix.model import RepoFacts
from evagix.scanner import scan_repo
from evagix.strict_scoring import strict_findings

SAFETY_CATEGORIES = {"safety", "agent_context"}


def scan_safety_findings(root: Path, facts: RepoFacts | None = None) -> tuple[Finding, ...]:
    repo_facts = facts or scan_repo(root)
    return tuple(
        finding
        for finding in strict_findings(root, repo_facts)
        if finding.category in SAFETY_CATEGORIES or finding.severity in {"critical", "high"}
    )
