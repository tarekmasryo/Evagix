from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from evagix.commands.preview_cmds import _cmd_agents, _cmd_context_pack, _cmd_mcp, _cmd_prepare


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    agents_parser = subparsers.add_parser("agents", help="Preview: discover common AI-agent context files.")
    agents_parser.add_argument("path", nargs="?", default=".")
    agents_parser.add_argument("--format", choices=["text", "markdown", "json"], default="text")

    prepare_parser = subparsers.add_parser(
        "prepare", help="Experimental: print a safe repository preparation plan without writing project files."
    )
    prepare_parser.add_argument("path", nargs="?", default=".")
    prepare_parser.add_argument(
        "--plan",
        action="store_true",
        help="Print the preparation plan. This is the only supported mode in this release.",
    )

    context_pack_parser = subparsers.add_parser("context-pack", help="Preview: print a source-grounded context pack.")
    context_pack_parser.add_argument("path", nargs="?", default=".")

    mcp_parser = subparsers.add_parser(
        "mcp", help="Experimental: detect common MCP config files without auditing security."
    )
    mcp_parser.add_argument("path", nargs="?", default=".")
    mcp_parser.add_argument("--format", choices=["text", "json"], default="text")


def dispatch(args: Any) -> int | None:
    if args.command == "agents":
        return _cmd_agents(Path(args.path), output_format=args.format)
    if args.command == "prepare":
        return _cmd_prepare(Path(args.path), plan=args.plan)
    if args.command == "context-pack":
        return _cmd_context_pack(Path(args.path))
    if args.command == "mcp":
        return _cmd_mcp(Path(args.path), output_format=args.format)
    return None
