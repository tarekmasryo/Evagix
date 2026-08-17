from __future__ import annotations

from pathlib import Path
from typing import Any

from evagix.model import RepoFacts
from evagix.renderers import DEFAULT_TARGETS
from evagix.utils import format_csv, stable_json
from evagix.validators import doctor_repo, suggest_actions


def render_onboarding_outputs(root: Path, facts: RepoFacts) -> dict[str, str]:
    report = doctor_repo(root, facts)
    payload = _report_payload(root, facts, report.score)
    return {
        ".evagix/summary.md": _summary_md(facts, report.score),
        ".evagix/architecture.md": _architecture_md(facts),
        ".evagix/commands.md": _commands_md(facts),
        ".evagix/environment.md": _environment_md(facts),
        ".evagix/testing.md": _testing_md(facts),
        ".evagix/risks.md": _risks_md(facts),
        ".evagix/first-pr.md": _first_pr_md(root, facts),
        ".evagix/contributor-guide.md": _contributor_guide_md(facts),
        ".evagix/report.json": stable_json(payload) + "\n",
        ".evagix/scorecard.json": stable_json(_scorecard_payload(root, facts, report.score)) + "\n",
    }


def _summary_md(facts: RepoFacts, score: int) -> str:
    return _join(
        [
            "# Repository Summary",
            "",
            f"- Repository: `{facts.root_name}`",
            f"- Readiness score: `{score}/100`",
            f"- Languages: {format_csv(facts.languages)}",
            f"- Frameworks: {format_csv(facts.frameworks)}",
            f"- Backend tools: {format_csv(facts.backend_tools)}",
            f"- Frontend tools: {format_csv(facts.frontend_tools)}",
            f"- AI/Retrieval tools: {format_csv(facts.llm_tools)}",
            f"- ML/data tools: {format_csv(facts.ml_data_tools)}",
            f"- Runtimes: {format_csv(facts.runtimes)}",
            f"- Databases: {format_csv(facts.databases)}",
            f"- Queues/caches: {format_csv(facts.queues)}",
            "",
            "## What this pack is for",
            "",
            "This pack is generated from repository evidence. Use it to onboard developers and AI coding agents before making changes.",
        ]
    )


def _architecture_md(facts: RepoFacts) -> str:
    lines = ["# Architecture", ""]
    lines.append("## Detected shape")
    lines.append("")
    if facts.is_backend_project:
        lines.append("- Backend/API project detected.")
    if facts.is_frontend_project:
        lines.append("- Frontend application or frontend subproject detected.")
    if facts.is_llm_project:
        lines.append("- AI/Retrieval-related tooling detected.")
    if facts.is_ml_project:
        lines.append("- ML/data workflow detected.")
    if facts.is_dashboard_project:
        lines.append("- Dashboard/app framework detected.")
    has_specialized_shape = any(
        [
            facts.is_backend_project,
            facts.is_frontend_project,
            facts.is_llm_project,
            facts.is_ml_project,
            facts.is_dashboard_project,
        ]
    )
    if not has_specialized_shape:
        lines.append("- No specialized architecture profile was detected with high confidence.")
    lines.extend(["", "## Repository map", ""])
    for folder in facts.folders[:40]:
        lines.append(f"- `{folder}/`")
    if facts.subprojects:
        lines.extend(["", "## Subprojects", ""])
        for item in facts.subprojects:
            labels = ", ".join(item.frameworks or item.dev_tools or [item.kind])
            lines.append(f"- `{item.path}`: {labels}; package manager: `{item.package_manager or 'n/a'}`")
    return _join(lines)


def _commands_md(facts: RepoFacts) -> str:
    lines = ["# Commands", ""]
    if not facts.commands:
        lines.append(
            "No high-confidence commands were detected. Inspect the repository manually before running commands."
        )
        return _join(lines)
    for name, command in facts.commands.items():
        evidence = facts.command_sources.get(name)
        source = f" — {evidence.source}, {evidence.confidence}" if evidence else ""
        lines.append(f"- `{name}`: `{command}`{source}")
    return _join(lines)


def _environment_md(facts: RepoFacts) -> str:
    lines = ["# Environment", ""]
    lines.append(f"- Package managers: {format_csv(facts.package_managers)}")
    lines.append(f"- Runtimes: {format_csv(facts.runtimes)}")
    lines.append(f"- Config files: {format_csv(facts.config_files)}")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    if any(name.startswith(".env") for name in facts.config_files) or any(
        "env" in flag.lower() for flag in facts.risk_flags
    ):
        lines.append("- Environment files or runtime config markers were detected. Do not commit secrets.")
    else:
        lines.append(
            "- No committed env example was classified with high confidence. Document required variables if the project needs runtime configuration."
        )
    return _join(lines)


def _testing_md(facts: RepoFacts) -> str:
    lines = ["# Testing & Validation", ""]
    for key in ["test", "lint", "typecheck", "build", "smoke", "doctor", "eval"]:
        if key in facts.commands:
            lines.append(f"- `{key}`: `{facts.commands[key]}`")
    scoped = [
        (key, value)
        for key, value in facts.commands.items()
        if key.endswith(("_test", "_lint", "_typecheck", "_build"))
    ]
    for key, value in scoped:
        lines.append(f"- `{key}`: `{value}`")
    if len(lines) == 2:
        lines.append(
            "No validation commands were detected. Add explicit test/lint/typecheck commands before claiming the project is validated."
        )
    return _join(lines)


def _risks_md(facts: RepoFacts) -> str:
    lines = ["# Risks", ""]
    if not facts.risk_flags and not facts.warnings:
        lines.append("No major risk flags were detected by the static scanner.")
        return _join(lines)
    if facts.risk_flags:
        lines.extend(["## Risk-sensitive areas", ""])
        for flag in facts.risk_flags:
            lines.append(f"- {flag}")
    if facts.warnings:
        lines.extend(["", "## Scanner warnings", ""])
        for warning in facts.warnings:
            lines.append(f"- {warning}")
    return _join(lines)


def _first_pr_md(root: Path, facts: RepoFacts) -> str:
    lines = ["# First PR Suggestions", ""]
    actions = suggest_actions(root, facts)
    for index, action in enumerate(actions[:5], start=1):
        lines.append(f"{index}. {action}")
    lines.extend(
        [
            "",
            "## Safe first-change scope",
            "",
            "- Prefer documentation, tests, config clarification, and small validation improvements.",
            "- Avoid auth, migrations, infra, secrets, dependency upgrades, and destructive cleanup in a first PR unless explicitly scoped.",
        ]
    )
    return _join(lines)


def _contributor_guide_md(facts: RepoFacts) -> str:
    lines = ["# Contributor Guide", ""]
    lines.extend(
        [
            "1. Read the generated agent instructions before editing.",
            "2. Keep changes small and scoped to one problem.",
            "3. Run the detected validation commands that match your change.",
            "4. Report commands that could not be run.",
            "5. Ask for human review before high-risk changes.",
        ]
    )
    if facts.is_llm_project:
        lines.append("6. For AI/Retrieval changes, document prompt/retrieval/eval impact.")
    if facts.is_ml_project:
        lines.append("6. For ML/data changes, document dataset, split, metric, and reproducibility impact.")
    return _join(lines)


def _report_payload(root: Path, facts: RepoFacts, score: int) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "tool": "evagix",
        "repository": facts.root_name,
        "readiness_score": score,
        "languages": facts.languages,
        "frameworks": facts.frameworks,
        "commands": facts.commands,
        "subprojects": [item.__dict__ for item in facts.subprojects],
        "risk_flags": facts.risk_flags,
        "warnings": facts.warnings,
        "generated_targets": {path: (root / path).exists() for path in DEFAULT_TARGETS.values()},
    }


def _scorecard_payload(root: Path, facts: RepoFacts, score: int) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "score": score,
        "checks": {
            "has_tests": "test" in facts.commands or any(key.endswith("_test") for key in facts.commands),
            "has_lint": "lint" in facts.commands or any(key.endswith("_lint") for key in facts.commands),
            "has_typecheck": "typecheck" in facts.commands or any(key.endswith("_typecheck") for key in facts.commands),
            "has_ci": bool(facts.ci_workflows),
            "has_readme": any(
                (root / name).exists() for name in ["README.md", "readme.md", "README.rst", "README.txt"]
            ),
            "has_agent_targets": all((root / path).exists() for path in DEFAULT_TARGETS.values()),
        },
    }


def _join(lines: list[str]) -> str:
    return "\n".join(lines).rstrip() + "\n"
