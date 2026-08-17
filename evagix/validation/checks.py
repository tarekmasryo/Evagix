from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from evagix.evidence import finding_to_doctor_message
from evagix.model import RepoFacts
from evagix.readme_audit import ReadmeStatus, audit_readme, read_readme_source
from evagix.repository_intent import is_docs_or_education_repo, is_library_or_toolkit_repo
from evagix.targets import supported_target_names as _supported_target_names
from evagix.utils import has_any_command, has_readme

FindingAdder = Callable[[str, str, str, int], None]


def _doctor_project_shape(root: Path, facts: RepoFacts, add: FindingAdder) -> None:
    has_tests = (
        (root / "tests").exists()
        or (root / "test").exists()
        or bool(facts.test_paths)
        or _has_any_command(facts, "test")
    )
    education_repo = is_docs_or_education_repo(root, facts)
    library_repo = is_library_or_toolkit_repo(root, facts)
    if facts.is_ml_project:
        if not facts.ml_data_tools:
            add("warning", "ml-tools-undetected", "ML project detected, but ML/data tools were not classified.", 8)
        if not has_tests and not education_repo:
            add("info", "missing-tests-folder", "No tests/ folder detected for an ML/data project.", 5)
        if not _has_readme(root) and not (
            facts.is_backend_project or facts.is_frontend_project or facts.is_llm_project
        ):
            add(
                "warning",
                "missing-readme",
                "No README detected for documenting ML assumptions and usage.",
                8,
            )
    if facts.is_backend_project and not education_repo and not library_repo:
        if not has_tests:
            add(
                "warning",
                "missing-backend-tests",
                "Backend/API project detected, but no tests/ or test command evidence is present.",
                8,
            )
        if facts.databases and not facts.has_database_migrations:
            add("info", "missing-migration-marker", "Database detected, but no migration system was detected.", 4)
    if (
        facts.is_dashboard_project
        and not education_repo
        and not library_repo
        and not facts.commands.get("run")
        and not facts.commands.get("dev")
    ):
        add(
            "warning",
            "missing-app-run",
            "Dashboard framework detected, but no run/dev command was found.",
            8,
        )
    if facts.is_frontend_project:
        if not _has_any_command(facts, "build"):
            add("warning", "missing-frontend-build", "Frontend project detected, but no build command was found.", 7)
        if "typescript" in facts.frontend_tools and not _has_any_command(facts, "typecheck"):
            add(
                "info",
                "missing-frontend-typecheck",
                "TypeScript detected, but no typecheck command was found.",
                4,
            )
        if any("no npm lockfile" in warning.lower() for warning in facts.warnings):
            add(
                "info",
                "frontend-install-not-deterministic",
                "A Node project has no npm lockfile; install command cannot use npm ci deterministically.",
                4,
            )
    if facts.is_llm_project and not any(name in facts.commands for name in ["eval", "doctor", "smoke"]):
        penalty = 0 if education_repo else 2 if library_repo else 5
        add(
            "info",
            "missing-llm-eval",
            "AI/Retrieval tools detected, but no eval/smoke/doctor command was found.",
            penalty,
        )


def _doctor_readme_consistency(root: Path, facts: RepoFacts, add: FindingAdder) -> None:
    readme = _readme_text(root)
    if not readme:
        return
    lower = readme.lower()
    likely_commands = _extract_inline_commands(readme)
    if facts.commands and not _readme_documents_common_commands(lower, likely_commands, facts):
        add(
            "info",
            "readme-command-gap",
            "README does not document detected setup/test/run commands; usage docs may be stale or incomplete.",
            3,
        )
    for suspicious in sorted(likely_commands):
        if suspicious.startswith(("npm ", "pnpm ", "yarn ")) and "javascript/typescript" not in facts.languages:
            add(
                "info",
                "readme-possible-stale-node-command",
                f"README mentions `{suspicious}` but no Node project was detected.",
                3,
            )
            break


def _doctor_readme_claim_audit(root: Path, facts: RepoFacts, add: FindingAdder) -> None:
    report = audit_readme(root, facts)
    for finding in report.findings:
        severity = "warning" if finding.severity in {"critical", "high", "medium"} else "info"
        penalty = 8 if finding.severity in {"critical", "high"} else 4 if finding.severity == "medium" else 2
        add(severity, finding.id, finding_to_doctor_message(finding), penalty)
    if not report.claims:
        return
    if report.unsupported:
        phrases = ", ".join(sorted({item.phrase for item in report.unsupported})[:3])
        add(
            "warning",
            "readme-unsupported-claims",
            f"README contains unsupported claim evidence: {phrases}.",
            8,
        )
    review_items = [*report.partial, *report.waived]
    if review_items:
        phrases = ", ".join(sorted({item.phrase for item in review_items})[:3])
        add(
            "info",
            "readme-partial-claims",
            f"README contains partially supported or waived claims that may need narrower wording: {phrases}.",
            3,
        )


def _doctor_onboarding_artifacts(
    root: Path, facts: RepoFacts, add: FindingAdder, *, required_by_policy: bool = False
) -> None:
    if not required_by_policy:
        return
    required = [
        root / ".evagix" / "summary.md",
        root / ".evagix" / "report.json",
        root / ".evagix" / "scorecard.json",
    ]
    if (root / "AGENTS.md").exists() and not all(path.exists() for path in required):
        add(
            "info",
            "missing-onboarding-pack",
            "Generated agent files exist and policy.require_onboarding_pack=true, but the .evagix onboarding pack is missing or incomplete.",
            2,
        )


def _readme_documents_common_commands(lower_readme: str, inline_commands: set[str], facts: RepoFacts) -> bool:
    common_names = {
        "install",
        "test",
        "lint",
        "typecheck",
        "build",
        "run",
        "dev",
        "format",
        "smoke",
        "doctor",
        "eval",
    }
    commands = [
        command
        for name, command in facts.commands.items()
        if name in common_names or any(name.endswith(f"_{suffix}") for suffix in common_names)
    ]
    if not commands:
        return True
    for command in commands:
        normalized = command.strip().lower()
        if not normalized:
            continue
        if normalized in lower_readme or normalized in inline_commands:
            return True
        parts = normalized.split()
        if len(parts) >= 2:
            compact = " ".join(parts[:2])
            if compact in lower_readme or compact in inline_commands:
                return True
        if normalized.startswith("cd ") and "&&" in normalized:
            tail = normalized.split("&&", 1)[1].strip()
            if tail in lower_readme or tail in inline_commands:
                return True
    return False


def _doctor_runtime_and_risks(root: Path, facts: RepoFacts, add: FindingAdder) -> None:
    if facts.risk_flags:
        add(
            "info",
            "risk-flags-detected",
            f"Risk-sensitive folders/configs detected: {len(facts.risk_flags)} item(s).",
            2,
        )
    if (
        facts.databases
        and "docker-compose" not in facts.container_platforms
        and not facts.has_database_migrations
        and not is_docs_or_education_repo(root, facts)
        and not is_library_or_toolkit_repo(root, facts)
    ):
        add(
            "info",
            "database-runtime-unclear",
            "Database dependency detected, but runtime/migration path is unclear.",
            4,
        )
    if any((root / name).exists() for name in [".env", ".env.local", ".env.production"]):
        add(
            "warning",
            "env-file-present",
            "Local .env file detected; ensure it is ignored and never committed.",
            8,
        )


def _has_any_command(facts: RepoFacts, name: str) -> bool:
    return has_any_command(facts.commands, name)


def _has_readme(root: Path) -> bool:
    return has_readme(root)


def _readme_text(root: Path) -> str:
    source = read_readme_source(root)
    return source.text if source.status == ReadmeStatus.COMPLETE else ""


def _extract_inline_commands(text: str) -> set[str]:
    commands = set()
    for match in re.finditer(r"`([^`]+)`", text):
        command = match.group(1).strip()
        if command.startswith(("python ", "pytest", "ruff", "make ", "npm ", "pnpm ", "yarn ", "docker ")):
            commands.add(command)
    return commands


def supported_target_names() -> str:
    return _supported_target_names()
