from __future__ import annotations

import argparse
from typing import Protocol

from evagix import __version__
from evagix.commands import core_cli, fix_cli, git_cli, inspect_cli, preview_cli, readiness_cli
from evagix.security.output import execute_with_redacted_output


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
    subparsers = parser.add_subparsers(dest="command", required=True)
    for module in COMMAND_MODULES:
        module.register(subparsers)
    return parser


def _dispatch(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    for module in COMMAND_MODULES:
        result = module.dispatch(args)
        if result is not None:
            return result
    return 2


def main(argv: list[str] | None = None) -> int:
    return execute_with_redacted_output(lambda: _dispatch(argv))


if __name__ == "__main__":
    raise SystemExit(main())
