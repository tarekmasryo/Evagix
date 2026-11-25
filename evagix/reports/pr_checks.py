"""Advisory Markdown for already collected, redacted PR check reports."""

from __future__ import annotations

from collections import Counter
from typing import Any

from evagix.reports.safe_markdown import bounded_markdown, markdown_code, markdown_details


def _inventory_sections(payload: dict[str, Any], *, show_all: bool) -> list[str]:
    lines: list[str] = []
    revisions = {revision["kind"]: revision for revision in payload["revisions"]}
    for kind, heading in (("head", "Head checks"), ("test_merge", "Test-merge checks")):
        lines.extend(("", f"### {heading}", ""))
        revision = revisions.get(kind)
        if revision is None:
            lines.append(f"Availability: {markdown_code(payload['test_merge_status'])}. No inventory available.")
            continue
        checks = revision["checks"]
        counts = Counter(check["result"] for check in checks)
        lines.extend(
            (
                f"Revision: {markdown_code(revision['sha'])}.",
                "",
                f"Inventory: **{revision['completeness']}**. "
                + "; ".join(
                    f"{state}: {counts[state]}" for state in ("passed", "failed", "pending", "other", "unknown")
                )
                + ".",
                "",
            )
        )
        for check in checks:
            if check["result"] == "passed" and not show_all:
                continue
            lines.append(
                f"- **{check['result']}** — {markdown_code(check['name'])}; "
                f"kind: {markdown_code(check['kind'])}; producer: {markdown_code(check['producer'] or 'unknown')} "
                f"(ID: {markdown_code(check['producer_id'] if check['producer_id'] is not None else 'unknown')}); "
                f"status: {markdown_code(check['status'])}; conclusion: {markdown_code(check['conclusion'] or 'none')}."
            )
            if check["url"] is not None:
                lines.append(f"  {markdown_details(check['url'])}")
        if not checks:
            lines.append("No checks observed; this does not establish test execution.")
        elif not show_all and counts["passed"]:
            lines.extend(("", f"Passed rows hidden: {counts['passed']}. Use `--all` to include them."))
    lines.extend(
        (
            "",
            "**Next:** Inspect failed, pending, or inconclusive checks and confirm required-check coverage.",
            "",
            "Required-check policy is unknown; merge readiness is not evaluated.",
        )
    )
    return lines


def _expectation_sections(payload: dict[str, Any], *, show_all: bool) -> list[str]:
    results = payload["results"]
    counts = Counter(item["outcome"] for item in results)
    lines = [
        "",
        "### Expected checks",
        "",
        "; ".join(f"{state}: {counts[state]}" for state in ("passed", "failed", "pending", "missing", "unverified"))
        + ".",
        "",
        f"Expectations digest: {markdown_code(payload['expectations_digest'])}.",
        "",
        "Authority: `caller_supplied`; policy decision: `not_evaluated`.",
        "",
    ]
    for item in results:
        if item["outcome"] == "passed" and not show_all:
            continue
        expected = item["expected"]
        lines.append(
            f"- **{item['outcome']}** — {markdown_code(expected['name'])}; "
            f"scope: {markdown_code(expected['revision'])}; kind: {markdown_code(expected['kind'])}; "
            f"producer ID: {markdown_code(expected['producer_id'])}."
        )
        lines.append(
            f"  Revision: {markdown_code(item['revision_sha'] or 'unavailable')}; "
            f"inventory: {markdown_code(item['inventory'])}; reason: {markdown_code(item['reason'])}."
        )
        for observed in item["observed"]:
            lines.append(
                f"  Observed ID: {markdown_code(observed['id'])}; "
                f"producer ID: {markdown_code(observed['producer_id'] if observed['producer_id'] is not None else 'unknown')}; "
                f"result: {markdown_code(observed['result'])}."
            )
            if observed["url"] is not None:
                lines.append(f"  {markdown_details(observed['url'])}")
    if not show_all and counts["passed"]:
        lines.extend(("", f"Passed expectations hidden: {counts['passed']}. Use `--all` to include them."))
    lines.extend(
        (
            "",
            "**Next:** Review missing or failed checks, wait for pending checks, and resolve unverified evidence.",
            "Confirm the supplied list covers the project's requirements; a check may not have started yet.",
        )
    )
    return lines


def render_pr_checks_markdown(payload: dict[str, Any], *, show_all: bool = False) -> str:
    """Render an inventory or expectation comparison without changing its verdicts."""
    lines = [
        "## Evagix PR checks",
        "",
        "**Advisory snapshot of GitHub-reported metadata.** This report does not prove which code was tested "
        "or authorize merging.",
        "",
        f"Repository: {markdown_code(payload['repository'])}; PR: {markdown_code(payload['pull_request'])}.",
        "",
        f"Base: {markdown_code(payload['base_sha'])}; head: {markdown_code(payload['head_sha'])}.",
        "",
        f"Collection: **{payload['completeness']}**; test-merge availability: {markdown_code(payload['test_merge_status'])}.",
    ]
    if payload["completeness"] == "incomplete":
        lines.extend(("", "**Incomplete collection: do not infer missing checks or a clean result.**"))
    lines.extend(
        _expectation_sections(payload, show_all=show_all)
        if payload["kind"] == "github_pr_expectations"
        else _inventory_sections(payload, show_all=show_all)
    )
    lines.extend(("", "Exit status describes collection completeness, not check success or merge approval."))
    return bounded_markdown("\n".join(lines) + "\n")
