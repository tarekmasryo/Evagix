"""Opt-in advisory review of committed Python test changes."""

from __future__ import annotations

import sys
from pathlib import Path

from evagix.reports.test_changes import (
    render_test_changes_annotations,
    render_test_changes_json,
    render_test_changes_markdown,
    render_test_changes_text,
)
from evagix.safety import REPOSITORY_PATH_POLICY
from evagix.terminal import PLAIN_STYLE, TerminalStyle, style_human_text
from evagix.test_changes import build_test_changes_report


def _cmd_test_changes(root: Path, base: str, head: str, output_format: str, style: TerminalStyle = PLAIN_STYLE) -> int:
    try:
        report = build_test_changes_report(REPOSITORY_PATH_POLICY.normalize(root), base=base, head=head)
        if output_format == "json":
            output = render_test_changes_json(report)
        elif output_format == "markdown":
            output = render_test_changes_markdown(report)
        elif output_format == "github-annotations":
            output = render_test_changes_annotations(report)
        else:
            output = style_human_text(render_test_changes_text(report), style)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(output, end="")
    return 0 if report.complete else 1
