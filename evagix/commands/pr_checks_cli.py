from __future__ import annotations

import argparse

from evagix.commands.verification_cli import _output_format


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "pr-checks",
        help="Show GitHub-reported pull request checks (uses network).",
        description=(
            "Collect checks for a GitHub.com pull request without a local repository. "
            "This command makes network requests. Optional authentication uses EVAGIX_GITHUB_TOKEN only. "
            "Exit 0 means complete report collection, not check success. Exit 1 means incomplete inventory; "
            "exit 2 means invalid input or collection failure. Required-check policy is not evaluated."
        ),
    )
    parser.add_argument("url", metavar="PR_URL", help="https://github.com/OWNER/REPO/pull/N")
    parser.add_argument(
        "--format", type=_output_format, choices=["text", "json"], default="text", help="Output format."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include passed rows in text output; JSON always includes every collected row.",
    )


def dispatch(args: argparse.Namespace) -> int | None:
    if args.command != "pr-checks":
        return None
    from evagix.commands.pr_checks import _cmd_pr_checks

    return _cmd_pr_checks(args.url, args.format, show_all=args.all)
