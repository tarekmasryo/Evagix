from __future__ import annotations

import sys
from pathlib import Path

from evagix.commands.common import _facts, _normalize_root, _resolve_cli_output_path, _targets
from evagix.decide import render_decision_json, render_decision_markdown
from evagix.drift import build_drift_report, render_drift_json, render_drift_markdown
from evagix.evidence import render_evidence_payload
from evagix.strict_scoring import build_evidence_ledger
from evagix.terminal import PLAIN_STYLE, TerminalStyle, style_human_text
from evagix.utils import write_text


def _cmd_decide(
    root: Path,
    output_format: str,
    output: str | None,
    force: bool,
    profiles: list[str] | None = None,
    style: TerminalStyle = PLAIN_STYLE,
) -> int:
    root = _normalize_root(root)
    facts, _ = _facts(root, profiles)
    content = render_decision_json(root, facts) if output_format == "json" else render_decision_markdown(root, facts)
    if output:
        output_path = _resolve_cli_output_path(root, output)
        if output_path.exists() and not force:
            print(f"{output} already exists. Re-run with --force to overwrite.", file=sys.stderr)
            return 1
        write_text(output_path, content)
        print(f"Created {output}")
        return 0
    print(style_human_text(content, style) if output_format == "text" else content, end="")
    return 0


def _cmd_drift(
    root: Path,
    output_format: str,
    output: str | None,
    force: bool,
    profiles: list[str] | None = None,
    style: TerminalStyle = PLAIN_STYLE,
) -> int:
    root = _normalize_root(root)
    facts, config = _facts(root, profiles)
    report = build_drift_report(root, facts, target_keys=_targets(config, None))
    content = render_drift_json(report) if output_format == "json" else render_drift_markdown(report)
    if output:
        output_path = _resolve_cli_output_path(root, output)
        if output_path.exists() and not force:
            print(f"{output} already exists. Re-run with --force to overwrite.", file=sys.stderr)
            return 1
        write_text(output_path, content)
        print(f"Created {output}")
        return 0
    print(style_human_text(content, style) if output_format == "text" else content, end="")
    return 0 if report.ok else 1


def _cmd_evidence(root: Path, output: str | None, force: bool, profiles: list[str] | None = None) -> int:
    root = _normalize_root(root)
    facts, _ = _facts(root, profiles)
    payload = build_evidence_ledger(root, facts)
    content = render_evidence_payload(payload)
    if output:
        output_path = _resolve_cli_output_path(root, output)
        if output_path.exists() and not force:
            print(f"{output} already exists. Re-run with --force to overwrite.", file=sys.stderr)
            return 1
        write_text(output_path, content)
        print(f"Created {output}")
        return 0
    if force:
        print("ERROR: --force only applies when --output is provided.", file=sys.stderr)
        return 1
    print(content, end="")
    return 0
