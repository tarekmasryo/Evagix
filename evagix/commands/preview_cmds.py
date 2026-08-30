from __future__ import annotations

import sys
from pathlib import Path

from evagix.commands.agents import run_agents
from evagix.commands.common import _normalize_existing_root
from evagix.commands.context_pack import run_context_pack
from evagix.commands.mcp import run_mcp
from evagix.commands.prepare import render_prepare_plan
from evagix.terminal import PLAIN_STYLE, TerminalStyle, style_human_text


def _cmd_agents(root: Path, output_format: str, style: TerminalStyle = PLAIN_STYLE) -> int:
    root = _normalize_existing_root(root)
    rendered, exit_code = run_agents(root, output_format=output_format)
    print(style_human_text(rendered, style) if output_format == "text" else rendered, end="")
    return exit_code


def _cmd_prepare(root: Path, plan: bool, style: TerminalStyle = PLAIN_STYLE) -> int:
    root = _normalize_existing_root(root)
    if not plan:
        print("prepare is experimental and only supports --plan. No files were written.", file=sys.stderr)
        return 2
    print(style_human_text(render_prepare_plan(root), style), end="")
    return 0


def _cmd_context_pack(root: Path) -> int:
    root = _normalize_existing_root(root)
    print(run_context_pack(root), end="")
    return 0


def _cmd_mcp(root: Path, output_format: str, style: TerminalStyle = PLAIN_STYLE) -> int:
    root = _normalize_existing_root(root)
    rendered, exit_code = run_mcp(root, output_format=output_format)
    print(style_human_text(rendered, style) if output_format == "text" else rendered, end="")
    return exit_code
