from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from evagix.config import CustomTarget, EvagixConfig
from evagix.model import RepoFacts
from evagix.report_models import DoctorFinding, DoctorReport
from evagix.repository_intent import is_docs_or_education_repo
from evagix.strict_scoring import doctor_findings_from_evidence, strict_findings
from evagix.utils import has_any_command as _has_any_command
from evagix.utils import has_readme as _has_readme
from evagix.validation.checks import (
    _doctor_onboarding_artifacts,
    _doctor_project_shape,
    _doctor_readme_claim_audit,
    _doctor_readme_consistency,
    _doctor_runtime_and_risks,
)
from evagix.validation.generated_context import check_repo
from evagix.validation.scoring import _format_target_list, _score_report


def doctor_repo(
    root: Path,
    facts: RepoFacts,
    target_keys: list[str] | None = None,
    custom_targets: list[CustomTarget] | None = None,
    *,
    fail_on_stale: bool = True,
    strict: bool = False,
    require_onboarding_pack: bool = False,
) -> DoctorReport:
    findings: list[DoctorFinding] = []

    def add(severity: str, code: str, message: str, penalty: int) -> None:
        findings.append(DoctorFinding(severity=severity, code=code, message=message, penalty=penalty))

    education_repo = is_docs_or_education_repo(root, facts)

    if not facts.languages:
        add("warning", "language-undetected", "No primary language detected with high confidence.", 10)
    if not _has_any_command(facts.commands, "install"):
        if education_repo:
            add(
                "info",
                "missing-install",
                "No install command detected; this is informational for docs/tutorial repositories.",
                0,
            )
        else:
            add("warning", "missing-install", "No install command detected.", 9)
    elif _command_is_only_inferred(facts, "install"):
        add(
            "warning",
            "inferred-install-command",
            "Install command is inferred from weak evidence and is not treated as fully ready.",
            7,
        )
    starter_template_repo = _is_starter_or_template_repo(root, facts)
    if not _has_any_command(facts.commands, "test"):
        if education_repo:
            add(
                "info",
                "missing-test",
                (
                    "No test command detected; this is informational for docs/tutorial repositories "
                    "unless tested claims are made."
                ),
                0,
            )
        elif starter_template_repo and (
            _has_any_command(facts.commands, "typecheck")
            or _has_any_command(facts.commands, "lint")
            or _has_any_command(facts.commands, "build")
        ):
            add(
                "info",
                "missing-test",
                (
                    "No test command detected; this is informational for starter/template repositories "
                    "when other validation commands are available."
                ),
                0,
            )
        else:
            add("warning", "missing-test", "No test command detected.", 16)
    elif _command_is_only_inferred(facts, "test"):
        add(
            "warning",
            "inferred-test-command",
            "Test command is inferred from weak evidence and is not treated as a verified test suite.",
            12,
        )
    if not _has_any_command(facts.commands, "lint"):
        add(
            "info",
            "missing-lint",
            "No lint command detected. Add one if the repository claims lint support or your CI policy requires it.",
            0,
        )
    elif facts.lint_tools and set(facts.lint_tools).issubset({"black", "make", "just"}):
        add(
            "info",
            "formatter-only-lint",
            "Lint command appears formatter-only; consider a semantic linter such as ruff, flake8, pylint, or ESLint.",
            3,
        )
    if not _has_any_command(facts.commands, "typecheck") and (
        "python" in facts.languages or "javascript/typescript" in facts.languages
    ):
        add(
            "info",
            "missing-typecheck",
            "No typecheck command detected. This is a recommendation unless the repository claims typecheck support.",
            0,
        )
    if not facts.ci_workflows:
        add("warning", "missing-ci", "No CI workflow detected.", 10)
    if (facts.is_backend_project or facts.is_frontend_project or facts.is_llm_project) and not _has_readme(root):
        add(
            "warning",
            "missing-readme",
            "No README detected for documenting setup, validation, and architecture assumptions.",
            8,
        )

    check = check_repo(root, facts, target_keys=target_keys, custom_targets=custom_targets, fail_on_stale=fail_on_stale)
    if check.missing_targets:
        add(
            "info",
            "missing-target",
            "Optional generated target(s) are not present: " + _format_target_list(check.missing_targets),
            0,
        )
    if check.stale_targets:
        add(
            "error",
            "generated-context-drift",
            "Generated context exports are stale: " + _format_target_list(check.stale_targets),
            30,
        )
    if check.tampered_targets:
        add(
            "error",
            "tampered-target",
            "Generated context exports were manually modified: " + _format_target_list(check.tampered_targets),
            25,
        )
    if check.unmanaged_targets:
        add(
            "error",
            "generated-context-unmanaged",
            "Generated context targets could not be safely verified as Evagix-managed regular files: "
            + _format_target_list(check.unmanaged_targets),
            25,
        )
    if check.truncated_targets:
        add(
            "error",
            "generated-context-truncated",
            "Generated context exports exceeded the verification read limit: "
            + _format_target_list(check.truncated_targets),
            25,
        )
    if check.invalid_encoding_targets:
        add(
            "error",
            "generated-context-invalid-encoding",
            "Generated context exports are not valid UTF-8: " + _format_target_list(check.invalid_encoding_targets),
            25,
        )

    _doctor_project_shape(root, facts, add)
    _doctor_readme_consistency(root, facts, add)
    if not strict:
        _doctor_readme_claim_audit(root, facts, add)
    _doctor_onboarding_artifacts(root, facts, add, required_by_policy=require_onboarding_pack)
    _doctor_runtime_and_risks(root, facts, add)

    if not facts.dev_tools:
        add("info", "dev-tools-undetected", "No developer tools were classified.", 5)

    if strict:
        findings.extend(doctor_findings_from_evidence(strict_findings(root, facts)))

    return _score_report(findings)


def _command_is_only_inferred(facts: RepoFacts, name: str) -> bool:
    matching = [key for key in facts.commands if key == name or key.endswith(f"_{name}")]
    if not matching:
        return False
    sources = [facts.command_sources.get(key) for key in matching]
    return all(source is not None and source.status == "inferred" for source in sources)


def apply_config_policy(report: DoctorReport, config: EvagixConfig) -> DoctorReport:
    findings: list[DoctorFinding] = []
    for item in report.findings:
        if item.code in config.ignored_findings:
            continue
        severity = config.severity_overrides.get(item.code, item.severity)
        penalty = item.penalty
        if item.code in {"stale-target", "generated-context-drift"} and not config.fail_on_stale:
            severity = "warning"
            penalty = min(penalty, 3)
        findings.append(replace(item, severity=severity, penalty=penalty))
    return _score_report(findings)


def _is_starter_or_template_repo(root: Path, facts: RepoFacts) -> bool:
    name = root.name.lower().replace("_", "-")
    if any(marker in name for marker in ["starter", "template", "boilerplate", "scaffold", "create-"]):
        return True

    if any("template" in key.lower() or "starter" in key.lower() for key in facts.commands):
        return True

    template_markers = [
        root / "template",
        root / "templates",
        root / "starter",
        root / "starters",
        root / "cli" / "template",
        root / "packages" / "template",
    ]
    return any(path.exists() for path in template_markers)
