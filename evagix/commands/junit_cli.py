"""Opt-in local pytest JUnit report inspection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evagix.reports.safe_markdown import markdown_code
from evagix.verification.junit import read_junit_report


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "junit-report",
        help="Preview: inspect a local pytest JUnit XML report (offline, advisory).",
        description=(
            "Read one local pytest JUnit XML report without running tests or contacting services. "
            "Exit 0 means consistent report collection, not test success; 1 means incomplete data; "
            "2 means unreadable, malformed or unsafe input. Execution and revision remain unverified."
        ),
    )
    parser.add_argument("path", type=Path, metavar="PATH", help="Local pytest --junitxml report (UTF-8).")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")
    parser.add_argument("--all", action="store_true", help="Include passed rows in text; JSON includes all rows.")


def _render_text(payload: dict[str, Any], *, show_all: bool) -> str:
    lines = [
        "Local pytest JUnit report (preview, advisory)",
        f"Report collection: {payload['collection_status']}; reported outcome: {payload['reported_outcome']}",
        "Observed case rows: " + ", ".join(f"{key}={value}" for key, value in payload["counts"].items()),
        "Source verification: unverified; revision binding: unknown; run completion: unknown.",
        "Counts describe this file only; they do not establish full-suite execution, test quality or task completion.",
        "Policy decision: not_evaluated. Exit status describes collection, not test success.",
    ]
    for issue in payload["issues"]:
        lines.append(f"Report issue: {issue}")
    hidden = 0
    for suite in payload["suites"]:
        note = " (identity shortened)" if suite["identity_truncated"] else ""
        lines.extend(("", f"Suite: {markdown_code(suite['name'])}{note}"))
        if payload["collection_status"] == "incomplete":
            lines.append(f"  Declared counters: {suite['declared']}; observed counters: {suite['observed']}")
        for case in suite["cases"]:
            if case["outcome"] == "passed" and not show_all:
                hidden += 1
                continue
            identity = f"{case['classname']}::{case['name']}" if case["classname"] else case["name"]
            markers = ", ".join(case["markers"]) or "none"
            note = " (identity shortened)" if case["identity_truncated"] else ""
            lines.append(f"  {case['outcome']}: {markdown_code(identity)}{note}; markers: {markers}")
    if hidden:
        lines.append(f"Passed rows hidden: {hidden}. Use --all to include them.")
    lines.append("Messages, tracebacks, properties and captured logs are omitted.")
    return "\n".join(lines)


def dispatch(args: argparse.Namespace) -> int | None:
    if args.command != "junit-report":
        return None
    report = read_junit_report(args.path)
    payload = report.to_dict()
    if args.format == "json":
        # Escape control/format characters as well as non-ASCII text for literal
        # terminal-safe JSON. Decoding preserves legitimate Unicode identities.
        print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
    else:
        print(_render_text(payload, show_all=args.all))
    return {"complete": 0, "incomplete": 1, "error": 2}[report.collection_status]
