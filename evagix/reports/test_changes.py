"""Redacted advisory presentation of committed test changes."""

from __future__ import annotations

import json
import unicodedata
from dataclasses import asdict

from evagix.core.text import escape_github_command_value
from evagix.reports.safe_markdown import bounded_markdown, markdown_code
from evagix.security.output import redacted_text_output
from evagix.security.redaction import redact_sensitive_text
from evagix.test_changes import TestChangeFinding, TestChangesReport
from evagix.utils import stable_json

_SCOPE = "Committed Python test_*.py / *_test.py paths; existing named tests and literal pytest.mark.skip declarations."
_BOUNDARY = "Advisory only: collection, execution, test quality and merge readiness are not verified. Changes may be intentional."
_RENAMES = "Git rename candidates use 50% similarity; unmatched removals may also be moves."


def render_test_changes_json(report: TestChangesReport) -> str:
    return (
        stable_json(
            {
                "schema_version": "1.0",
                "tool": "evagix",
                "kind": "test_changes",
                **asdict(report),
                "completeness": "complete" if report.complete else "incomplete",
                "policy_decision": "not_evaluated",
                "scope": {
                    "filenames": ["test_*.py", "*_test.py"],
                    "skip_syntax": "literal_pytest_mark_skip",
                    "working_tree": "excluded",
                    "collection": "not_evaluated",
                    "rename_similarity": 50,
                },
            }
        )
        + "\n"
    )


def _message(item: TestChangeFinding) -> str:
    if item.code == "tests.deleted-file":
        return "Python test-file path present at merge base is absent at head; test behavior may have moved."
    return "Existing named test gained a supported unconditional skip declaration."


def _literal(value: str) -> str:
    return json.dumps(redact_sensitive_text(value), ensure_ascii=True)


@redacted_text_output
def render_test_changes_text(report: TestChangesReport) -> str:
    lines = [
        "Test change review (advisory)",
        f"Compared: {report.merge_base} -> {report.head}",
        f"Scope: {_SCOPE}",
        f"Inspection: {'complete' if report.complete else 'incomplete'} within this scope.",
        _RENAMES,
    ]
    for item in report.findings:
        lines.append(
            f"  {item.code}: {_literal(item.path)}:{item.line}:{item.column} ({item.revision}): {_message(item)}"
        )
        if item.test is not None:
            lines.append(
                f"    Test: {_literal(item.test)}; previous declaration: {_literal(item.previous_path or '')}:{item.previous_line} (merge base)."
            )
    if not report.findings:
        lines.append("No findings within the inspected scope.")
    for rename in report.renames:
        lines.append(
            f"  Rename candidate: {_literal(rename.previous_path)} -> {_literal(rename.path)} ({rename.similarity}% similarity)."
        )
    lines.extend(f"  Limit: {_literal(item)}" for item in report.limitations)
    lines.extend(
        ("Review whether the test removal or skip is intentional and sufficiently covered elsewhere.", _BOUNDARY)
    )
    return "\n".join(lines) + "\n"


def render_test_changes_markdown(report: TestChangesReport) -> str:
    lines = [
        "## Test change review",
        "",
        f"Advisory inspection. {_SCOPE}",
        "",
        f"**Inspection:** {'complete' if report.complete else 'incomplete'} within this scope. **Findings:** {len(report.findings)}.",
        "",
        f"- Base: {markdown_code(report.base)}",
        f"- Head: {markdown_code(report.head)}",
        f"- Merge base: {markdown_code(report.merge_base)}",
        "",
        _RENAMES,
        "",
    ]
    for item in report.findings:
        lines.append(
            f"- {markdown_code(item.code)}: {markdown_code(f'{item.path}:{item.line}:{item.column}')} ({item.revision}). {_message(item)}"
        )
        if item.test is not None:
            lines.append(
                f"  - Test: {markdown_code(item.test)}; previous declaration: {markdown_code(f'{item.previous_path}:{item.previous_line}')} (merge base)."
            )
    if not report.findings:
        lines.append("No findings within the inspected scope.")
    for rename in report.renames:
        lines.append(
            f"- Rename candidate: {markdown_code(rename.previous_path)} -> {markdown_code(rename.path)} ({rename.similarity}% similarity)."
        )
    if report.limitations:
        lines.extend(("", "### Inspection limits", ""))
        lines.extend(f"- {markdown_code(item)}" for item in report.limitations)
    lines.extend(
        (
            "",
            "Review whether the test removal or skip is intentional and sufficiently covered elsewhere.",
            "",
            _BOUNDARY,
        )
    )
    return bounded_markdown("\n".join(lines) + "\n")


@redacted_text_output
def render_test_changes_annotations(report: TestChangesReport) -> str:
    lines = []
    for item in report.findings:
        message = escape_github_command_value(f"{_literal(item.path)} ({item.revision}): {_message(item)} {_BOUNDARY}")
        if item.revision == "head" and not any(
            unicodedata.category(char) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for char in item.path
        ):
            path = escape_github_command_value(redact_sensitive_text(item.path))
            lines.append(f"::notice file={path},line={item.line},col={item.column},title=Test change::{message}")
        else:
            # Deleted-file spans refer to the old tree, not a current PR line.
            lines.append(f"::notice title=Test change::{message}")
    lines.extend(f"::warning::{escape_github_command_value(_literal(item))}" for item in report.limitations)
    if not report.findings:
        lines.append("::notice::No findings within the inspected scope; collection and execution are not verified.")
    return "\n".join(lines) + "\n"
