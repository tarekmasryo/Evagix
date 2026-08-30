from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from evagix.commands.git_cmds import _cmd_changed, _cmd_pr_risk


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    changed_parser = subparsers.add_parser(
        "changed", help="Assess changed files against a git base reference and recommend required gates."
    )
    changed_parser.add_argument("path", nargs="?", default=".")
    changed_parser.add_argument("--base", default="main", help="Git ref used as the comparison base. Default: main.")
    changed_parser.add_argument("--head", default="HEAD", help="Git ref used as the comparison head. Default: HEAD.")
    changed_parser.add_argument("--format", choices=["text", "json", "github-annotations"], default="text")

    pr_risk_parser = subparsers.add_parser(
        "pr-risk", help="Review PR-level repository risk and return merge/review/block guidance."
    )
    pr_risk_parser.add_argument("path", nargs="?", default=".")
    pr_risk_parser.add_argument("--base", default="main", help="Git ref used as the comparison base. Default: main.")
    pr_risk_parser.add_argument("--head", default="HEAD", help="Git ref used as the comparison head. Default: HEAD.")
    pr_risk_parser.add_argument("--format", choices=["text", "json", "github-annotations"], default="text")
    pr_risk_parser.add_argument("--profile", action="append", help="Override/add policy profile. May be repeated.")


def dispatch(args: Any) -> int | None:
    if args.command == "changed":
        return _cmd_changed(
            Path(args.path),
            base=args.base,
            head=args.head,
            output_format=args.format,
            style=args.terminal_style,
        )
    if args.command == "pr-risk":
        return _cmd_pr_risk(
            Path(args.path),
            base=args.base,
            head=args.head,
            output_format=args.format,
            profiles=args.profile,
            style=args.terminal_style,
        )
    return None
