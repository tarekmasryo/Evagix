from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from evagix.model import RepoFacts
from evagix.readme_audit import ReadmeStatus, audit_readme
from evagix.security.output import redacted_text_output
from evagix.utils import stable_json
from evagix.validators import DoctorReport, doctor_repo, suggest_actions


@dataclass(frozen=True)
class RepoDecision:
    readiness: str
    risk_level: str
    next_best_actions: list[str]
    safe_for_ai_agents: list[str]
    needs_human_approval: list[str]
    hardening_steps: list[str]
    rationale: list[str]


def decide_repo(root: Path, facts: RepoFacts) -> RepoDecision:
    doctor = doctor_repo(root, facts)
    readme = audit_readme(root, facts)
    risk_level = _risk_level(facts, doctor.score, readme.score)
    readiness = _readiness(doctor.score, risk_level)
    actions = _prioritized_actions(facts, doctor, suggest_actions(root, facts))[:5]
    hardening = _hardening_steps(facts, doctor.score, readme.score)
    rationale = [f"Doctor score: {doctor.score}/100", f"README claim audit score: {readme.score}/100"]
    if readme.status in {ReadmeStatus.TRUNCATED, ReadmeStatus.INVALID_UTF8, ReadmeStatus.READ_ERROR}:
        readiness = "not-ready"
        risk_level = "high"
        hardening.insert(0, _readme_hardening_step(readme.status))
        hardening = hardening[:3]
        rationale.append(f"README audit incomplete: {readme.status.value}.")
    elif readme.status in {ReadmeStatus.MISSING, ReadmeStatus.EMPTY}:
        readiness = "not-ready"
        rationale.append(f"README status: {readme.status.value}.")
    if facts.risk_flags:
        rationale.append(f"Risk-sensitive markers detected: {len(facts.risk_flags)}")
    if not facts.ci_workflows:
        rationale.append("No CI workflow detected.")
    return RepoDecision(
        readiness=readiness,
        risk_level=risk_level,
        next_best_actions=actions,
        safe_for_ai_agents=_safe_tasks(facts),
        needs_human_approval=_approval_gates(facts),
        hardening_steps=hardening,
        rationale=rationale,
    )


@redacted_text_output
def render_decision_markdown(root: Path, facts: RepoFacts) -> str:
    decision = decide_repo(root, facts)
    lines = [
        "# Repo Decision Plan",
        "",
        f"- Repository: `{facts.root_name}`",
        f"- Agent readiness: `{decision.readiness}`",
        f"- Risk level: `{decision.risk_level}`",
        "",
        "## Next best actions",
        "",
    ]
    for index, action in enumerate(decision.next_best_actions, start=1):
        lines.append(f"{index}. {action}")
    lines.extend(["", "## Safe for AI agents", ""])
    for item in decision.safe_for_ai_agents:
        lines.append(f"- {item}")
    lines.extend(["", "## Requires human approval", ""])
    for item in decision.needs_human_approval:
        lines.append(f"- {item}")
    lines.extend(["", "## Top hardening steps", ""])
    for index, item in enumerate(decision.hardening_steps, start=1):
        lines.append(f"{index}. {item}")
    lines.extend(["", "## Rationale", ""])
    for item in decision.rationale:
        lines.append(f"- {item}")
    return "\n".join(lines).rstrip() + "\n"


def render_decision_json(root: Path, facts: RepoFacts) -> str:
    return (
        stable_json(
            {
                "schema_version": "1.0",
                "tool": "evagix",
                "repository": facts.root_name,
                "decision": asdict(decide_repo(root, facts)),
            }
        )
        + "\n"
    )


def _readiness(score: int, risk_level: str) -> str:
    if score >= 85 and risk_level in {"low", "medium"}:
        return "ready"
    if score >= 65:
        return "limited"
    return "not-ready"


def _readme_hardening_step(status: ReadmeStatus) -> str:
    if status == ReadmeStatus.TRUNCATED:
        return "Make the README fully auditable by reducing its size or explicitly raising the reviewed scan limit."
    if status == ReadmeStatus.INVALID_UTF8:
        return "Encode the README as valid UTF-8, then rerun the README and repository audits."
    return "Restore safe README read access, then rerun the README and repository audits."


def _risk_level(facts: RepoFacts, doctor_score: int, readme_score: int) -> str:
    high_risk_signals = 0
    if facts.has_database_migrations or facts.databases:
        high_risk_signals += 1
    if facts.risk_flags:
        high_risk_signals += 1
    if facts.is_llm_project:
        high_risk_signals += 1
    if doctor_score < 60 or readme_score < 60:
        high_risk_signals += 1
    if high_risk_signals >= 3:
        return "high"
    if high_risk_signals >= 1:
        return "medium"
    return "low"


def _prioritized_actions(facts: RepoFacts, doctor: DoctorReport, base_actions: list[str]) -> list[str]:
    actions: list[str] = []
    seen_categories: set[str] = set()
    codes = {item.code for item in doctor.findings}
    has_agent_context_issue = bool(
        {
            "missing-target",
            "stale-target",
            "generated-context-drift",
            "tampered-target",
            "generated-context-unmanaged",
        }.intersection(codes)
    )

    if "generated-context-unmanaged" in codes:
        _append_action(
            actions,
            seen_categories,
            "Move the user-owned configured target or review and regenerate it explicitly before running `evagix check .` again.",
        )
    elif {"stale-target", "generated-context-drift", "tampered-target"}.intersection(codes):
        _append_action(
            actions,
            seen_categories,
            "Run `evagix compile . --force`, then `evagix check .` to refresh stale or tampered generated instruction files.",
        )
    elif "missing-target" in codes:
        _append_action(
            actions,
            seen_categories,
            "Run `evagix compile .`, then `evagix check .` to generate missing instruction files.",
        )

    if "missing-install" in codes:
        _append_action(
            actions,
            seen_categories,
            "Document an explicit install/setup command before asking AI agents to modify the repo.",
        )
    if "missing-test" in codes:
        _append_action(
            actions, seen_categories, "Add an explicit test or smoke command before relying on AI-assisted changes."
        )
    if "missing-lint" in codes:
        _append_action(actions, seen_categories, "Add an explicit lint command for safe automated review.")

    if facts.is_ml_project:
        _append_action(
            actions,
            seen_categories,
            "Add a dashboard/model smoke check that preserves datasets, splits, metrics, and model artifacts.",
        )
    if facts.is_llm_project:
        _append_action(
            actions,
            seen_categories,
            "Add a small AI/Retrieval smoke or eval command covering retrieval, grounding, and provider config.",
        )
    if facts.is_backend_project:
        _append_action(
            actions,
            seen_categories,
            "Document a backend smoke path for health/readiness, auth-sensitive routes, and migration-safe changes.",
        )
    if facts.is_frontend_project:
        _append_action(
            actions, seen_categories, "Document the build/typecheck command expected after UI or route changes."
        )

    for action in base_actions:
        if _is_ready_message(action) and (doctor.score < 80 or has_agent_context_issue):
            continue
        _append_action(actions, seen_categories, action)
    return actions


def _append_action(actions: list[str], seen_categories: set[str], action: str) -> None:
    category = _action_category(action)
    normalized = _normalize_action(action)
    if category in seen_categories or normalized in {_normalize_action(existing) for existing in actions}:
        return
    actions.append(action)
    seen_categories.add(category)


def _is_ready_message(action: str) -> bool:
    return "repository looks ready" in action.lower()


def _normalize_action(action: str) -> str:
    return " ".join(action.lower().replace("`", "").split())


def _action_category(action: str) -> str:
    normalized = _normalize_action(action)
    if "evagix compile" in normalized or "generated instruction" in normalized or "generated target" in normalized:
        return "context-governance"
    if "install/setup" in normalized or "install command" in normalized:
        return "install"
    if "test" in normalized or "smoke" in normalized:
        if "dashboard/model" in normalized or "ml/dashboard" in normalized:
            return "ml-smoke"
        if "llm/rag" in normalized or "retrieval" in normalized or "grounding" in normalized:
            return "llm-eval"
        if "backend" in normalized or "health/readiness" in normalized:
            return "backend-smoke"
        return "test"
    if "lint" in normalized:
        return "lint"
    if "typecheck" in normalized or "pyright" in normalized or "mypy" in normalized:
        return "typecheck"
    if "build" in normalized or "ui" in normalized or "route" in normalized:
        return "frontend-build"
    if "init-ci" in normalized or " ci" in normalized:
        return "ci"
    if "lockfile" in normalized or "package manager" in normalized:
        return "lockfile"
    if "readme" in normalized or "claim" in normalized:
        return "readme"
    if _is_ready_message(action):
        return "ready"
    return normalized


def _safe_tasks(facts: RepoFacts) -> list[str]:
    tasks = [
        "Documentation updates based on existing evidence.",
        "Adding or improving tests without changing production behavior.",
        "Small refactors that preserve public APIs and behavior.",
        "Regenerating evagix-generated instruction files.",
    ]
    if facts.is_frontend_project:
        tasks.append("Small UI copy or component-local changes after running build/typecheck.")
    if facts.is_ml_project:
        tasks.append("Non-destructive notebook/report cleanup that preserves data, splits, and metrics.")
    return tasks


def _approval_gates(facts: RepoFacts) -> list[str]:
    gates = [
        "Deleting files, generated artifacts, datasets, or lockfiles.",
        "Adding/upgrading dependencies or changing package managers.",
        "Changing secrets, environment variable names, auth, permissions, or tokens.",
        "Changing Docker, CI, deployment, or infrastructure behavior.",
    ]
    if facts.databases or facts.has_database_migrations:
        gates.append("Database schema, migration, seed, or destructive data changes.")
    if facts.is_llm_project:
        gates.append("Prompt, retrieval, embeddings, reranking, model, or provider behavior changes.")
    if facts.is_ml_project:
        gates.append("Dataset, label, split, metric, preprocessing, or model artifact changes.")
    return gates


def _hardening_steps(facts: RepoFacts, doctor_score: int, readme_score: int) -> list[str]:
    steps: list[str] = []
    if "test" not in facts.commands and not any(key.endswith("_test") for key in facts.commands):
        steps.append("Add an explicit test command and at least one smoke/regression test.")
    if facts.is_ml_project and not any(name in facts.commands for name in ["smoke", "eval"]):
        steps.append("Add a deterministic ML/dashboard smoke check for app loading and metric/artifact preservation.")
    if facts.is_llm_project and not any(name in facts.commands for name in ["smoke", "eval", "doctor"]):
        steps.append("Add a deterministic AI/Retrieval smoke or eval command for retrieval and grounding.")
    if "lint" not in facts.commands and not any(key.endswith("_lint") for key in facts.commands):
        steps.append("Add an explicit lint command for safe automated review.")
    if not facts.ci_workflows:
        steps.append("Add a CI workflow that runs tests, lint, `evagix check`, and `evagix doctor`.")
    if readme_score < 90:
        steps.append("Fix unsupported or partially supported README claims.")
    if not steps:
        steps.append("Keep generated agent files current and enforce `evagix check` in CI.")
    return steps[:3]
