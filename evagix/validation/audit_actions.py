from __future__ import annotations

from pathlib import Path

from evagix.model import RepoFacts


def suggest_actions(root: Path, facts: RepoFacts) -> list[str]:
    from evagix.validation.doctor import doctor_repo

    report = doctor_repo(root, facts)
    actions: list[str] = []
    codes = {item.code for item in report.findings}
    if "missing-ci" in codes:
        actions.append("Run `evagix init-ci . --fail-under 80` and commit the workflow after review.")
    if "missing-lint" in codes:
        actions.append("Add an explicit lint command, then regenerate Evagix files.")
    if "missing-typecheck" in codes and ("python" in facts.languages or "javascript/typescript" in facts.languages):
        actions.append("Add a typecheck command such as `mypy .`, `pyright`, or a scoped frontend typecheck script.")
    if "missing-llm-eval" in codes:
        actions.append(
            "Add a small AI/Retrieval smoke or eval command covering retrieval, grounding, and provider config."
        )
    if any(item.code in {"stale-target", "generated-context-drift"} for item in report.findings):
        actions.append("Run `evagix compile .` to refresh stale generated instruction files.")
    if facts.is_frontend_project and any(_uses_plain_npm_install(cmd) for cmd in facts.commands.values()):
        actions.append("Commit a Node lockfile or switch to a deterministic package manager command.")
    if not actions:
        actions.append("Repository looks ready; keep `evagix check` and `evagix doctor --fail-under 80` in CI.")
    return actions


def _uses_plain_npm_install(command: str) -> bool:
    """Return True only for npm install commands, not pnpm install."""
    normalized = " ".join(command.strip().split())
    segments = [segment.strip() for segment in normalized.split("&&")]
    return any(segment == "npm install" or segment.startswith("npm install ") for segment in segments)
