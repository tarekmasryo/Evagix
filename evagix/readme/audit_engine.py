from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path

from evagix.evidence import Finding
from evagix.model import RepoFacts
from evagix.readme.claim_rules import claim_rules
from evagix.readme.command_extractor import _command_claims_from_readme, _suggest_replacement
from evagix.readme.findings import ReadmeAuditReport, ReadmeClaim
from evagix.readme.source import ReadmeSource, ReadmeStatus, read_readme_source
from evagix.readme.text_utils import (
    _claim_confidence,
    _claim_occurrences,
    _score,
    _strip_ignored_blocks,
)
from evagix.security.output import redacted_text_output
from evagix.text_diagnostics import invalid_utf8_finding
from evagix.utils import stable_json


def audit_readme(root: Path, facts: RepoFacts, *, strict: bool = False) -> ReadmeAuditReport:
    source = read_readme_source(root)
    source_findings = _readme_source_findings(root, source)
    if not source.text:
        return ReadmeAuditReport(
            score=0,
            claims=[],
            readme_path=source.path,
            status=source.status,
            chars_read=source.chars_read,
            max_chars=source.max_chars,
            findings=source_findings,
        )

    auditable_text = _strip_ignored_blocks(source.text)
    lower = auditable_text.lower()
    waived_claims = {item.lower() for item in facts.readme_ignore_claims}
    claims: list[ReadmeClaim] = []
    for claim, pattern, checker, suggestion in claim_rules():
        matches = _claim_occurrences(pattern, lower, root_name=facts.root_name)
        if not matches:
            continue
        evidence, missing = checker(root, facts)
        phrase, source_line = matches[0]
        source_text = _source_line_text(auditable_text, source_line)
        manual_review_reason = _manual_review_reason(claim, phrase, source_text)
        manual_review_suggestion = _manual_review_suggestion(claim) if manual_review_reason else ""
        if claim.lower() in waived_claims:
            verdict = "waived"
            waiver_reason = "Claim explicitly waived by readme_audit policy; local evidence remains incomplete."
            if waiver_reason not in missing:
                missing = [*missing, waiver_reason]
        else:
            verdict, missing = _claim_verdict(
                claim,
                evidence,
                missing,
                strict=strict,
                manual_review_reason=manual_review_reason,
            )
        claims.append(
            ReadmeClaim(
                claim=claim,
                phrase=phrase,
                verdict=verdict,
                evidence=evidence,
                missing_evidence=missing,
                suggestion=manual_review_suggestion or suggestion,
                suggested_replacement=("" if manual_review_reason else _suggest_replacement(claim, phrase, facts)),
                source=source.path,
                source_file=source.path,
                source_line=source_line,
                line_range=[source_line] if source_line else [],
                confidence=_claim_confidence(verdict, claim),
            )
        )

    claims.extend(_command_claims_from_readme(root, source.text, facts, readme_path=source.path))
    score = _score(claims, strict=strict) if source.complete else 0
    return ReadmeAuditReport(
        score=score,
        claims=claims,
        readme_path=source.path,
        status=source.status,
        chars_read=source.chars_read,
        max_chars=source.max_chars,
        findings=source_findings,
    )


def _readme_source_findings(root: Path, source: ReadmeSource) -> list[Finding]:
    if source.status == ReadmeStatus.EMPTY:
        return [
            Finding(
                id="readme.empty",
                title="README is empty",
                category="readme_evidence",
                severity="medium",
                status="empty",
                source=source.path,
                source_file=source.path,
                evidence=["README exists but contains no text"],
                risk="Documentation and claim evidence cannot be evaluated from an empty README.",
                recommendation="Document installation, usage, validation, and current limitations, then rerun Evagix.",
                confidence="high",
                root_cause=f"empty-readme:{source.path}",
            )
        ]
    if source.status == ReadmeStatus.TRUNCATED:
        return [
            Finding(
                id="readme.scan-truncated",
                title="README analysis was truncated",
                category="readme_evidence",
                severity="high",
                status="incomplete",
                source=source.path,
                source_file=source.path,
                evidence=[f"README exceeded the {source.max_chars}-character analysis limit"],
                risk="Claims beyond the inspected prefix could be missed, producing a false clean result.",
                recommendation="Reduce or split the README, or raise the reviewed limit before relying on the audit.",
                confidence="high",
                root_cause=f"readme-truncated:{source.path}",
                metadata={"chars_read": source.chars_read, "max_chars": source.max_chars},
            )
        ]
    if source.status == ReadmeStatus.INVALID_UTF8:
        return [invalid_utf8_finding(root, root / source.path, scanner="README audit", category="readme_evidence")]
    if source.status == ReadmeStatus.READ_ERROR:
        return [
            Finding(
                id="readme.read-error",
                title="README could not be read safely",
                category="readme_evidence",
                severity="high",
                status="incomplete",
                source=source.path,
                source_file=source.path,
                evidence=["README audit could not read the selected README"],
                risk="The README was not inspected, so repository claims may be missed.",
                recommendation="Restore read access, confirm the path is a regular UTF-8 file, and rerun Evagix.",
                confidence="high",
                root_cause=f"readme-read-error:{source.path}",
            )
        ]
    return []


def _claim_verdict(
    claim: str,
    evidence: list[str],
    missing: list[str],
    *,
    strict: bool,
    manual_review_reason: str,
) -> tuple[str, list[str]]:
    if manual_review_reason:
        if manual_review_reason not in missing:
            missing = [*missing, manual_review_reason]
        return "manual_review_required", missing

    if not evidence and _has_incomplete_evidence_search(missing):
        reason = "Required evidence discovery was incomplete, so absence cannot be established automatically."
        if reason not in missing:
            missing = [*missing, reason]
        return "manual_review_required", missing

    if claim in {"secure", "production-ready"}:
        if not evidence:
            return "unsupported", missing
        reason = (
            "Static repository markers cannot verify this high-trust claim; "
            "operational or external evidence requires manual review."
        )
        if reason not in missing:
            missing = [*missing, reason]
        return ("manual_review_required" if strict else "weak_evidence"), missing

    if strict and claim in {"monitoring", "deployable"}:
        if evidence:
            reason = "Static evidence shows capability structure but does not prove operational behavior."
            if reason not in missing:
                missing = [*missing, reason]
            return "weak_evidence", missing
        return "unsupported", missing

    if evidence and not missing:
        return "supported", missing
    if evidence and missing:
        return "partially_supported", missing
    return "unsupported", missing


def _has_incomplete_evidence_search(missing: list[str]) -> bool:
    return any("was truncated because" in item and "results may be incomplete" in item for item in missing)


def _source_line_text(text: str, source_line: int | None) -> str:
    if source_line is None:
        return ""
    lines = text.splitlines()
    return lines[source_line - 1] if 0 < source_line <= len(lines) else ""


def _manual_review_suggestion(claim: str) -> str:
    if claim == "package-installable":
        return "Verify the public package page and installation command during release before treating this claim as proven."
    if claim == "tested":
        return "Link to successful CI run evidence for the stated versions or platforms, or narrow the wording."
    return "Verify this claim manually before release."


def _manual_review_reason(claim: str, phrase: str, source_text: str) -> str:
    normalized = " ".join(f"{phrase} {source_text}".lower().split())
    if claim == "package-installable" and any(
        marker in normalized
        for marker in ("published package", "published on pypi", "available on pypi", "pypi package")
    ):
        return "External package publication cannot be proven from local repository evidence."
    if claim == "tested" and (
        "tested on" in normalized
        or any(platform in normalized for platform in ("windows", "macos", "linux"))
        or bool(re.search(r"python\s+3\.\d+", normalized))
    ):
        return "Runtime and platform test claims require CI run evidence or manual verification."
    return ""


@redacted_text_output
def render_readme_audit_markdown(root: Path, facts: RepoFacts, *, strict: bool = False) -> str:
    report = audit_readme(root, facts, strict=strict)
    lines = [
        "# README Claim Audit",
        "",
        f"- Repository: `{facts.root_name}`",
        f"- Static evidence score: `{report.score}/100`",
        f"- Read status: `{report.status.value}`",
        f"- Complete scan: `{'yes' if report.complete else 'no'}`",
        f"- Characters read: `{report.chars_read}` (limit: `{report.max_chars}`)",
    ]
    if report.readme_path:
        lines.append(f"- README: `{report.readme_path}`")
    lines.append("")

    if report.findings:
        lines.extend(["## Read diagnostics", ""])
        for finding in report.findings:
            lines.append(f"- **{finding.severity}** `{finding.id}`: {finding.title}")
            if finding.evidence:
                lines.append("  - Evidence: " + "; ".join(finding.evidence))
            if finding.risk:
                lines.append(f"  - Risk: {finding.risk}")
            if finding.recommendation:
                lines.append(f"  - Fix: {finding.recommendation}")
        lines.append("")

    if not report.claims:
        if report.status == ReadmeStatus.MISSING:
            lines.append("No README was found.")
        elif report.status == ReadmeStatus.EMPTY:
            lines.append("The README is empty; no claims could be audited.")
        elif not report.complete:
            lines.append("README claims could not be audited completely.")
        else:
            lines.append("No auditable README claims were detected.")
        return "\n".join(lines).rstrip() + "\n"

    for title, items in [
        ("Unsupported claims", report.unsupported),
        ("Partially supported claims", report.partial),
        ("Waived claims", report.waived),
        ("Supported claims", report.supported),
    ]:
        lines.extend([f"## {title}", ""])
        if not items:
            lines.append("- None.")
        for item in items:
            lines.append(f"- `{item.claim}` from phrase `{item.phrase}`: **{item.verdict}**")
            source = item.source_file or item.source
            if source:
                location = f"{source}:{item.source_line}" if item.source_line else source
                lines.append(f"  - Source: `{location}`")
            if item.confidence:
                lines.append(f"  - Confidence: `{item.confidence}`")
            if item.evidence:
                lines.append("  - Evidence: " + "; ".join(item.evidence))
            if item.missing_evidence:
                lines.append("  - Missing: " + "; ".join(item.missing_evidence))
            if item.verdict != "supported":
                lines.append(f"  - Suggested safer wording: {item.suggestion}")
                if item.suggested_replacement:
                    lines.append(f"  - Suggested README fix: `{item.suggested_replacement}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_readme_audit_json(root: Path, facts: RepoFacts, *, strict: bool = False) -> str:
    report = audit_readme(root, facts, strict=strict)
    weak_evidence = [item for item in report.claims if item.verdict == "weak_evidence"]
    partially_supported = [item for item in report.claims if item.verdict in {"partial", "partially_supported"}]
    manual_review = [item for item in report.claims if item.verdict == "manual_review_required"]
    waived = [item for item in report.claims if item.verdict == "waived"]
    return (
        stable_json(
            {
                "schema_version": "1.0",
                "tool": "evagix",
                "repository": facts.root_name,
                "readme_path": report.readme_path,
                "status": report.status.value,
                "complete": report.complete,
                "chars_read": report.chars_read,
                "max_chars": report.max_chars,
                "score": report.score,
                "summary": {
                    "supported_claims": len(report.supported),
                    "unsupported_claims": len(report.unsupported),
                    "weak_evidence_claims": len(weak_evidence),
                    "partial_claims": len(partially_supported),
                    "manual_review_claims": len(manual_review),
                    "waived_claims": len(waived),
                    "findings": len(report.findings),
                    "incomplete_findings": sum(item.status == "incomplete" for item in report.findings),
                },
                "supported_claims": [asdict(item) for item in report.supported],
                "unsupported_claims": [asdict(item) for item in report.unsupported],
                "weak_evidence_claims": [asdict(item) for item in weak_evidence],
                "partial_claims": [asdict(item) for item in partially_supported],
                "manual_review_claims": [asdict(item) for item in manual_review],
                "waived_claims": [asdict(item) for item in waived],
                "claims": [asdict(item) for item in report.claims],
                "findings": [item.to_dict() for item in report.findings],
            }
        )
        + "\n"
    )


@redacted_text_output
def render_readme_audit_github_annotations(root: Path, facts: RepoFacts, *, strict: bool = False) -> str:
    report = audit_readme(root, facts, strict=strict)
    lines: list[str] = []
    readme_path = report.readme_path or "README.md"
    for finding in report.findings:
        level = "error" if strict and finding.severity in {"critical", "high"} else "warning"
        message = f"{finding.id}: {finding.title}"
        lines.append(f"::{level} file={readme_path},title=Evagix README audit::{_escape_annotation(message)}")
    for item in report.claims:
        if item.verdict == "supported":
            continue
        level = "error" if item.verdict == "unsupported" else "warning"
        message = f"{item.verdict} README claim `{item.phrase}` ({item.claim})"
        if item.suggested_replacement:
            message += f"; suggested replacement: {item.suggested_replacement}"
        line_part = f",line={item.source_line}" if item.source_line else ""
        lines.append(
            f"::{level} file={readme_path}{line_part},title=Evagix README audit::{_escape_annotation(message)}"
        )
    if not lines:
        if report.status == ReadmeStatus.MISSING:
            lines.append("::notice title=Evagix README audit::No README was found.")
        elif report.status == ReadmeStatus.EMPTY:
            lines.append("::warning file=README.md,title=Evagix README audit::README is empty.")
        elif report.claims:
            lines.append(
                "::notice title=Evagix README audit::All detected README claims are supported by repository evidence."
            )
        else:
            lines.append("::notice title=Evagix README audit::No auditable README claims detected.")
    return "\n".join(lines) + "\n"


def _escape_annotation(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
