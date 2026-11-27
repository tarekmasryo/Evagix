"""Advisory Markdown for a local, unverified pytest JUnit report."""

from __future__ import annotations

from evagix.reports.safe_markdown import bounded_markdown, markdown_code
from evagix.verification.junit import JUnitReport


def render_junit_report_markdown(report: JUnitReport) -> str:
    """Render reported outcomes without assigning execution or revision trust."""
    payload = report.to_dict()
    lines = [
        "## Local pytest JUnit report",
        "",
        "**Unverified local input:** this file is not associated with a GitHub job or the requested commits.",
        "Source verification: `unverified`; revision binding: `unknown`; run completion: `unknown`.",
        "Policy decision: `not_evaluated`. Counts do not establish full-suite execution, test quality or task completion.",
        "",
        f"**Collection:** {payload['collection_status']}; **Reported outcome:** {payload['reported_outcome']}.",
        "Observed case rows: " + ", ".join(f"{key}={value}" for key, value in payload["counts"].items()) + ".",
    ]
    if report.collection_status == "incomplete":
        lines.extend(("", "**Incomplete report: do not infer a clean result or complete test execution.**"))
    for issue in payload["issues"]:
        lines.append(f"- Report issue: {markdown_code(issue)}.")
    hidden = 0
    for suite in payload["suites"]:
        note = " (display identity shortened)" if suite["identity_truncated"] else ""
        lines.extend(("", f"### Suite: {markdown_code(suite['name'])}{note}", ""))
        if report.collection_status == "incomplete":
            for label, counters in (("Declared", suite["declared"]), ("Observed", suite["observed"])):
                lines.append(
                    f"{label} suite counters: "
                    + ", ".join(f"{key}={value if value is not None else 'unknown'}" for key, value in counters.items())
                    + "."
                )
            lines.append("Suite failure/error/skip counters count markers, separately from case-row outcomes.")
        for case in suite["cases"]:
            if case["outcome"] == "passed":
                hidden += 1
                continue
            identity = f"{case['classname']}::{case['name']}" if case["classname"] else case["name"]
            note = " (display identity shortened)" if case["identity_truncated"] else ""
            markers = ", ".join(case["markers"]) or "none"
            lines.append(
                f"- **{case['outcome']}**: {markdown_code(identity)}{note}; markers: {markdown_code(markers)}."
            )
    if hidden:
        lines.extend(("", f"Passed rows hidden: {hidden}. Use `evagix junit-report PATH --all` to inspect them."))
    lines.extend(
        (
            "",
            "Messages, tracebacks, properties, source paths and captured logs are omitted. "
            "Display identities are not unique or authenticated evidence identifiers.",
            "Exit status describes collection completeness, not test success or merge approval.",
        )
    )
    return bounded_markdown("\n".join(lines) + "\n")
