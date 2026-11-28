"""Redacted advisory output for literal CI coverage threshold changes."""

from __future__ import annotations

import json
import unicodedata
from dataclasses import asdict

from evagix.core.text import escape_github_command_value
from evagix.coverage_drift import CoverageDriftFinding, CoverageDriftReport
from evagix.reports.safe_markdown import bounded_markdown, markdown_code
from evagix.security.output import redacted_text_output
from evagix.security.redaction import redact_sensitive_text
from evagix.utils import stable_json

_SCOPE = (
    "Changed existing .github/workflows/*.yml / *.yaml files; comparable literal pytest --cov-fail-under declarations."
)
_BOUNDARY = "Advisory only: effective coverage, execution, required checks and merge readiness are not verified. Changes may be intentional."


def render_coverage_drift_json(report: CoverageDriftReport) -> str:
    return (
        stable_json(
            {
                "schema_version": "1.0",
                "tool": "evagix",
                "kind": "coverage_drift",
                **asdict(report),
                "completeness": "complete" if report.complete else "incomplete",
                "policy_decision": "not_evaluated",
                "scope": {
                    "source": "github_actions_literal_pytest_cov_fail_under",
                    "comparison": "merge_base_to_committed_head",
                    "working_tree": "excluded",
                    "effective_coverage": "not_evaluated",
                    "execution": "not_evaluated",
                },
            }
        )
        + "\n"
    )


def _message(item: CoverageDriftFinding) -> str:
    return f"Literal --cov-fail-under declaration decreased from {item.previous_value}% to {item.value}%."


def _literal(value: str) -> str:
    return json.dumps(redact_sensitive_text(value), ensure_ascii=True)


@redacted_text_output
def render_coverage_drift_text(report: CoverageDriftReport) -> str:
    lines = [
        "CI coverage threshold review (advisory)",
        f"Compared: {report.merge_base} -> {report.head}",
        f"Scope: {_SCOPE}",
        f"Inspection: {'complete' if report.complete else 'incomplete'} within this scope.",
        f"Comparable declarations: {report.compared_thresholds}",
    ]
    for item in report.findings:
        lines.extend(
            (
                f"  {item.code}: {_literal(item.path)}:{item.line}:{item.column} (head): {_message(item)}",
                f"    Job: {_literal(item.job)}; step {item.step_kind}: {_literal(item.step)}; previous declaration: {item.previous_line}:{item.previous_column} (merge_base).",
            )
        )
    if not report.findings:
        lines.append("No findings within the inspected scope.")
    lines.extend(f"  Limit: {_literal(item)}" for item in report.limitations)
    lines.extend(("Review whether the lower declaration is intentional.", _BOUNDARY))
    return "\n".join(lines) + "\n"


def render_coverage_drift_markdown(report: CoverageDriftReport) -> str:
    lines = [
        "## CI coverage threshold review",
        "",
        f"Advisory inspection. {_SCOPE}",
        "",
        f"**Inspection:** {'complete' if report.complete else 'incomplete'} within this scope. **Comparable declarations:** {report.compared_thresholds}.",
        "",
        f"- Base: {markdown_code(report.base)}",
        f"- Head: {markdown_code(report.head)}",
        f"- Merge base: {markdown_code(report.merge_base)}",
        "",
    ]
    for item in report.findings:
        lines.extend(
            (
                f"- {markdown_code(item.code)}: {markdown_code(f'{item.path}:{item.line}:{item.column}')} (head). {_message(item)}",
                f"  - Job: {markdown_code(item.job)}; step {item.step_kind}: {markdown_code(item.step)}. Previous declaration: {markdown_code(f'{item.path}:{item.previous_line}:{item.previous_column}')} (merge_base).",
            )
        )
    if not report.findings:
        lines.append("No findings within the inspected scope.")
    if report.limitations:
        lines.extend(("", "### Inspection limits", ""))
        lines.extend(f"- {markdown_code(item)}" for item in report.limitations)
    lines.extend(("", "Review whether the lower declaration is intentional.", "", _BOUNDARY))
    return bounded_markdown("\n".join(lines) + "\n")


@redacted_text_output
def render_coverage_drift_annotations(report: CoverageDriftReport) -> str:
    lines = []
    for item in report.findings:
        message = escape_github_command_value(f"{_literal(item.path)} (head): {_message(item)} {_BOUNDARY}")
        if not any(unicodedata.category(char) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for char in item.path):
            path = escape_github_command_value(redact_sensitive_text(item.path))
            lines.append(
                f"::notice file={path},line={item.line},col={item.column},title=Coverage declaration::{message}"
            )
        else:
            lines.append(f"::notice title=Coverage declaration::{message}")
    lines.extend(f"::warning::{escape_github_command_value(_literal(item))}" for item in report.limitations)
    if not report.findings:
        lines.append(
            "::notice::No findings within the inspected scope; effective coverage and execution are not verified."
        )
    return "\n".join(lines) + "\n"
