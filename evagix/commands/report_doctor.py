from __future__ import annotations

import sys
from pathlib import Path

from evagix.commands.common import _facts, _normalize_root, _resolve_cli_output_path, _targets
from evagix.config import EvagixConfig
from evagix.model import RepoFacts
from evagix.utils import write_text
from evagix.validators import (
    DoctorReport,
    apply_config_policy,
    doctor_repo,
    render_doctor_json,
    render_doctor_markdown,
    render_github_annotations,
    render_pr_comment,
    render_sarif,
)

REPORT_DEFAULT_OUTPUTS = {
    "markdown": "EVAGIX_REPORT.md",
    "json": "evagix-report.json",
    "sarif": "evagix.sarif",
    "pr-comment": ".evagix/pr-comment.md",
    "github-annotations": ".evagix/github-annotations.txt",
}


def build_doctor_report(
    root: Path, profiles: list[str] | None = None, *, strict: bool = False
) -> tuple[RepoFacts, EvagixConfig, DoctorReport]:
    facts, config = _facts(root, profiles)
    report = apply_config_policy(
        doctor_repo(
            root,
            facts,
            target_keys=_targets(config, None),
            custom_targets=config.custom_targets,
            fail_on_stale=config.fail_on_stale,
            strict=strict,
            require_onboarding_pack=config.require_onboarding_pack,
        ),
        config,
    )
    return facts, config, report


def _doctor(
    root: Path, profiles: list[str] | None = None, *, strict: bool = False
) -> tuple[RepoFacts, EvagixConfig, DoctorReport]:
    return build_doctor_report(root, profiles, strict=strict)


def _cmd_doctor(
    root: Path,
    output_format: str,
    fail_under: int | None = None,
    profiles: list[str] | None = None,
    strict: bool = False,
) -> int:
    root = _normalize_root(root)
    facts, config, report = build_doctor_report(root, profiles, strict=strict)
    threshold = fail_under if fail_under is not None else config.fail_under
    threshold_failed = report.score < threshold

    if output_format == "json":
        print(render_doctor_json(facts, report, fail_under=threshold))
    elif output_format == "sarif":
        print(render_sarif(root, facts, report))
    elif output_format == "markdown":
        print(render_doctor_markdown(root, facts, report))
    elif output_format == "pr-comment":
        print(render_pr_comment(facts, report))
    elif output_format == "github-annotations":
        print(render_github_annotations(report), end="")
    else:
        _print_doctor_text(report, threshold=threshold, strict=strict, threshold_failed=threshold_failed)
    return 1 if threshold_failed or any(item.severity == "error" for item in report.findings) else 0


def _print_doctor_text(report: DoctorReport, *, threshold: int, strict: bool, threshold_failed: bool) -> None:
    print(f"Evagix Static Evidence Score: {report.score}/100")
    if strict:
        print("Mode: strict evidence-first")
    print(f"Static evidence tier: {report.maturity_level}")
    print(f"Required threshold: {threshold}/100")
    if report.domain_scores:
        print("Score breakdown:")
        for name, domain in report.domain_scores.items():
            print(f"  - {name}: {domain.score}/100 ({domain.status})")
    if report.categories:
        print("Categories:")
        for name, category in report.categories.items():
            print(f"  - {name}: {category.score}/100 ({category.status})")
    if not report.findings:
        print("No issues found.")
    else:
        print("Findings:")
        for item in report.findings:
            print(f"  - [{item.severity}] {item.code}: {item.message}")
    if threshold_failed:
        print(f"ERROR: readiness score is below threshold={threshold}", file=sys.stderr)


def default_report_output(output_format: str) -> str:
    return REPORT_DEFAULT_OUTPUTS.get(output_format, "EVAGIX_REPORT.md")


def render_report_output(root: Path, facts: RepoFacts, report: DoctorReport, output_format: str) -> str:
    if output_format == "json":
        return render_doctor_json(facts, report)
    if output_format == "sarif":
        return render_sarif(root, facts, report)
    if output_format == "pr-comment":
        return render_pr_comment(facts, report)
    if output_format == "github-annotations":
        return render_github_annotations(report)
    return render_doctor_markdown(root, facts, report)


def _default_report_output(output_format: str) -> str:
    return default_report_output(output_format)


def _render_report_output(root: Path, facts: RepoFacts, report: DoctorReport, output_format: str) -> str:
    return render_report_output(root, facts, report, output_format)


def _cmd_report(
    root: Path,
    output: str | None,
    output_format: str,
    force: bool,
    profiles: list[str] | None = None,
) -> int:
    root = _normalize_root(root)
    facts, _, report = build_doctor_report(root, profiles)
    output_name = output or default_report_output(output_format)
    output_path = _resolve_cli_output_path(root, output_name)
    if output_path.exists() and not force:
        print(f"{output_name} already exists. Re-run with --force to overwrite.", file=sys.stderr)
        return 1
    content = render_report_output(root, facts, report, output_format)
    write_text(output_path, content)
    print(f"Created {output_name}")
    return 0
