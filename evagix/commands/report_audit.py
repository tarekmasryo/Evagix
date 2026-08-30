from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from evagix import __version__
from evagix.commands.common import _facts, _normalize_root, _resolve_cli_output_path, _targets
from evagix.model import RepoFacts
from evagix.security.output import redacted_text_output
from evagix.terminal import PLAIN_STYLE, TerminalStyle
from evagix.utils import stable_json, write_text
from evagix.validators import DoctorReport, apply_config_policy, audit_repo, doctor_repo


def _cmd_audit(
    root: Path,
    as_json: bool,
    output: str | None,
    force: bool,
    profiles: list[str] | None = None,
    style: TerminalStyle = PLAIN_STYLE,
) -> int:
    root = _normalize_root(root)
    facts, config = _facts(root, profiles)
    report = apply_config_policy(
        doctor_repo(
            root,
            facts,
            target_keys=_targets(config, None),
            custom_targets=config.custom_targets,
            fail_on_stale=config.fail_on_stale,
            strict=True,
            require_onboarding_pack=config.require_onboarding_pack,
        ),
        config,
    )
    findings = audit_repo(root, facts)
    payload = audit_payload(root, facts, findings, report)
    if as_json:
        print(stable_json(payload))
    else:
        _print_audit_text(report, findings, overall_ok=bool(payload["overall_ok"]), style=style)
    if output:
        output_path = _resolve_cli_output_path(root, output)
        if output_path.exists() and not force:
            print(f"{output} already exists. Re-run with --force to overwrite.", file=sys.stderr)
            return 1
        write_text(output_path, render_audit_markdown(root, facts, findings, report))
        print(f"Created {output}")
    return 0 if bool(payload["overall_ok"]) else 1


def _print_audit_text(
    report: DoctorReport,
    findings: Sequence[object],
    *,
    overall_ok: bool,
    style: TerminalStyle = PLAIN_STYLE,
) -> None:
    print(style.heading("Evagix Audit"))
    print(
        style.muted(
            "Scope: governance summary plus lightweight profile hints; use doctor/readme-audit/eval-context for full detail."
        )
    )
    print("")
    print(f"Status: {style.status('PASS' if overall_ok else 'FAIL')}")
    print(f"Static evidence: {report.score}/100 ({'pass' if report.ok else 'needs attention'})")
    print("")
    print(style.heading("Findings:"))
    if not findings:
        print(f"  [{style.status('PASS', width=5)}] No audit findings.")
    for item in findings:
        severity = str(getattr(item, "severity", "info"))
        code = getattr(item, "code", "finding")
        message = getattr(item, "message", str(item))
        print(f"  [{style.severity(severity, width=5)}] {code}")
        print(f"          {message}")


def audit_payload(
    root: Path, facts: RepoFacts, findings: Sequence[object], report: DoctorReport | None = None
) -> dict[str, object]:
    severity_counts: dict[str, int] = {}
    serialized_findings = []
    for item in findings:
        severity = getattr(item, "severity", "info")
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        if hasattr(item, "__dict__"):
            serialized_findings.append(dict(item.__dict__))
        else:
            serialized_findings.append({"message": str(item), "severity": severity})
    governance_ok = not any(severity in {"error", "high", "critical"} for severity in severity_counts)
    readiness_ok = report.ok if report is not None else True
    overall_ok = governance_ok and readiness_ok
    return {
        "schema_version": "1.0",
        "tool": "evagix",
        "version": __version__,
        "repository": {"name": facts.root_name, "path": str(root)},
        "ok": overall_ok,
        "governance_ok": governance_ok,
        "readiness_ok": readiness_ok,
        "overall_ok": overall_ok,
        "summary": {
            "finding_count": len(serialized_findings),
            "severity_counts": severity_counts,
            "active_profiles": facts.active_profiles,
            "scope": "governance-summary",
        },
        "readiness": audit_readiness_summary(report),
        "recommended_next_commands": [
            "evagix doctor . --strict --fail-under 80",
            "evagix readme-audit . --strict --fail-on unsupported",
            "evagix eval-context . --strict --fail-on high",
        ],
        "findings": serialized_findings,
        "profiles": facts.active_profiles,
    }


def _audit_payload(
    root: Path, facts: RepoFacts, findings: Sequence[object], report: DoctorReport | None = None
) -> dict[str, object]:
    return audit_payload(root, facts, findings, report)


def audit_readiness_summary(report: DoctorReport | None) -> dict[str, object]:
    if report is None:
        return {}
    return {
        "score_type": "static_evidence",
        "ok": report.ok,
        "score": report.score,
        "finding_count": len(report.findings),
        "severity_counts": doctor_severity_counts(report),
        "tier": report.maturity_level,
    }


def _audit_readiness_summary(report: DoctorReport | None) -> dict[str, object]:
    return audit_readiness_summary(report)


def doctor_severity_counts(report: DoctorReport) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in report.findings:
        counts[item.severity] = counts.get(item.severity, 0) + 1
    return counts


def _doctor_severity_counts(report: DoctorReport) -> dict[str, int]:
    return doctor_severity_counts(report)


@redacted_text_output
def render_audit_markdown(root: Path, facts: RepoFacts, findings: Sequence[object], report: DoctorReport) -> str:
    lines = [
        "# Evagix Audit",
        "",
        f"- Repository: `{facts.root_name}`",
        f"- Static evidence score: `{report.score}/100`",
        f"- Status: `{'pass' if report.ok else 'needs attention'}`",
        f"- Profiles: {', '.join(facts.active_profiles) if facts.active_profiles else 'none'}",
        "",
        "## Scope",
        "",
        "This audit is a governance summary. Use `doctor`, `readme-audit`, and `eval-context` for detailed readiness gates.",
        "",
        "## Findings",
        "",
    ]
    if findings:
        for item in findings:
            severity = getattr(item, "severity", "info")
            code = getattr(item, "code", "finding")
            message = getattr(item, "message", str(item))
            lines.append(f"- **{severity}** `{code}`: {message}")
    else:
        lines.append("- No audit findings.")
    lines.extend(
        [
            "",
            "## Recommended Next Commands",
            "",
            "```bash",
            "evagix doctor . --strict --fail-under 80",
            "evagix readme-audit . --strict --fail-on unsupported",
            "evagix eval-context . --strict --fail-on high",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _render_audit_markdown(root: Path, facts: RepoFacts, findings: Sequence[object], report: DoctorReport) -> str:
    return render_audit_markdown(root, facts, findings, report)
