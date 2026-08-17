from __future__ import annotations

from evagix.classification import format_primary_classification
from evagix.model import RepoFacts
from evagix.rendering.fingerprints import generated_markdown_header
from evagix.utils import format_csv


def render_agent_tasks(facts: RepoFacts) -> dict[str, str]:
    """Render reusable task templates for AI coding agents."""

    return {
        ".agent_tasks/README.md": _task_index(facts),
        ".agent_tasks/bugfix.md": _task_template(
            facts,
            title="Bugfix Task",
            goal="Fix a narrowly scoped defect without broad refactors.",
            allowed=("source files related to the defect", "tests/", "docs/ when behavior or usage changes"),
            forbidden=(
                "unrelated refactors",
                "dependency or CI changes unless explicitly needed",
                "generated context files unless running Evagix sync",
            ),
            validations=("test", "lint", "typecheck", "evagix check"),
            stop=(
                "root cause is unclear",
                "fix requires auth/security/CI changes",
                "tests cannot be run or interpreted",
            ),
        ),
        ".agent_tasks/refactor.md": _task_template(
            facts,
            title="Refactor Task",
            goal="Improve structure while preserving public behavior and interfaces.",
            allowed=(
                "small cohesive modules",
                "tests covering behavior before and after",
                "documentation updates for changed architecture",
            ),
            forbidden=(
                "public API breaks without approval",
                "large framework rewrites",
                "removing tests to make validation pass",
            ),
            validations=("test", "lint", "typecheck", "evagix doctor"),
            stop=(
                "behavioral requirements are ambiguous",
                "migration/data/auth paths are touched",
                "diff becomes broad or hard to review",
            ),
        ),
        ".agent_tasks/add-feature.md": _task_template(
            facts,
            title="Feature Task",
            goal="Add a clearly scoped feature with tests, documentation, and safe rollout boundaries.",
            allowed=(
                "feature-specific source files",
                "tests/",
                "README or docs for public usage",
                "configuration only when required",
            ),
            forbidden=(
                "silent breaking changes",
                "new dependencies without justification",
                "security-sensitive changes without approval",
            ),
            validations=("test", "lint", "typecheck", "evagix readme-audit", "evagix check"),
            stop=(
                "requirements conflict with current architecture",
                "new dependency or runtime service is required",
                "feature touches high-risk paths",
            ),
        ),
        ".agent_tasks/write-tests.md": _task_template(
            facts,
            title="Write Tests Task",
            goal="Add targeted regression or coverage tests without changing production behavior.",
            allowed=("tests/", "fixtures with minimal realistic data", "docs explaining test-only fixtures"),
            forbidden=(
                "production behavior changes",
                "weak assertions that only increase coverage",
                "test deletion or broad skips",
            ),
            validations=("test", "lint"),
            stop=(
                "test requires unknown external services",
                "expected behavior is not inferable from code/docs",
                "secrets or real user data would be needed",
            ),
        ),
        ".agent_tasks/security-review.md": _task_template(
            facts,
            title="Security Review Task",
            goal="Review risk-sensitive changes and produce findings without destructive edits.",
            allowed=("read-only inspection", "small safe tests", "documentation of findings and mitigations"),
            forbidden=(
                "secret rotation",
                "exploit execution",
                "broad cleanup commands",
                "auth/payment/CI changes without approval",
            ),
            validations=("evagix audit", "evagix changed", "evagix doctor"),
            stop=(
                "potential secret exposure is found",
                "auth/CI/deployment paths require modification",
                "external scanning would be needed",
            ),
        ),
    }


def _task_index(facts: RepoFacts) -> str:
    lines = [
        "# Evagix Agent Task Templates",
        "",
        "Use these generated templates to scope AI-assisted repository work before editing files.",
        "Each task lists allowed files, forbidden actions, validation commands, stop conditions, and human review triggers.",
        "",
        "## Available tasks",
        "",
        "- `bugfix.md`",
        "- `refactor.md`",
        "- `add-feature.md`",
        "- `write-tests.md`",
        "- `security-review.md`",
        "",
        "## Repository context",
        "",
        f"- Repository: `{facts.root_name}`",
        f"- Primary type: {format_primary_classification(facts.classification) or 'not detected'}",
        f"- Validation commands: {format_csv(sorted(facts.commands))}",
        f"- Risk flags: {format_csv(facts.risk_flags)}",
        "",
    ]
    return generated_markdown_header(facts) + "\n".join(lines).rstrip() + "\n"


def _task_template(
    facts: RepoFacts,
    *,
    title: str,
    goal: str,
    allowed: tuple[str, ...],
    forbidden: tuple[str, ...],
    validations: tuple[str, ...],
    stop: tuple[str, ...],
) -> str:
    lines = [
        f"# {title}",
        "",
        f"Goal: {goal}",
        "",
        "## Allowed files and activities",
        "",
    ]
    lines.extend(f"- {item}" for item in allowed)
    lines.extend(["", "## Forbidden actions", ""])
    lines.extend(f"- {item}" for item in forbidden)
    lines.extend(["", "## Validation commands", ""])
    for name in validations:
        command = facts.commands.get(name)
        lines.append(
            f"- `{name}`: `{command}`"
            if command
            else f"- `{name}`: inspect repository-specific command before claiming validation"
        )
    lines.extend(["", "## Stop conditions", ""])
    lines.extend(f"- {item}" for item in stop)
    lines.extend(
        [
            "",
            "## Human review triggers",
            "",
            "- CI workflow, dependency, auth, security, migration, deployment, dataset, model artifact, or generated-context changes.",
            "- Any validation command cannot be run or fails for unclear reasons.",
            "- The requested change expands beyond the stated task goal.",
            "",
        ]
    )
    return generated_markdown_header(facts) + "\n".join(lines).rstrip() + "\n"
