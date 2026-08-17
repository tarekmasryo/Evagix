from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from evagix.commands.inspect import (
    _cmd_classify,
    _cmd_explain,
    _cmd_policy,
    _cmd_profiles,
    _cmd_scan,
    _cmd_suggest,
    _cmd_targets,
)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    scan_parser = subparsers.add_parser("scan", help="Inspect a repository and print detected context.")
    scan_parser.add_argument("path", nargs="?", default=".")
    scan_parser.add_argument("--json", action="store_true", help="Compatibility alias for --format json.")
    scan_parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")
    scan_parser.add_argument(
        "--verbose", action="store_true", help="Print all detected subprojects, commands, and warnings."
    )
    scan_parser.add_argument("--profile", action="append", help="Override/add policy profile for the scan output.")

    suggest_parser = subparsers.add_parser("suggest", help="Print prioritized next actions based on doctor findings.")
    suggest_parser.add_argument("path", nargs="?", default=".")
    suggest_parser.add_argument("--profile", action="append", help="Override/add policy profile. May be repeated.")

    profiles_parser = subparsers.add_parser("profiles", help="List available policy profiles.")
    profiles_parser.add_argument("name", nargs="?", help="Optional profile name to show details.")

    targets_parser = subparsers.add_parser("targets", help="List available context export targets.")
    targets_parser.add_argument("action", nargs="?", choices=["list", "show"], default="list")
    targets_parser.add_argument("name", nargs="?", help="Optional target name for `targets show`.")

    policy_parser = subparsers.add_parser("policy", help="Show effective evagix.toml policy.")
    policy_parser.add_argument("path", nargs="?", default=".")
    policy_parser.add_argument("--json", action="store_true", help="Print effective policy as JSON.")

    classify_parser = subparsers.add_parser(
        "classify", help="Classify the repository shape from evidence-backed signals."
    )
    classify_parser.add_argument("path", nargs="?", default=".")
    classify_parser.add_argument("--json", action="store_true", help="Print classification as JSON.")
    classify_parser.add_argument("--profile", action="append", help="Override/add policy profile. May be repeated.")

    explain_parser = subparsers.add_parser("explain", help="Explain a doctor finding code and recommended remediation.")
    explain_parser.add_argument("code", help="Finding code, for example missing-ci or missing-llm-eval.")


def dispatch(args: Any) -> int | None:
    if args.command == "scan":
        return _cmd_scan(
            Path(args.path), as_json=args.json or args.format == "json", verbose=args.verbose, profiles=args.profile
        )
    if args.command == "suggest":
        return _cmd_suggest(Path(args.path), profiles=args.profile)
    if args.command == "profiles":
        return _cmd_profiles(args.name)
    if args.command == "targets":
        return _cmd_targets(args.action, args.name)
    if args.command == "policy":
        return _cmd_policy(Path(args.path), as_json=args.json)
    if args.command == "classify":
        return _cmd_classify(Path(args.path), as_json=args.json, profiles=args.profile)
    if args.command == "explain":
        return _cmd_explain(args.code)
    return None
