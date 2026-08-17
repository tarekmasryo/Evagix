from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from evagix import __version__
from evagix.commands.generation import (
    _cmd_baseline,
    _cmd_check,
    _cmd_compile,
    _cmd_diff,
    _cmd_init,
    _cmd_init_ci,
    _cmd_onboard,
    _cmd_scoped,
    _cmd_sync,
)
from evagix.constants import DEFAULT_GITHUB_REF, DEFAULT_GITHUB_REPO
from evagix.targets import ALL_TARGET_KEYS
from evagix.thresholds import score_threshold_arg
from evagix.validators import supported_target_names

CHECK_HELP = "Validate Evagix-managed generated context freshness and self-governance drift."


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    compile_parser = subparsers.add_parser("compile", help="Export governed repository context to configured targets.")
    compile_parser.add_argument("path", nargs="?", default=".")
    compile_parser.add_argument(
        "--target",
        action="append",
        choices=sorted(ALL_TARGET_KEYS),
        help=f"Target to generate. May be repeated. Supported: {supported_target_names()}",
    )
    compile_parser.add_argument("--dry-run", action="store_true", help="Print planned writes without writing files.")
    compile_parser.add_argument("--profile", action="append", help="Override/add policy profile. May be repeated.")
    compile_parser.add_argument("--force", action="store_true", help="Overwrite existing non-evagix files.")

    sync_parser = subparsers.add_parser(
        "sync", help="Regenerate governed context exports and immediately validate them."
    )
    sync_parser.add_argument("path", nargs="?", default=".")
    sync_parser.add_argument("--plan", action="store_true", help="Show planned writes without modifying files.")
    sync_parser.add_argument("--profile", action="append", help="Override/add policy profile. May be repeated.")

    check_parser = subparsers.add_parser("check", help=CHECK_HELP, description=CHECK_HELP)
    check_parser.add_argument("path", nargs="?", default=".")
    check_parser.add_argument("--profile", action="append", help="Override/add policy profile. May be repeated.")

    onboard_parser = subparsers.add_parser("onboard", help="Generate a human and AI onboarding pack under .evagix/.")
    onboard_parser.add_argument("path", nargs="?", default=".")
    onboard_parser.add_argument("--dry-run", action="store_true", help="Print planned writes without writing files.")
    onboard_parser.add_argument("--force", action="store_true", help="Overwrite existing onboarding files.")
    onboard_parser.add_argument("--profile", action="append", help="Override/add policy profile. May be repeated.")

    baseline_parser = subparsers.add_parser(
        "baseline", help="Write current findings into evagix.toml ignore list for staged adoption."
    )
    baseline_parser.add_argument("path", nargs="?", default=".")
    baseline_parser.add_argument("--force", action="store_true", help="Overwrite existing config.")
    baseline_parser.add_argument(
        "--profile", action="append", help="Profile to include in generated config. May be repeated."
    )

    diff_parser = subparsers.add_parser("diff", help="Show diffs between current and generated files.")
    diff_parser.add_argument("path", nargs="?", default=".")
    diff_parser.add_argument(
        "--target", action="append", choices=sorted(ALL_TARGET_KEYS), help="Target to diff. May be repeated."
    )

    init_parser = subparsers.add_parser("init", help="Create an evagix.toml configuration file.")
    init_parser.add_argument("path", nargs="?", default=".")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing config.")
    init_parser.add_argument(
        "--profile", action="append", help="Profile to include in generated config. May be repeated."
    )

    ci_parser = subparsers.add_parser("init-ci", help="Create a GitHub Actions drift/readiness workflow.")
    ci_parser.add_argument("path", nargs="?", default=".")
    ci_parser.add_argument("--force", action="store_true", help="Overwrite existing workflow.")
    ci_parser.add_argument(
        "--fail-under",
        type=score_threshold_arg,
        default=80,
        help="Readiness score threshold used by the generated workflow (0-100).",
    )
    ci_parser.add_argument(
        "--install-mode",
        choices=["github", "pypi", "editable"],
        default="github",
        help="How the generated workflow installs Evagix. Use github/pypi for external repos; editable only for the Evagix repo itself.",
    )
    ci_parser.add_argument("--repo", default=DEFAULT_GITHUB_REPO, help="GitHub repo used when --install-mode github.")
    ci_parser.add_argument("--ref", default=DEFAULT_GITHUB_REF, help="Git ref/tag used when --install-mode github.")
    ci_parser.add_argument(
        "--package-version", default=__version__, help="Package version used when --install-mode pypi."
    )

    scoped_parser = subparsers.add_parser("scoped", help="Generate scoped AGENTS.md files for detected subprojects.")
    scoped_parser.add_argument("path", nargs="?", default=".")
    scoped_parser.add_argument(
        "--dry-run", action="store_true", help="Print planned scoped files without writing them."
    )
    scoped_parser.add_argument("--force", action="store_true", help="Overwrite existing scoped AGENTS.md files.")


def dispatch(args: Any) -> int | None:
    if args.command == "compile":
        return _cmd_compile(
            Path(args.path), target=args.target, dry_run=args.dry_run, force=args.force, profiles=args.profile
        )
    if args.command == "sync":
        return _cmd_sync(Path(args.path), plan=args.plan, profiles=args.profile)
    if args.command == "check":
        return _cmd_check(Path(args.path), profiles=args.profile)
    if args.command == "onboard":
        return _cmd_onboard(Path(args.path), dry_run=args.dry_run, force=args.force, profiles=args.profile)
    if args.command == "baseline":
        return _cmd_baseline(Path(args.path), force=args.force, profiles=args.profile)
    if args.command == "diff":
        return _cmd_diff(Path(args.path), target=args.target)
    if args.command == "init":
        return _cmd_init(Path(args.path), force=args.force, profiles=args.profile)
    if args.command == "init-ci":
        return _cmd_init_ci(
            Path(args.path),
            force=args.force,
            fail_under=args.fail_under,
            install_mode=args.install_mode,
            repo=args.repo,
            ref=args.ref,
            package_version=args.package_version,
        )
    if args.command == "scoped":
        return _cmd_scoped(Path(args.path), dry_run=args.dry_run, force=args.force)
    return None
