"""Advisory inspection of script commands whose tracked targets were removed."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from evagix.core.text import escape_github_command_value
from evagix.reference_drift import DeletedReference, ReferenceDriftReport
from evagix.reports.safe_markdown import bounded_markdown, markdown_code
from evagix.scanning.git_snapshot import GitSnapshot, TreeEntry
from evagix.script_references import extract_script_references
from evagix.security.output import redacted_text_output
from evagix.utils import stable_json

_DOCUMENTS = ("README.md", "AGENTS.md")
_DOCUMENT_LIMIT = 500_000
_FINDING_LIMIT = 1000
_SCOPE = (
    "Root README.md / AGENTS.md; supported literal script commands; "
    "repository-root working directory assumed; committed snapshots only."
)
_NEXT = "Review the command's working directory, then update its script path or remove the obsolete instruction."
_BOUNDARY = "This report does not prove execution failure, select a replacement, or decide merge readiness."


def _ambiguous_ancestor(target: str, tree: dict[str, TreeEntry]) -> bool:
    parts = target.split("/")
    return any(
        (entry := tree.get("/".join(parts[:index]))) is not None and entry.mode != "040000"
        for index in range(1, len(parts))
    )


def build_script_drift_report(root: Path, *, base: str = "main", head: str = "HEAD") -> ReferenceDriftReport:
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
        ancestor_limited = False
        for reference in extract_script_references(text):
            if reference.target not in deleted:
                continue
            if _ambiguous_ancestor(reference.target, after):
                if not ancestor_limited:
                    report.limitations.append(
                        f"{document}: script paths below non-directory Git entries at head were not inspected."
                    )
                    ancestor_limited = True
                continue
            if len(report.findings) >= _FINDING_LIMIT:
                report.limitations.append("Finding limit reached; remaining script references were not evaluated.")
                return report
            report.findings.append(
                DeletedReference(
                    document,
                    reference.line,
                    reference.column,
                    reference.target,
                    code="context.deleted-script-reference",
                )
            )
    return report


def render_script_drift_json(report: ReferenceDriftReport) -> str:
    return (
        stable_json(
            {
                "schema_version": "1.0",
                "tool": "evagix",
                "kind": "deleted_script_drift",
                **asdict(report),
                "completeness": "complete" if report.complete else "incomplete",
                "scope": {
                    "documents": list(_DOCUMENTS),
                    "syntax": "literal_script_commands",
                    "working_directory": "repository_root_assumed",
                    "working_tree": "excluded",
                },
            }
        )
        + "\n"
    )


@redacted_text_output
def render_script_drift_text(report: ReferenceDriftReport) -> str:
    lines = [
        "Deleted-script instruction review (advisory)",
        f"Compared: {report.merge_base} -> {report.head}",
        f"Scope: {_SCOPE}",
        f"Inspection: {'complete' if report.complete else 'incomplete'} within this scope.",
    ]
    for item in report.findings:
        lines.append(
            f"  {item.document}:{item.line}:{item.column}: {item.target} was tracked before and is absent at head."
        )
    if not report.findings:
        lines.append("No deleted-script references found within the inspected scope.")
    lines.extend(f"  Limit: {item}" for item in report.limitations)
    lines.extend((_NEXT, _BOUNDARY))
    return "\n".join(lines) + "\n"


def render_script_drift_markdown(report: ReferenceDriftReport) -> str:
    lines = [
        "## Deleted-script instruction review",
        "",
        f"Advisory inspection. {_SCOPE}",
        "",
        f"**Inspection:** {'complete' if report.complete else 'incomplete'} within this scope. "
        f"**Findings:** {len(report.findings)}.",
        "",
        f"- Base: {markdown_code(report.base)}",
        f"- Head: {markdown_code(report.head)}",
        f"- Merge base: {markdown_code(report.merge_base)}",
        "- Inspected documents: " + (", ".join(markdown_code(item) for item in report.inspected_documents) or "none"),
        "",
        "### Findings",
        "",
    ]
    for item in report.findings:
        lines.extend(
            (
                f"- Source: {markdown_code(f'{item.document}:{item.line}:{item.column}')}",
                f"  - Removed script target: {markdown_code(item.target)}",
                "  - The target was a tracked file at the merge base and is absent from the head tree.",
            )
        )
    if not report.findings:
        lines.append("No deleted-script references found within the inspected scope.")
    if report.limitations:
        lines.extend(("", "### Inspection limits", ""))
        lines.extend(f"- {markdown_code(item)}" for item in report.limitations)
        lines.extend(("", "Complete the missing inspection before relying on this report."))
    lines.extend(("", f"**Next:** {_NEXT}", "", _BOUNDARY))
    return bounded_markdown("\n".join(lines) + "\n")


@redacted_text_output
def render_script_drift_github_annotations(report: ReferenceDriftReport) -> str:
    lines = []
    for item in report.findings:
        message = escape_github_command_value(
            f"Script target removed since merge base: {item.target}. Repository-root working directory assumed. {_NEXT}"
        )
        lines.append(
            f"::notice file={item.document},line={item.line},col={item.column},title=Deleted-script reference::{message}"
        )
    lines.extend(f"::warning::{escape_github_command_value(item)}" for item in report.limitations)
    if not lines:
        lines.append("::notice::No deleted-script references found within the inspected scope.")
    return "\n".join(lines) + "\n"
