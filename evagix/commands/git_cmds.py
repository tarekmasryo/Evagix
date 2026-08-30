from __future__ import annotations

import sys
from pathlib import Path

from evagix.changes import (
    build_changed_report,
    render_changed_github_annotations,
    render_changed_json,
    render_changed_text,
)
from evagix.commands.common import _doctor, _facts, _normalize_root, _targets
from evagix.pr_risk import (
    build_pr_risk_report,
    render_pr_risk_github_annotations,
    render_pr_risk_json,
    render_pr_risk_text,
)
from evagix.terminal import PLAIN_STYLE, TerminalStyle, style_human_text
from evagix.validators import (
    check_repo,
)


def _cmd_changed(
    root: Path,
    base: str,
    head: str,
    output_format: str,
    style: TerminalStyle = PLAIN_STYLE,
) -> int:
    root = _normalize_root(root)
    try:
        facts, _config = _facts(root)
        report = build_changed_report(root, base=base, head=head, commands=facts.commands)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if output_format == "json":
        print(render_changed_json(report), end="")
    elif output_format == "github-annotations":
        print(render_changed_github_annotations(report), end="")
    else:
        print(style_human_text(render_changed_text(report), style), end="")
    return 1 if report.has_high_risk else 0


def _cmd_pr_risk(
    root: Path,
    base: str,
    head: str,
    output_format: str,
    profiles: list[str] | None = None,
    style: TerminalStyle = PLAIN_STYLE,
) -> int:
    root = _normalize_root(root)
    facts, config, doctor = _doctor(root, profiles)
    check = check_repo(
        root,
        facts,
        target_keys=_targets(config, None),
        custom_targets=config.custom_targets,
        fail_on_stale=config.fail_on_stale,
    )
    try:
        report = build_pr_risk_report(root, facts, doctor, check, base=base, head=head)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if output_format == "json":
        print(render_pr_risk_json(report), end="")
    elif output_format == "github-annotations":
        print(render_pr_risk_github_annotations(report), end="")
    else:
        print(style_human_text(render_pr_risk_text(report), style), end="")
    return 1 if report.should_block else 0
