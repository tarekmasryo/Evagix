"""Advisory evidence for explicit document links broken by committed deletions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from evagix.core.text import escape_github_command_value
from evagix.reference_links import extract_local_links
from evagix.scanning.git_snapshot import GitSnapshot
from evagix.security.output import redacted_text_output
from evagix.security.redaction import redact_sensitive_text
from evagix.utils import stable_json

_DOCUMENTS = ("README.md", "AGENTS.md")
_DOCUMENT_LIMIT = 500_000
_FINDING_LIMIT = 1000


@dataclass(frozen=True)
class DeletedReference:
    document: str
    line: int
    column: int
    target: str
    code: str = "context.deleted-file-reference"
    severity: str = "advisory"

    def __post_init__(self) -> None:
        object.__setattr__(self, "target", redact_sensitive_text(self.target))


@dataclass(frozen=True)
class ReferenceDriftReport:
    base: str
    head: str
    merge_base: str
    inspected_documents: list[str]
    limitations: list[str]
    findings: list[DeletedReference]

    @property
    def complete(self) -> bool:
        return not self.limitations


def build_reference_drift_report(root: Path, *, base: str = "main", head: str = "HEAD") -> ReferenceDriftReport:
    git = GitSnapshot(root)
    base_oid, head_oid = git.resolve(base), git.resolve(head)
    ancestor = git.merge_base(base_oid, head_oid)
    before, after = git.tree(ancestor), git.tree(head_oid)
    deleted = {path for path, entry in before.items() if entry.regular and path not in after}
    report = ReferenceDriftReport(base_oid, head_oid, ancestor, [], [], [])
    for document in _DOCUMENTS:
        entry = after.get(document)
        if entry is None:
            continue
        if not entry.regular:
            report.limitations.append(f"{document}: not a regular tracked file; not inspected.")
            continue
        try:
            text = git.text(entry, limit=_DOCUMENT_LIMIT)
        except (RuntimeError, ValueError):
            report.limitations.append(f"{document}: unavailable, oversized, or invalid UTF-8; not inspected.")
            continue
        if "\0" in text:
            report.limitations.append(f"{document}: binary content; not inspected.")
            continue
        report.inspected_documents.append(document)
        for link in extract_local_links(text):
            if link.target not in deleted:
                continue
            if len(report.findings) >= _FINDING_LIMIT:
                report.limitations.append("Finding limit reached; remaining links were not evaluated.")
                return report
            report.findings.append(DeletedReference(document, link.line, link.column, link.target))
    return report


def render_reference_drift_json(report: ReferenceDriftReport) -> str:
    return (
        stable_json(
            {
                "schema_version": "1.0",
                "tool": "evagix",
                "kind": "deleted_reference_drift",
                **asdict(report),
                "completeness": "complete" if report.complete else "incomplete",
                "scope": {
                    "documents": list(_DOCUMENTS),
                    "syntax": "markdown_inline_links",
                    "working_tree": "excluded",
                },
            }
        )
        + "\n"
    )


@redacted_text_output
def render_reference_drift_text(report: ReferenceDriftReport) -> str:
    lines = [
        "Deleted-file reference review (advisory)",
        f"Compared: {report.merge_base} -> {report.head}",
        "Scope: root README.md / AGENTS.md; explicit local Markdown links; committed snapshots only.",
        f"Inspection: {'complete' if report.complete else 'incomplete'} within this scope.",
    ]
    for item in report.findings:
        lines.append(
            f"  {item.document}:{item.line}:{item.column}: {item.target} existed before and is absent at head."
        )
    if not report.findings:
        lines.append("No deleted-file references found within the inspected scope.")
    lines.extend(f"  Limit: {item}" for item in report.limitations)
    lines.append("Review the reference; this report does not decide merge readiness or select a replacement.")
    return "\n".join(lines) + "\n"


@redacted_text_output
def render_reference_drift_github_annotations(report: ReferenceDriftReport) -> str:
    lines = []
    for item in report.findings:
        message = escape_github_command_value(
            f"Referenced file removed since merge base: {item.target}. Review the link."
        )
        lines.append(
            f"::notice file={item.document},line={item.line},col={item.column},title=Deleted-file reference::{message}"
        )
    lines.extend(f"::warning::{escape_github_command_value(item)}" for item in report.limitations)
    if not lines:
        lines.append("::notice::No deleted-file references found within the inspected scope.")
    return "\n".join(lines) + "\n"
