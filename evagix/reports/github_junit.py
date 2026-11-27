"""Bounded advisory Markdown for a selected artifact and PR metadata scope."""

from __future__ import annotations

from evagix.reports.safe_markdown import bounded_markdown, markdown_code
from evagix.verification.github_junit import GitHubJUnitReport


def _match(value: bool | None) -> str:
    return "unknown" if value is None else "match" if value else "mismatch"


def render_github_junit_markdown(
    report: GitHubJUnitReport, *, repository_match: bool | None, head_repository_match: bool | None
) -> str:
    """Show linkage separately from test outcomes and unauthenticated execution."""
    data = report.to_dict()
    request = data["request"]
    lines = [
        "## GitHub-associated JUnit report",
        "",
        "**Advisory metadata association, not authenticated test execution.**",
        f"Collection: {markdown_code(data['collection_status'])}.",
        f"Selected run: {markdown_code(request['run_id'])}; artifact: {markdown_code(request['artifact_id'])}.",
        f"PR repository identity: {markdown_code(_match(repository_match))}; "
        f"head repository identity: {markdown_code(_match(head_repository_match))}.",
        f"Archive digest binding: {markdown_code(data['archive_binding'])}; "
        f"artifact/run match: {markdown_code(data['artifact_run_match'])}.",
        f"Expected provider revision (requested PR head): {markdown_code(request['revision'])}; "
        f"revision match: {markdown_code(data['revision_match'])}.",
        f"Selected attempt: {markdown_code(request['attempt'])}; "
        f"currentness: {markdown_code(data['selected_attempt_status'])}.",
        "Currentness compares attempts within the selected run; it does not select the latest workflow or PR run.",
    ]
    scope_matches = repository_match is True and head_repository_match is True
    if report.exit_code != 0 or not scope_matches:
        lines.extend(("", "**Incomplete or unmatched evidence: do not infer a clean result for the requested PR.**"))
    if data["run"] is not None:
        run, attempt = data["run"], data["attempt"]
        lines.extend(
            (
                "",
                f"Provider head_sha: {markdown_code(run['provider_head_sha'])}.",
                f"Run state: {markdown_code(run['status'])}; conclusion: {markdown_code(run['conclusion'] or 'unknown')}.",
                f"Selected attempt state: {markdown_code(attempt['status'])}; "
                f"conclusion: {markdown_code(attempt['conclusion'] or 'unknown')}.",
            )
        )
    for issue in data["issues"]:
        lines.append(f"- Association issue: {markdown_code(issue)}.")
    junit = data["junit"]
    if junit is not None and scope_matches:
        lines.extend(
            (
                "",
                "**XML observations for the selected artifact/run, not proof of PR test execution:**",
                f"XML collection: {markdown_code(junit['collection_status'])}; "
                f"reported outcome: {markdown_code(junit['reported_outcome'])}.",
                "Observed case rows: " + ", ".join(f"{key}={value}" for key, value in junit["counts"].items()) + ".",
            )
        )
        lines.extend(f"- XML issue: {markdown_code(issue)}." for issue in junit["issues"])
    else:
        lines.extend(("", "No XML counts are displayed for the requested PR scope."))
    lines.extend(
        (
            "",
            "Artifact-producing attempt: `unknown`; tested revision: `unknown`; execution verification: `unverified`.",
            "Policy decision: `not_evaluated`. Run conclusions, observed PR checks and XML outcomes remain separate.",
            "A matching provider revision does not prove that this run was triggered by the PR or tested its "
            "head/test-merge checkout. No full-suite, test-quality or task-completion claim is made.",
            "Test names, messages, tracebacks, properties, source paths and captured logs are omitted.",
        )
    )
    return bounded_markdown("\n".join(lines) + "\n")
