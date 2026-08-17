from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from evagix.commands.fix_apply import _cmd_fix
from evagix.thresholds import score_threshold_arg


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    fix_parser = subparsers.add_parser("fix", help="Plan or apply a safe built-in remediation for a finding code.")
    fix_parser.add_argument(
        "code", nargs="?", default=None, help="Finding code to fix, or repository path when used with --plan."
    )
    fix_parser.add_argument("path", nargs="?", default=".")
    fix_parser.add_argument(
        "--plan", action="store_true", help="Experimental: print a repository-level fix plan without editing files."
    )
    fix_parser.add_argument("--apply", action="store_true", help="Write safe fix files. Default is dry-run.")
    fix_parser.add_argument(
        "--dry-run", action="store_true", help="Explicit dry-run alias; this is the default behavior."
    )
    fix_parser.add_argument("--force", action="store_true", help="Overwrite existing files when applying a fix.")
    fix_parser.add_argument(
        "--fail-under", type=score_threshold_arg, default=80, help="Readiness threshold used by CI fixes (0-100)."
    )


def dispatch(args: Any) -> int | None:
    if args.command == "fix":
        return _cmd_fix(
            Path(args.path),
            args.code,
            plan=args.plan,
            apply_changes=args.apply,
            force=args.force,
            fail_under=args.fail_under,
        )
    return None
