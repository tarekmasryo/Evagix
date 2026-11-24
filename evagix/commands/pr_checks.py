"""Display PR metadata; exit status describes inventory, never check success."""

from __future__ import annotations

import json
import os
import sys
import unicodedata
from collections import Counter
from typing import Any

from evagix.security.redaction import redact_sensitive_text
from evagix.utils import stable_json
from evagix.verification.github_collection import GitHubCollectionError
from evagix.verification.github_pr_checks import collect_pr_checks

_RESULT_LABELS = {
    "passed": "passed",
    "failed": "failed",
    "pending": "pending",
    "other": "other outcomes",
    "unknown": "unknown",
}


def _escape_invisible(value: str, *, json_text: bool = False) -> str:
    categories = {"Cf", "Cs", "Zl", "Zp"}
    if not json_text:
        categories.add("Cc")
    return "".join(
        json.dumps(char, ensure_ascii=True)[1:-1] if unicodedata.category(char) in categories else char
        for char in value
    )


def _display(value: object) -> str:
    return _escape_invisible(redact_sensitive_text(str(value)))


def _render_text(payload: dict[str, Any], *, show_all: bool) -> str:
    lines = [
        "GitHub-reported pull request checks",
        f"Repository: {_display(payload['repository'])}; PR: #{payload['pull_request']} ({payload['state']})",
        f"Report inventory: {payload['completeness']}",
    ]
    revisions = {revision["kind"]: revision for revision in payload["revisions"]}
    for kind in ("head", "test_merge"):
        revision = revisions.get(kind)
        lines.extend(("", kind))
        if revision is None:
            lines.append(f"  Availability: {payload['test_merge_status']}")
            lines.append("  No inventory available for this revision.")
            continue
        checks = revision["checks"]
        counts = Counter(check["result"] for check in checks)
        lines.extend(
            (
                f"  Revision: {revision['sha']}",
                f"  Inventory: {revision['completeness']}",
                "  Observed: " + ", ".join(f"{label}={counts[result]}" for result, label in _RESULT_LABELS.items()),
            )
        )
        for check in checks:
            if check["result"] == "passed" and not show_all:
                continue
            producer = _display(check["producer"]) if check["producer"] is not None else "unknown"
            conclusion = _display(check["conclusion"]) if check["conclusion"] is not None else "none"
            lines.append(
                f"  [{_RESULT_LABELS[check['result']]}] {_display(check['name'])} "
                f"({check['kind']}; producer: {producer}; status: {_display(check['status'])}; conclusion: {conclusion})"
            )
            if check["url"] is not None:
                lines.append(f"    {_display(check['url'])}")
        if not checks:
            lines.append("  No checks observed.")
        elif not show_all and counts["passed"]:
            lines.append(f"  Passed rows hidden: {counts['passed']}; use --all to show them.")
    results = {check["result"] for revision in payload["revisions"] for check in revision["checks"]}
    if "failed" in results:
        next_action = "Inspect failed checks using their detail links or the PR checks page."
    elif "pending" in results:
        next_action = "Wait for pending checks, or review approvals on the PR."
    elif not results or results & {"other", "unknown"}:
        next_action = "Inspect workflow/provider outcomes on the PR; execution is not established."
    elif payload["completeness"] == "incomplete":
        next_action = "Review the remaining check inventory on the PR."
    else:
        next_action = "Review required-check coverage and approvals on the PR."
    checks_url = _display(f"https://github.com/{payload['repository']}/pull/{payload['pull_request']}/checks")
    lines.extend(
        (
            "",
            f"Next: {next_action}",
            f"PR checks: {checks_url}",
            "Scope: GitHub-reported metadata only.",
            "Required-check coverage is not assessed; this report does not decide merge readiness.",
        )
    )
    return "\n".join(lines)


def _cmd_pr_checks(url: str, output_format: str, *, show_all: bool = False) -> int:
    try:
        report = collect_pr_checks(url, token=os.environ.get("EVAGIX_GITHUB_TOKEN"))
    except GitHubCollectionError as exc:
        print(f"ERROR: {exc} ({exc.code})", file=sys.stderr)
        return 2
    payload = report.to_dict()
    if output_format == "json":
        print(_escape_invisible(stable_json(payload, redact=False), json_text=True))
    else:
        print(_render_text(payload, show_all=show_all))
    return 0 if report.complete else 1
