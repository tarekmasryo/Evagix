"""Opt-in advisory reference inspection, separate from changed-file risk gates."""

from __future__ import annotations

import sys
from pathlib import Path

from evagix.reference_drift import (
    build_reference_drift_report,
    render_reference_drift_github_annotations,
    render_reference_drift_json,
    render_reference_drift_text,
)
from evagix.safety import REPOSITORY_PATH_POLICY
from evagix.terminal import PLAIN_STYLE, TerminalStyle, style_human_text


def _cmd_reference_drift(
    root: Path,
    base: str,
    head: str,
    output_format: str,
    style: TerminalStyle = PLAIN_STYLE,
) -> int:
    try:
        report = build_reference_drift_report(REPOSITORY_PATH_POLICY.normalize(root), base=base, head=head)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if output_format == "json":
        print(render_reference_drift_json(report), end="")
    elif output_format == "github-annotations":
        print(render_reference_drift_github_annotations(report), end="")
    else:
        print(style_human_text(render_reference_drift_text(report), style), end="")
    return 0 if report.complete else 1
