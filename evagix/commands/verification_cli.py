from __future__ import annotations

import argparse
from pathlib import Path


def _output_format(value: str) -> str:
    if value not in {"text", "json"}:
        raise argparse.ArgumentTypeError("Output format must be text or json.")
    return value


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "verify-check",
        help="Collect and evaluate one caller-selected GitHub-reported check result (uses network).",
        description=(
            "Explicitly collect GitHub Actions metadata for one selected commit check. "
            "This command makes network requests to GitHub.com. "
            "The request selects the check; it does not authenticate required-check policy. "
            "Optional authentication uses EVAGIX_GITHUB_TOKEN only."
        ),
    )
    parser.add_argument("--request", required=True, metavar="PATH", help="Strict check request JSON file.")
    parser.add_argument("--github-repo", required=True, metavar="OWNER/NAME", help="GitHub repository to contact.")
    parser.add_argument(
        "--format", type=_output_format, choices=["text", "json"], default="text", help="Output format."
    )


def dispatch(args: argparse.Namespace) -> int | None:
    if args.command != "verify-check":
        return None
    from evagix.commands.verification import _cmd_verify_check

    return _cmd_verify_check(Path(args.request), args.github_repo, args.format)
