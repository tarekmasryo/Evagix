"""Opt-in advisory inspection of committed script instructions."""

from __future__ import annotations

import sys
from pathlib import Path

from evagix.safety import REPOSITORY_PATH_POLICY
from evagix.script_drift import (
    build_script_drift_report,
    render_script_drift_github_annotations,
    render_script_drift_json,
    render_script_drift_markdown,
    render_script_drift_text,
)
from evagix.terminal import PLAIN_STYLE, TerminalStyle, style_human_text


def _cmd_script_drift(
    root: Path,
    base: str,
    head: str,
    output_format: str,
    style: TerminalStyle = PLAIN_STYLE,
) -> int:
    try:
        report = build_script_drift_report(REPOSITORY_PATH_POLICY.normalize(root), base=base, head=head)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if output_format == "json":
        output = render_script_drift_json(report)
    elif output_format == "markdown":
        try:
            output = render_script_drift_markdown(report)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    elif output_format == "github-annotations":
        output = render_script_drift_github_annotations(report)
    else:
        output = style_human_text(render_script_drift_text(report), style)
    print(output, end="")
    return 0 if report.complete else 1
