from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evagix.model import RepoFacts
from evagix.security.output import redacted_text_output
from evagix.utils import stable_json
from evagix.validators import CheckResult, check_repo


@dataclass
class DriftReport:
    repository: str
    status: str
    ok: bool
    missing_targets: list[str] = field(default_factory=list)
    stale_targets: list[str] = field(default_factory=list)
    tampered_targets: list[str] = field(default_factory=list)
    unmanaged_targets: list[str] = field(default_factory=list)
    invalid_encoding_targets: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    recommended_fix: str = "Run `evagix sync .` to regenerate and validate generated agent instruction files."

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "tool": "evagix",
            "report_type": "drift",
            "repository": self.repository,
            "status": self.status,
            "ok": self.ok,
            "missing_targets": self.missing_targets,
            "stale_targets": self.stale_targets,
            "tampered_targets": self.tampered_targets,
            "unmanaged_targets": self.unmanaged_targets,
            "invalid_encoding_targets": self.invalid_encoding_targets,
            "warnings": self.warnings,
            "errors": self.errors,
            "recommended_fix": self.recommended_fix,
        }


def build_drift_report(root: Path, facts: RepoFacts, target_keys: list[str] | None = None) -> DriftReport:
    result = check_repo(root, facts, target_keys=target_keys)
    return drift_report_from_check(facts, result)


def drift_report_from_check(facts: RepoFacts, result: CheckResult) -> DriftReport:
    drift_items = (
        result.missing_targets
        + result.stale_targets
        + result.tampered_targets
        + result.unmanaged_targets
        + result.invalid_encoding_targets
    )
    status = "in-sync" if result.ok and not drift_items else "drift-detected"
    recommended_fix = "No drift detected. Keep `evagix check .` in CI."
    if drift_items:
        recommended_fix = "Run `evagix sync .` to regenerate and validate generated agent instruction files."
    return DriftReport(
        repository=facts.root_name,
        status=status,
        ok=result.ok and not drift_items,
        missing_targets=list(result.missing_targets),
        stale_targets=list(result.stale_targets),
        tampered_targets=list(result.tampered_targets),
        unmanaged_targets=list(result.unmanaged_targets),
        invalid_encoding_targets=list(result.invalid_encoding_targets),
        warnings=list(result.warnings),
        errors=list(result.errors),
        recommended_fix=recommended_fix,
    )


def render_drift_json(report: DriftReport) -> str:
    return stable_json(report.to_dict()) + "\n"


@redacted_text_output
def render_drift_markdown(report: DriftReport) -> str:
    lines = [
        "# Evagix Drift Report",
        "",
        f"- Repository: `{report.repository}`",
        f"- Status: `{report.status}`",
        f"- OK: `{str(report.ok).lower()}`",
        "",
    ]
    if not (
        report.missing_targets
        or report.stale_targets
        or report.tampered_targets
        or report.unmanaged_targets
        or report.invalid_encoding_targets
    ):
        lines.extend(["No generated Evagix drift detected.", ""])
    else:
        if report.missing_targets:
            lines.append("## Missing targets")
            lines.extend(f"- `{item}`" for item in report.missing_targets)
            lines.append("")
        if report.stale_targets:
            lines.append("## Stale targets")
            lines.extend(f"- `{item}`" for item in report.stale_targets)
            lines.append("")
        if report.tampered_targets:
            lines.append("## Tampered targets")
            lines.extend(f"- `{item}`" for item in report.tampered_targets)
            lines.append("")
        if report.unmanaged_targets:
            lines.append("## Unmanaged configured targets")
            lines.extend(f"- `{item}`" for item in report.unmanaged_targets)
            lines.append("")
        if report.invalid_encoding_targets:
            lines.append("## Invalid UTF-8 targets")
            lines.extend(f"- `{item}`" for item in report.invalid_encoding_targets)
            lines.append("")
    if report.errors:
        lines.append("## Errors")
        lines.extend(f"- {item}" for item in report.errors)
        lines.append("")
    if report.warnings:
        lines.append("## Warnings")
        lines.extend(f"- {item}" for item in report.warnings)
        lines.append("")
    lines.extend(["## Recommended fix", "", report.recommended_fix, ""])
    return "\n".join(lines)
