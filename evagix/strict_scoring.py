from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from evagix.command_safety import scan_package_script_dangers, scan_task_recipe_dangers
from evagix.context_quality import audit_context_quality
from evagix.ecosystems import ecosystem_payload
from evagix.evidence import Finding, evidence_payload, finding_to_doctor_message
from evagix.model import RepoFacts
from evagix.readme_audit import audit_readme
from evagix.report_models import DoctorFinding
from evagix.scanners.agent_files import discover_agent_files
from evagix.scoring.weights import STRICT_SEVERITY_WEIGHTS

SEVERITY_TO_DOCTOR = {
    "critical": "error",
    "high": "warning",
    "medium": "warning",
    "low": "info",
}

SEVERITY_TO_PENALTY = {severity: penalty for severity, penalty in STRICT_SEVERITY_WEIGHTS.items() if severity != "info"}


def strict_findings(root: Path, facts: RepoFacts) -> list[Finding]:
    readme_report = audit_readme(root, facts, strict=True)
    findings: list[Finding] = list(readme_report.findings)
    for claim in readme_report.claims:
        if claim.verdict in {"supported"}:
            continue
        severity = "high" if claim.verdict == "unsupported" else "medium"
        if claim.claim in {"production-ready", "secure"} and claim.verdict != "supported":
            severity = "high"
        findings.append(
            Finding(
                id=_readme_claim_finding_id(claim.claim, claim.verdict),
                title=f"README claim `{claim.claim}` is {claim.verdict.replace('_', ' ')}",
                category="readme_evidence",
                severity=severity,
                status=claim.verdict,
                source=claim.source or readme_report.readme_path or "README.md",
                source_file=claim.source_file or claim.source or readme_report.readme_path or "README.md",
                source_line=claim.source_line,
                line_range=claim.line_range or ([] if claim.source_line is None else [claim.source_line]),
                evidence=claim.evidence,
                evidence_files=_evidence_files_from_text(claim.evidence),
                missing=claim.missing_evidence,
                missing_evidence=claim.missing_evidence,
                confidence=claim.confidence,
                root_cause=f"readme:{claim.claim}",
                risk=_readme_claim_risk(claim.claim),
                recommendation=claim.suggestion,
            )
        )
    findings.extend(audit_context_quality(root, facts, strict=True))
    findings.extend(scan_package_script_dangers(root))
    findings.extend(scan_task_recipe_dangers(root))
    return _dedupe_findings(findings)


def _readme_claim_finding_id(claim: str, verdict: str) -> str:
    if claim == "readme-command":
        return "readme-evidence.command.unsupported"
    if verdict == "waived":
        return "readme-evidence.claim-waived"
    return f"readme-evidence.{claim.replace('/', '-')}.{verdict}"


def doctor_findings_from_evidence(findings: list[Finding]) -> list[DoctorFinding]:
    doctor_findings: list[DoctorFinding] = []
    charged_roots: set[str] = set()
    for finding in findings:
        root_cause = finding.root_cause or finding.id
        base_penalty = _calibrated_penalty(finding)
        penalty = 0 if finding.summary_only else base_penalty
        if root_cause in charged_roots:
            penalty = min(penalty, 2)
        else:
            charged_roots.add(root_cause)
        doctor_findings.append(
            DoctorFinding(
                severity=(
                    "error"
                    if finding.id in {"readme.scan-truncated", "readme.read-error", "text.invalid-utf8"}
                    else SEVERITY_TO_DOCTOR.get(finding.severity, "warning")
                ),
                code=finding.id,
                message=finding_to_doctor_message(finding),
                penalty=penalty,
            )
        )
    return doctor_findings


def _calibrated_penalty(finding: Finding) -> int:
    """Keep strict mode strict without treating missing Evagix onboarding as unsafe behavior."""
    if finding.id in {"readme.scan-truncated", "readme.read-error", "text.invalid-utf8"}:
        return 25
    if finding.id == "agent-context.missing":
        return 3
    if finding.id.startswith("agent-context.missing-"):
        if finding.id == "agent-context.missing-test":
            return 4
        if finding.id in {"agent-context.missing-install", "agent-context.missing-build"}:
            return 2
        return 1
    return SEVERITY_TO_PENALTY.get(finding.severity, 6)


def build_evidence_ledger(root: Path, facts: RepoFacts) -> dict[str, Any]:
    readme_report = audit_readme(root, facts, strict=True)
    context_findings = audit_context_quality(root, facts, strict=True)
    findings = strict_findings(root, facts)
    commands = []
    for name, command in sorted(facts.commands.items()):
        source = facts.command_sources.get(name)
        commands.append(
            {
                "name": name,
                "command": command,
                "source": source.source if source else "detected",
                "source_file": source.path if source else "",
                "source_line": source.line if source else None,
                "confidence": source.confidence if source else "medium",
            }
        )
    claims = [asdict(item) for item in readme_report.claims]
    agent_context = _agent_context_evidence(root, context_findings)
    return evidence_payload(
        facts.root_name,
        findings,
        claims=claims,
        agent_context=agent_context,
        commands=commands,
        ecosystems=ecosystem_payload(list(getattr(facts, "ecosystems", []) or [])),
    )


def _agent_context_evidence(root: Path, context_findings: list[Finding]) -> list[dict[str, Any]]:
    """Return discovered agent-context files plus file-scoped quality findings.

    The evidence ledger should describe the files discovered by `evagix agents .`,
    not only strict quality findings. This keeps `evidence.agent_context` aligned
    with the public agent-discovery command while preserving conservative status
    and confidence fields for downstream JSON consumers.
    """
    findings_by_source: dict[str, list[dict[str, Any]]] = {}
    for finding in context_findings:
        source = finding.source_file or finding.source
        if not source:
            continue
        findings_by_source.setdefault(source, []).append(
            {
                "id": finding.id,
                "severity": finding.severity,
                "status": finding.status,
                "title": finding.title,
                "source_line": finding.source_line,
                "confidence": finding.confidence,
            }
        )

    rows: list[dict[str, Any]] = []
    for item in discover_agent_files(root):
        row = item.to_dict()
        row.update(
            {
                "source_file": item.path,
                "type": "agent_context_file",
                "generated": False,
                "findings": findings_by_source.get(item.path, []),
            }
        )
        rows.append(row)

    # Preserve repository-level context findings even when no specific file owns them.
    for finding in context_findings:
        source = finding.source_file or finding.source
        if source and any(row.get("path") == source for row in rows):
            continue
        rows.append(
            {
                "path": source or "",
                "tool": "repository context",
                "status": finding.status,
                "confidence": finding.confidence,
                "type": "agent_context_finding",
                "source_file": source or "",
                "findings": [
                    {
                        "id": finding.id,
                        "severity": finding.severity,
                        "status": finding.status,
                        "title": finding.title,
                        "source_line": finding.source_line,
                        "confidence": finding.confidence,
                    }
                ],
            }
        )
    return sorted(rows, key=lambda row: (str(row.get("path", "")), str(row.get("type", ""))))


def _readme_claim_risk(claim: str) -> str:
    risks = {
        "tested": "Developers or AI agents may trust validation that is not actually available.",
        "dockerized": "Developers or AI agents may follow invalid container setup instructions.",
        "ci/cd": "Maintainers may assume checks run automatically when they do not.",
        "fastapi": "AI agents may edit or generate API code around a framework that is not present.",
        "secure": "Security claims without evidence can create false confidence.",
        "production-ready": "Operational readiness claims without evidence can mislead users and reviewers.",
        "agent-instructions": "AI agents may assume high-quality context exists when it is missing or stale.",
    }
    return risks.get(claim, "Repository documentation may be stale, unsupported, or misleading.")


def _dedupe_findings(findings: list[Finding]) -> list[Finding]:
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    result: list[Finding] = []
    for finding in findings:
        key = (finding.id, finding.source, tuple(finding.evidence[:2]))
        if key in seen:
            continue
        seen.add(key)
        result.append(finding)
    return result


def _evidence_files_from_text(items: list[str]) -> list[str]:
    files: list[str] = []
    for item in items:
        if ":" in item and any(
            suffix in item for suffix in [".md", ".toml", ".json", ".yml", ".yaml", ".py", "Dockerfile"]
        ):
            files.append(item.split(":", 1)[0])
        elif any(
            token in item.lower()
            for token in ["pyproject", "package.json", "dockerfile", "workflow", "tests", "readme"]
        ):
            files.append(item)
    return sorted(set(files))
