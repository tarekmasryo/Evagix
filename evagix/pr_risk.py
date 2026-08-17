from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from evagix.changes import ChangedReport, build_changed_report
from evagix.core.collections import unique_preserving_order
from evagix.core.text import escape_github_command_value
from evagix.model import RepoFacts
from evagix.security.output import redacted_text_output
from evagix.security.redaction import redact_sensitive_text
from evagix.utils import stable_json
from evagix.validators import CheckResult, DoctorReport


@dataclass(frozen=True)
class PRRiskReport:
    """Repository PR risk decision built from changed files, context sync, and readiness."""

    base: str
    head: str
    risk_level: str
    decision: str
    reasons: list[str]
    required_gates: list[str]
    changed: ChangedReport
    readiness_score: int
    context_ok: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "base", redact_sensitive_text(self.base))
        object.__setattr__(self, "head", redact_sensitive_text(self.head))
        object.__setattr__(self, "reasons", [redact_sensitive_text(item) for item in self.reasons])
        object.__setattr__(self, "required_gates", [redact_sensitive_text(item) for item in self.required_gates])

    @property
    def should_block(self) -> bool:
        return self.decision == "block"


def build_pr_risk_report(
    root: Path,
    facts: RepoFacts,
    doctor: DoctorReport,
    check: CheckResult,
    *,
    base: str = "main",
    head: str = "HEAD",
) -> PRRiskReport:
    """Build a PR-level risk decision without executing project validation commands."""

    changed = build_changed_report(root, base=base, head=head)
    reasons = _risk_reasons(changed, doctor, check)
    risk_level = _risk_level(changed, doctor, check, reasons)
    decision = _decision_for(risk_level, check, doctor)
    gates = _required_gates(facts, changed, risk_level, check, doctor)
    return PRRiskReport(
        base=base,
        head=head,
        risk_level=risk_level,
        decision=decision,
        reasons=reasons,
        required_gates=gates,
        changed=changed,
        readiness_score=doctor.score,
        context_ok=check.ok,
    )


@redacted_text_output
def render_pr_risk_text(report: PRRiskReport) -> str:
    lines = [
        f"Evagix PR Risk against `{report.base}` -> `{report.head}`",
        "",
        f"Risk level: {report.risk_level}",
        f"Decision: {report.decision}",
        f"Readiness score: {report.readiness_score}/100",
        f"Generated context: {'ok' if report.context_ok else 'needs attention'}",
        "",
        "Changed files:",
    ]
    if not report.changed.files:
        lines.append("  - none detected")
    for item in report.changed.files:
        lines.append(f"  - {item.risk:<6} {item.path:<45} — {item.reason}")
    lines.extend(["", "Reasons:"])
    if report.reasons:
        for reason in report.reasons:
            lines.append(f"  - {reason}")
    else:
        lines.append("  - no material PR risk signals detected")
    lines.extend(["", "Required gates:"])
    for gate in report.required_gates:
        lines.append(f"  - {gate}")
    return "\n".join(lines).rstrip() + "\n"


def render_pr_risk_json(report: PRRiskReport) -> str:
    payload = {
        "schema_version": "1.0",
        "tool": "evagix",
        "base": report.base,
        "head": report.head,
        "risk_level": report.risk_level,
        "decision": report.decision,
        "reasons": report.reasons,
        "required_gates": report.required_gates,
        "readiness_score": report.readiness_score,
        "context_ok": report.context_ok,
        "changed": {
            "files": [asdict(item) for item in report.changed.files],
            "required_gates": report.changed.required_gates,
            "has_high_risk": report.changed.has_high_risk,
        },
    }
    return stable_json(payload) + "\n"


@redacted_text_output
def render_pr_risk_github_annotations(report: PRRiskReport) -> str:
    lines: list[str] = []
    decision_level = "error" if report.decision == "block" else "warning" if report.decision == "review" else "notice"
    summary = escape_github_command_value(f"{report.risk_level} risk PR; decision={report.decision}")
    lines.append(f"::{decision_level} title=Evagix PR risk::{summary}")
    for item in report.changed.files:
        level = "error" if item.risk == "HIGH" else "warning" if item.risk == "MEDIUM" else "notice"
        message = escape_github_command_value(f"{item.risk} risk changed file: {item.reason}")
        path = escape_github_command_value(item.path)
        lines.append(f"::{level} file={path},line=1,title=Evagix PR risk::{message}")
    for reason in report.reasons[:8]:
        lines.append(f"::notice title=Evagix PR risk reason::{escape_github_command_value(reason)}")
    return "\n".join(lines) + "\n"


def _risk_reasons(changed: ChangedReport, doctor: DoctorReport, check: CheckResult) -> list[str]:
    reasons: list[str] = []
    if not check.ok:
        if check.missing_targets:
            reasons.append("generated context exports are missing")
        if check.stale_targets:
            reasons.append("generated context exports are stale")
        if check.tampered_targets:
            reasons.append("generated context exports were manually modified")
        if check.unmanaged_targets:
            reasons.append("configured context targets are not Evagix-managed")
        if check.invalid_encoding_targets:
            reasons.append("generated context exports contain invalid UTF-8")
    high_files = [item.path for item in changed.files if item.risk == "HIGH"]
    medium_files = [item.path for item in changed.files if item.risk == "MEDIUM"]
    if high_files:
        reasons.append("high-risk files changed: " + ", ".join(high_files[:8]))
    if medium_files:
        reasons.append("medium-risk files changed: " + ", ".join(medium_files[:8]))
    if _risky_source_changed_without_tests(changed):
        reasons.append("source/config changed without nearby test changes in this diff")
    if doctor.score < 80:
        reasons.append(f"readiness score below default threshold: {doctor.score}/100")
    error_codes = [item.code for item in doctor.findings if item.severity == "error"]
    if error_codes:
        reasons.append("doctor error findings present: " + ", ".join(error_codes[:8]))
    return reasons


def _risk_level(changed: ChangedReport, doctor: DoctorReport, check: CheckResult, reasons: list[str]) -> str:
    if not check.ok or any(item.severity == "error" for item in doctor.findings):
        return "critical"
    if changed.has_high_risk or doctor.score < 80 or _risky_source_changed_without_tests(changed):
        return "high"
    if any(item.risk == "MEDIUM" for item in changed.files) or reasons:
        return "medium"
    return "low"


def _decision_for(risk_level: str, check: CheckResult, doctor: DoctorReport) -> str:
    if risk_level == "critical" or not check.ok or any(item.severity == "error" for item in doctor.findings):
        return "block"
    if risk_level in {"high", "medium"}:
        return "review"
    return "merge"


def _required_gates(
    facts: RepoFacts, changed: ChangedReport, risk_level: str, check: CheckResult, doctor: DoctorReport
) -> list[str]:
    gates = ["evagix check", "evagix doctor"]
    gates.extend(_project_validation_gates(facts, changed))
    if not check.ok or risk_level in {"critical", "high"} or any(item.severity == "error" for item in doctor.findings):
        gates.append("human approval")
    return unique_preserving_order(gates)


def _project_validation_gates(facts: RepoFacts, changed: ChangedReport) -> list[str]:
    paths = [item.path.lower() for item in changed.files]
    has_python_change = any(path.endswith(".py") for path in paths)
    has_test_change = any(path.startswith("tests/") or "/tests/" in path for path in paths)
    gates: list[str] = []
    if has_python_change or has_test_change:
        gates.append(facts.commands.get("test", "pytest"))
        gates.append(facts.commands.get("lint", "ruff check ."))
        gates.append(facts.commands.get("typecheck", "mypy ."))
    else:
        for name in ("test", "lint", "typecheck"):
            if name in facts.commands:
                gates.append(facts.commands[name])
    return gates


def _risky_source_changed_without_tests(changed: ChangedReport) -> bool:
    paths = [item.path.lower() for item in changed.files]
    if not paths:
        return False
    has_test_change = any(path.startswith("tests/") or "/tests/" in path or path.startswith("test_") for path in paths)
    has_risky_source = any(
        (path.endswith((".py", ".js", ".ts", ".tsx")) and not path.startswith(("tests/", "examples/", "docs/")))
        or path in {"pyproject.toml", "package.json"}
        or _is_sensitive_or_workflow_path(path)
        for path in paths
    )
    return has_risky_source and not has_test_change


def _is_sensitive_or_workflow_path(path: str) -> bool:
    if path.startswith(".github/workflows/"):
        return True
    segments = {part for part in path.split("/") if part}
    return bool(
        segments
        & {
            "auth",
            "security",
            "permissions",
            "permission",
            "jwt",
            "token",
            "tokens",
            "billing",
            "payment",
            "payments",
            "secret",
            "secrets",
        }
    )
