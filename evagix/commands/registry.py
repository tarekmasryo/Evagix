from __future__ import annotations

import argparse
import sys
from typing import Protocol, TextIO

from evagix import __version__
from evagix.commands import core_cli, fix_cli, git_cli, inspect_cli, preview_cli, readiness_cli
from evagix.security.output import execute_with_redacted_output
from evagix.terminal import terminal_style


class CommandModule(Protocol):
    def register(self, subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None: ...

    def dispatch(self, args: argparse.Namespace) -> int | None: ...


COMMAND_MODULES: tuple[CommandModule, ...] = (
    inspect_cli,
    core_cli,
    readiness_cli,
    preview_cli,
    git_cli,
    fix_cli,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evagix",
        description="Build, validate, and govern universal repository context for AI coding agents.",
    )
    parser.add_argument("--version", action="version", version=f"evagix {__version__}")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI styling for human-readable output.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for module in COMMAND_MODULES:
        module.register(subparsers)
    for command_parser in subparsers.choices.values():
        if "--no-color" not in command_parser._option_string_actions:
            command_parser.add_argument(
                "--no-color",
                action="store_true",
                default=argparse.SUPPRESS,
                help="Disable ANSI styling for human-readable output.",
            )
    return parser


def _dispatch(argv: list[str] | None = None, *, stdout_target: TextIO | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.terminal_style = terminal_style(
        stdout_target if stdout_target is not None else sys.stdout,
        no_color=args.no_color,
    )
    for module in COMMAND_MODULES:
        result = module.dispatch(args)
        if result is not None:
            return result
    return 2


def main(argv: list[str] | None = None) -> int:
    stdout_target = sys.stdout
    return execute_with_redacted_output(lambda: _dispatch(argv, stdout_target=stdout_target))


if __name__ == "__main__":
    raise SystemExit(main())
