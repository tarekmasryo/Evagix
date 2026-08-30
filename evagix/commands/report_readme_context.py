from __future__ import annotations

import sys
from pathlib import Path

from evagix.commands.common import _facts, _normalize_root, _resolve_cli_output_path, _targets
from evagix.config import CustomTarget
from evagix.context_eval import render_context_eval_json, render_context_eval_markdown
from evagix.model import RepoFacts
from evagix.readme_audit import (
    render_readme_audit_github_annotations,
    render_readme_audit_json,
    render_readme_audit_markdown,
)
from evagix.terminal import PLAIN_STYLE, TerminalStyle, style_human_text
from evagix.utils import write_text


def _cmd_readme_audit(
    root: Path,
    output_format: str,
    output: str | None,
    force: bool,
    profiles: list[str] | None = None,
    strict: bool = False,
    fail_on: str | None = None,
    style: TerminalStyle = PLAIN_STYLE,
) -> int:
    root = _normalize_root(root)
    facts, _ = _facts(root, profiles)
    content = render_readme_audit_output(root, facts, output_format, strict=strict)
    exit_code = readme_audit_exit_code(root, facts, strict=strict, fail_on=fail_on)
    if output:
        output_path = _resolve_cli_output_path(root, output)
        if output_path.exists() and not force:
            print(f"{output} already exists. Re-run with --force to overwrite.", file=sys.stderr)
            return 1
        write_text(output_path, content)
        print(f"Created {output}")
        return exit_code
    print(style_human_text(content, style) if output_format == "text" else content, end="")
    return exit_code


def render_readme_audit_output(root: Path, facts: RepoFacts, output_format: str, *, strict: bool = False) -> str:
    if output_format == "json":
        return render_readme_audit_json(root, facts, strict=strict)
    if output_format == "github-annotations":
        return render_readme_audit_github_annotations(root, facts, strict=strict)
    return render_readme_audit_markdown(root, facts, strict=strict)


def _render_readme_audit_output(root: Path, facts: RepoFacts, output_format: str, *, strict: bool = False) -> str:
    return render_readme_audit_output(root, facts, output_format, strict=strict)


def readme_audit_exit_code(root: Path, facts: RepoFacts, *, strict: bool, fail_on: str | None) -> int:
    from evagix.readme_audit import audit_readme

    report = audit_readme(root, facts, strict=strict)
    if not report.complete and (strict or fail_on):
        return 1
    if not fail_on:
        return 0
    verdicts = {item.verdict for item in report.claims}
    if fail_on == "unsupported" and "unsupported" in verdicts:
        return 1
    if fail_on == "weak-evidence" and verdicts.intersection({"unsupported", "weak_evidence", "waived"}):
        return 1
    if fail_on == "manual-review" and "manual_review_required" in verdicts:
        return 1
    return 0


def _readme_audit_exit_code(root: Path, facts: RepoFacts, *, strict: bool, fail_on: str | None) -> int:
    return readme_audit_exit_code(root, facts, strict=strict, fail_on=fail_on)


def _cmd_eval_context(
    root: Path,
    output_format: str,
    output: str | None,
    force: bool,
    profiles: list[str] | None = None,
    strict: bool = False,
    fail_on: str | None = None,
    fail_under: int | None = None,
    style: TerminalStyle = PLAIN_STYLE,
) -> int:
    root = _normalize_root(root)
    facts, config = _facts(root, profiles)
    target_keys = _targets(config, None)
    content = (
        render_context_eval_json(
            root, facts, strict=strict, target_keys=target_keys, custom_targets=config.custom_targets
        )
        if output_format == "json"
        else render_context_eval_markdown(
            root, facts, strict=strict, target_keys=target_keys, custom_targets=config.custom_targets
        )
    )
    exit_code = context_eval_exit_code(
        root,
        facts,
        strict=strict,
        fail_on=fail_on,
        fail_under=fail_under,
        target_keys=target_keys,
        custom_targets=config.custom_targets,
    )
    if output:
        output_path = _resolve_cli_output_path(root, output)
        if output_path.exists() and not force:
            print(f"{output} already exists. Re-run with --force to overwrite.", file=sys.stderr)
            return 1
        write_text(output_path, content)
        print(f"Created {output}")
        return exit_code
    print(style_human_text(content, style) if output_format == "text" else content, end="")
    return exit_code


def context_eval_exit_code(
    root: Path,
    facts: RepoFacts,
    *,
    strict: bool,
    fail_on: str | None,
    fail_under: int | None,
    target_keys: list[str] | None = None,
    custom_targets: list[CustomTarget] | None = None,
) -> int:
    from evagix.context_eval import evaluate_context

    report = evaluate_context(root, facts, strict=strict, target_keys=target_keys, custom_targets=custom_targets)
    if fail_under is not None and (report.score is None or report.score < fail_under):
        return 1
    if fail_on and strict:
        severity_rank = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        threshold = severity_rank.get(fail_on, 0)
        if threshold >= 3 and any(item.status == "fail" for item in report.checks):
            return 1
        findings = report.findings or []
        if any(severity_rank.get(str(item.get("severity", "")), 0) >= threshold for item in findings):
            return 1
    return 0


def _context_eval_exit_code(
    root: Path,
    facts: RepoFacts,
    *,
    strict: bool,
    fail_on: str | None,
    fail_under: int | None,
    target_keys: list[str] | None = None,
    custom_targets: list[CustomTarget] | None = None,
) -> int:
    return context_eval_exit_code(
        root,
        facts,
        strict=strict,
        fail_on=fail_on,
        fail_under=fail_under,
        target_keys=target_keys,
        custom_targets=custom_targets,
    )
