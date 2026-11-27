"""Explicit artifact-to-run association; the offline JUnit command is unchanged."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from evagix.verification.github_junit import JUnitArtifactRequest, inspect_github_junit


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "junit-github",
        help="Preview: associate a local JUnit artifact ZIP with GitHub run metadata (online, advisory).",
        description=(
            "Read an original local artifact ZIP and contact GitHub.com to compare its digest, run and provider revision. "
            "The selected attempt is checked separately; artifact-producing attempt and tested code remain unknown. "
            "No archive extraction, report upload, test execution or merge-policy evaluation. "
            "Exit 0 means complete matching collection with a current selected attempt, not successful tests; "
            "1 means incomplete, mismatched or stale evidence; 2 means input or collection error."
        ),
    )
    parser.add_argument(
        "path", type=Path, metavar="ARCHIVE", help="Original downloaded artifact ZIP, not repacked XML."
    )
    parser.add_argument("--run", required=True, metavar="RUN_URL", help="https://github.com/OWNER/REPO/actions/runs/N")
    parser.add_argument("--attempt", required=True, metavar="N", help="Explicit run attempt to inspect.")
    parser.add_argument(
        "--artifact-id", required=True, metavar="N", help="Explicit artifact ID in the selected repository."
    )
    parser.add_argument(
        "--revision", required=True, metavar="SHA", help="Expected full provider head_sha; not tested-code proof."
    )
    parser.add_argument("--member", default="evagix-quality-junit.xml", help="Sole XML member name in the ZIP.")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")


def _positive(value: str) -> int:
    if re.fullmatch(r"[1-9][0-9]{0,18}", value) is None:
        raise ValueError("Invalid identifier")
    return int(value)


def _request(args: argparse.Namespace) -> JUnitArtifactRequest:
    match = re.fullmatch(r"https://github\.com/([^/?#]+/[^/?#]+)/actions/runs/([1-9][0-9]{0,18})/?", args.run)
    if match is None:
        raise ValueError("Invalid run URL")
    return JUnitArtifactRequest(
        match[1],
        int(match[2]),
        _positive(args.attempt),
        _positive(args.artifact_id),
        args.revision,
        args.member,
    )


def _text(payload: dict[str, Any]) -> str:
    request = payload["request"]
    run_url = f"https://github.com/{request['repository']}/actions/runs/{request['run_id']}"
    lines = [
        "GitHub JUnit artifact association (preview, advisory)",
        f"Collection: {payload['collection_status']}",
        f"Run: {run_url}; artifact: {request['artifact_id']}",
        f"Archive digest binding: {payload['archive_binding']}; artifact/run match: {payload['artifact_run_match']}",
        f"Expected provider revision: {request['revision']}; match: {payload['revision_match']}",
        f"Selected attempt: {request['attempt']}; currentness: {payload['selected_attempt_status']}",
    ]
    if payload["run"] is not None:
        run, attempt = payload["run"], payload["attempt"]
        lines.extend(
            (
                f"Provider head_sha: {run['provider_head_sha']}; latest attempt: {run['attempt']}",
                f"Selected attempt metadata: {attempt['status']}; conclusion: {attempt['conclusion'] or 'unknown'}",
            )
        )
    if payload["junit"] is not None:
        junit = payload["junit"]
        lines.extend(
            (
                f"XML collection: {junit['collection_status']}; reported outcome: {junit['reported_outcome']}",
                "Observed case rows: " + ", ".join(f"{key}={value}" for key, value in junit["counts"].items()),
            )
        )
        lines.extend(f"XML issue: {issue}" for issue in junit["issues"])
    else:
        lines.append("No XML results attributed to the selected run.")
    lines.extend(f"Association issue: {issue}" for issue in payload["issues"])
    lines.extend(
        (
            "Artifact-producing attempt: unknown; GitHub artifact metadata does not supply that binding.",
            "Execution verification: unverified; tested revision: unknown; policy decision: not_evaluated.",
            "Run conclusions and XML outcomes are separate. No full-suite, test-quality or task-completion claim.",
        )
    )
    return "\n".join(lines)


def dispatch(args: argparse.Namespace) -> int | None:
    if args.command != "junit-github":
        return None
    try:
        request = _request(args)
    except ValueError:
        print("ERROR: Invalid JUnit association arguments; use junit-github --help for usage.", file=sys.stderr)
        return 2
    report = inspect_github_junit(args.path, request=request, token=os.environ.get("EVAGIX_GITHUB_TOKEN"))
    payload = report.to_dict()
    print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) if args.format == "json" else _text(payload))
    return report.exit_code
