"""Opt-in advisory comparison of committed CI coverage declarations."""

from __future__ import annotations

import sys
from pathlib import Path

from evagix.coverage_drift import build_coverage_drift_report
from evagix.reports.coverage_drift import (
    render_coverage_drift_annotations,
    render_coverage_drift_json,
    render_coverage_drift_markdown,
    render_coverage_drift_text,
)
from evagix.safety import REPOSITORY_PATH_POLICY
from evagix.terminal import PLAIN_STYLE, TerminalStyle, style_human_text


def _cmd_coverage_drift(
    root: Path, base: str, head: str, output_format: str, style: TerminalStyle = PLAIN_STYLE
) -> int:
    try:
        report = build_coverage_drift_report(REPOSITORY_PATH_POLICY.normalize(root), base=base, head=head)
        if output_format == "json":
            output = render_coverage_drift_json(report)
        elif output_format == "markdown":
            output = render_coverage_drift_markdown(report)
        elif output_format == "github-annotations":
            output = render_coverage_drift_annotations(report)
        else:
            output = style_human_text(render_coverage_drift_text(report), style)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(output, end="")
    return 0 if report.complete else 1
