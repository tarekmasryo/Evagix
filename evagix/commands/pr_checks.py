"""Display PR metadata; exit status describes inventory, never check success."""

from __future__ import annotations

import json
import os
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from evagix.core.io import safe_read_text_result
from evagix.reports.pr_checks import render_pr_checks_markdown
from evagix.security.redaction import redact_sensitive_text
from evagix.utils import stable_json
from evagix.verification._json import decode_object
from evagix.verification.contracts import ContractError
from evagix.verification.github_collection import GitHubCollectionError
from evagix.verification.github_pr_checks import collect_pr_checks
from evagix.verification.pr_expectations import CheckExpectations, compare_pr_checks, parse_expectations

_RESULT_LABELS = {
    "passed": "passed",
    "failed": "failed",
    "pending": "pending",
    "other": "other outcomes",
    "unknown": "unknown",
}
_MAX_EXPECTATIONS_OUTPUT_BYTES = 8_000_000


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


def _load_expectations(path: Path) -> CheckExpectations:
    try:
        contents = safe_read_text_result(path, max_chars=65_536)
    except (OSError, UnicodeError, ValueError):
        raise ContractError("Unable to read expectations as UTF-8.") from None
    if contents.truncated:
        raise ContractError("Expectations file exceeds 65536 characters.")
    return parse_expectations(decode_object(contents.text))


def _render_expectations(payload: dict[str, Any], *, show_all: bool) -> str:
    results = payload["results"]
    counts = Counter(item["outcome"] for item in results)
    lines = [
        "Caller-supplied pull request check expectations",
        f"Repository: {_display(payload['repository'])}; PR: #{payload['pull_request']}",
        f"Report inventory: {payload['completeness']}",
        "Expected: "
        + ", ".join(f"{state}={counts[state]}" for state in ("passed", "failed", "pending", "missing", "unverified")),
    ]
    for item in results:
        if item["outcome"] == "passed" and not show_all:
            continue
        expected = item["expected"]
        lines.append(
            f"  [{item['outcome']}] {_display(expected['name'])} "
            f"({expected['revision']}; {expected['kind']}; producer ID: {expected['producer_id']})"
        )
        lines.append(f"    Revision: {_display(item['revision_sha']) if item['revision_sha'] else 'unavailable'}")
        lines.append(f"    Inventory: {item['inventory']}; reason: {item['reason']}")
        for observed in item["observed"]:
            producer = observed["producer_id"] if observed["producer_id"] is not None else "unknown"
            lines.append(f"    Observed ID: {observed['id']}; producer ID: {producer}; result: {observed['result']}")
            if observed["url"] is not None:
                lines.append(f"      {_display(observed['url'])}")
    if not show_all and counts["passed"]:
        lines.append(f"Passed expectations hidden: {counts['passed']}; use --all to show them.")
    if counts["failed"] or counts["missing"]:
        action = "Review failed or missing expected checks and confirm the expected producer and revision."
    elif counts["pending"]:
        action = "Wait for pending checks, then collect again."
    elif counts["unverified"]:
        action = "Resolve unavailable, incomplete, or ambiguous evidence before relying on these results."
    else:
        action = "Review whether these caller-supplied expectations cover the project's acceptance requirements."
    lines.extend(
        (
            "",
            f"Next: {action}",
            "Expectations authority: caller_supplied; policy decision: not_evaluated.",
            "Advisory provider metadata only; this report does not prove test execution or decide merge readiness.",
        )
    )
    return "\n".join(lines)


def _cmd_pr_checks(
    url: str, output_format: str, *, show_all: bool = False, expectations_path: Path | None = None
) -> int:
    expectations = None
    if expectations_path is not None:
        try:
            expectations = _load_expectations(expectations_path)
        except ContractError:
            print("ERROR: Expectations must be a valid bounded UTF-8 check expectations file.", file=sys.stderr)
            return 2
    try:
        report = collect_pr_checks(url, token=os.environ.get("EVAGIX_GITHUB_TOKEN"))
    except GitHubCollectionError as exc:
        print(f"ERROR: {exc} ({exc.code})", file=sys.stderr)
        return 2
    if expectations is not None:
        try:
            payload = compare_pr_checks(report, expectations).to_dict()
        except ContractError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    else:
        payload = report.to_dict()
    if output_format == "markdown":
        try:
            output = render_pr_checks_markdown(payload, show_all=show_all).rstrip("\n")
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    elif output_format == "json":
        output = _escape_invisible(stable_json(payload, redact=False), json_text=True)
    else:
        output = (
            _render_expectations(payload, show_all=show_all)
            if expectations is not None
            else _render_text(payload, show_all=show_all)
        )
    if expectations is not None and len((output + "\n").encode("utf-8")) > _MAX_EXPECTATIONS_OUTPUT_BYTES:
        print(
            f"ERROR: Expectations report exceeds the {_MAX_EXPECTATIONS_OUTPUT_BYTES}-byte output limit.",
            file=sys.stderr,
        )
        return 2
    print(output)
    return 0 if report.complete else 1
