from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from evagix.commands.reports_cmds import (
    _cmd_audit,
    _cmd_decide,
    _cmd_doctor,
    _cmd_drift,
    _cmd_eval_context,
    _cmd_evidence,
    _cmd_readme_audit,
    _cmd_report,
)
from evagix.thresholds import score_threshold_arg


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    doctor_parser = subparsers.add_parser("doctor", help="Score repository readiness for AI coding agents.")
    doctor_parser.add_argument("path", nargs="?", default=".")
    doctor_parser.add_argument("--json", action="store_true", help="Compatibility alias for --format json.")
    doctor_parser.add_argument(
        "--format", choices=["text", "json", "sarif", "markdown", "pr-comment", "github-annotations"], default="text"
    )
    doctor_parser.add_argument(
        "--no-color",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Disable ANSI styling for human-readable output.",
    )
    doctor_parser.add_argument(
        "--fail-under",
        type=score_threshold_arg,
        default=None,
        help="Exit with failure when score is below this threshold (0-100).",
    )
    doctor_parser.add_argument(
        "--strict",
        action="store_true",
        help="Use stricter evidence-first scoring. Combine with --fail-under to make CI fail below a threshold.",
    )
    doctor_parser.add_argument("--profile", action="append", help="Override/add policy profile. May be repeated.")

    report_parser = subparsers.add_parser("report", help="Write a readiness report.")
    report_parser.add_argument("path", nargs="?", default=".")
    report_parser.add_argument(
        "-o", "--output", help="Report path relative to the repository root. Defaults to a format-specific filename."
    )
    report_parser.add_argument(
        "--format", choices=["markdown", "json", "sarif", "pr-comment", "github-annotations"], default="markdown"
    )
    report_parser.add_argument("--force", action="store_true", help="Overwrite an existing report.")
    report_parser.add_argument("--profile", action="append", help="Override/add policy profile. May be repeated.")

    readme_audit_parser = subparsers.add_parser("readme-audit", help="Audit README claims against repository evidence.")
    readme_audit_parser.add_argument("path", nargs="?", default=".")
    readme_audit_parser.add_argument(
        "--format", choices=["text", "markdown", "json", "github-annotations"], default="text"
    )
    readme_audit_parser.add_argument(
        "--strict",
        action="store_true",
        help="Use stricter evidence levels for high-trust claims. Combine with --fail-on for CI failure policy.",
    )
    readme_audit_parser.add_argument(
        "--fail-on",
        choices=["unsupported", "weak-evidence", "manual-review"],
        default=None,
        help="Exit non-zero when strict README audit reaches this evidence level.",
    )
    readme_audit_parser.add_argument(
        "-o", "--output", default=None, help="Optional output path relative to the repository root."
    )
    readme_audit_parser.add_argument("--force", action="store_true", help="Overwrite an existing output file.")
    readme_audit_parser.add_argument("--profile", action="append", help="Override/add policy profile. May be repeated.")

    for command, help_text in [
        ("decide", "Recommend safe next actions and human approval gates."),
        ("plan", "Alias for decide: recommend a safe repository work plan."),
    ]:
        parser = subparsers.add_parser(command, help=help_text)
        parser.add_argument("path", nargs="?", default=".")
        parser.add_argument("--format", choices=["text", "markdown", "json"], default="text")
        parser.add_argument(
            "-o", "--output", default=None, help="Optional output path relative to the repository root."
        )
        parser.add_argument("--force", action="store_true", help="Overwrite an existing output file.")
        parser.add_argument("--profile", action="append", help="Override/add policy profile. May be repeated.")

    drift_parser = subparsers.add_parser("drift", help="Print a detailed generated context drift report.")
    drift_parser.add_argument("path", nargs="?", default=".")
    drift_parser.add_argument("--format", choices=["text", "markdown", "json"], default="text")
    drift_parser.add_argument(
        "-o", "--output", default=None, help="Optional output path relative to the repository root."
    )
    drift_parser.add_argument("--force", action="store_true", help="Overwrite an existing output file.")
    drift_parser.add_argument("--profile", action="append", help="Override/add policy profile. May be repeated.")

    context_parser = subparsers.add_parser(
        "eval-context", help="Evaluate the quality and completeness of generated agent instruction files."
    )
    context_parser.add_argument("path", nargs="?", default=".")
    context_parser.add_argument("--format", choices=["text", "markdown", "json"], default="text")
    context_parser.add_argument(
        "--strict",
        action="store_true",
        help="Include stricter agent-context quality and safety checks. Combine with --fail-under/--fail-on for CI failure policy.",
    )
    context_parser.add_argument(
        "--fail-on",
        choices=["high", "medium", "low"],
        default=None,
        help="Exit non-zero when strict context findings reach this severity.",
    )
    context_parser.add_argument(
        "--fail-under",
        type=score_threshold_arg,
        default=None,
        help="Exit non-zero when context quality score is below this threshold.",
    )
    context_parser.add_argument(
        "-o", "--output", default=None, help="Optional output path relative to the repository root."
    )
    context_parser.add_argument("--force", action="store_true", help="Overwrite an existing output file.")
    context_parser.add_argument("--profile", action="append", help="Override/add policy profile. May be repeated.")

    evidence_parser = subparsers.add_parser(
        "evidence", help="Write or print the strict evidence ledger for README and agent-context findings."
    )
    evidence_parser.add_argument("path", nargs="?", default=".")
    evidence_parser.add_argument("--format", choices=["json"], default="json")
    evidence_parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output path relative to the repository root. Omit to print JSON to stdout.",
    )
    evidence_parser.add_argument("--force", action="store_true", help="Overwrite an existing output file.")
    evidence_parser.add_argument("--profile", action="append", help="Override/add policy profile. May be repeated.")

    audit_parser = subparsers.add_parser("audit", help="Print a lightweight governance audit for the repository.")
    audit_parser.add_argument("path", nargs="?", default=".")
    audit_parser.add_argument("--json", action="store_true", help="Compatibility alias for --format json.")
    audit_parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")
    audit_parser.add_argument(
        "--no-color",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Disable ANSI styling for human-readable output.",
    )
    audit_parser.add_argument(
        "-o", "--output", default=None, help="Optional Markdown output path relative to the repository root."
    )
    audit_parser.add_argument("--force", action="store_true", help="Overwrite an existing audit report.")
    audit_parser.add_argument("--profile", action="append", help="Override/add policy profile. May be repeated.")


def dispatch(args: Any) -> int | None:
    if args.command == "doctor":
        output_format = "json" if args.json else args.format
        return _cmd_doctor(
            Path(args.path),
            output_format=output_format,
            fail_under=args.fail_under,
            profiles=args.profile,
            strict=args.strict,
            style=args.terminal_style,
        )
    if args.command == "report":
        return _cmd_report(
            Path(args.path),
            output=args.output,
            output_format=args.format,
            force=args.force,
            profiles=args.profile,
        )
    if args.command == "readme-audit":
        return _cmd_readme_audit(
            Path(args.path),
            output_format=args.format,
            output=args.output,
            force=args.force,
            profiles=args.profile,
            strict=args.strict,
            fail_on=args.fail_on,
            style=args.terminal_style,
        )
    if args.command in {"decide", "plan"}:
        return _cmd_decide(
            Path(args.path),
            output_format=args.format,
            output=args.output,
            force=args.force,
            profiles=args.profile,
            style=args.terminal_style,
        )
    if args.command == "drift":
        return _cmd_drift(
            Path(args.path),
            output_format=args.format,
            output=args.output,
            force=args.force,
            profiles=args.profile,
            style=args.terminal_style,
        )
    if args.command == "eval-context":
        return _cmd_eval_context(
            Path(args.path),
            output_format=args.format,
            output=args.output,
            force=args.force,
            profiles=args.profile,
            strict=args.strict,
            fail_on=args.fail_on,
            fail_under=args.fail_under,
            style=args.terminal_style,
        )
    if args.command == "evidence":
        return _cmd_evidence(Path(args.path), output=args.output, force=args.force, profiles=args.profile)
    if args.command == "audit":
        return _cmd_audit(
            Path(args.path),
            as_json=args.json or args.format == "json",
            output=args.output,
            force=args.force,
            profiles=args.profile,
            style=args.terminal_style,
        )
    return None
