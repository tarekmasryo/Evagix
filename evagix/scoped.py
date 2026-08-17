from __future__ import annotations

from evagix.model import RepoFacts, Subproject


def scoped_outputs(facts: RepoFacts) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for sub in facts.subprojects:
        if sub.path == ".":
            continue
        outputs[f"{sub.path}/AGENTS.md"] = _subproject_agents_md(facts, sub)
    if "tests" in facts.folders or "test" in facts.folders:
        outputs["tests/AGENTS.md"] = _tests_agents_md(facts)
    if "app" in facts.folders and facts.is_backend_project:
        outputs["app/AGENTS.md"] = _app_agents_md(facts)
    return outputs


def _subproject_agents_md(facts: RepoFacts, sub: Subproject) -> str:
    lines = [
        "# Scoped AI Agent Instructions",
        "",
        f"Scope: `{sub.path}/`",
        f"Parent repository: `{facts.root_name}`",
        f"Kind: `{sub.kind}`",
        f"Package manager: `{sub.package_manager or 'not detected'}`",
        "",
        "## Scoped Commands",
        "",
    ]
    if sub.commands:
        for name, command in sub.commands.items():
            lines.append(f"- `{name}`: `{command}`")
    else:
        lines.append("- No scoped commands detected; inspect this subproject before claiming validation passed.")
    lines.extend(
        [
            "",
            "## Scoped Rules",
            "",
            "- Keep edits inside this subproject unless the task explicitly requires cross-project changes.",
            "- Preserve package-manager and lockfile conventions for this subproject.",
            "- Run scoped validation commands after changing behavior, build config, dependencies, routing, or API clients.",
            "- Do not suppress build/type/lint errors without fixing the root cause or documenting the tradeoff.",
            "",
        ]
    )
    return "\n".join(lines)


def _tests_agents_md(facts: RepoFacts) -> str:
    return """# Scoped AI Agent Instructions

Scope: `tests/`

## Testing Rules

- Add focused regression tests for behavior changes.
- Do not remove tests to make a failing suite pass.
- Keep fixtures small, deterministic, and easy to review.
- Prefer explicit assertions over broad snapshot churn.
"""


def _app_agents_md(facts: RepoFacts) -> str:
    return """# Scoped AI Agent Instructions

Scope: `app/`

## Backend Rules

- Keep API handlers thin and preserve service/repository boundaries.
- Do not change request/response schemas, auth behavior, or error semantics without documenting compatibility impact.
- Keep database session boundaries explicit and avoid hidden global sessions or implicit commits.
- Validate route behavior and startup/config paths after backend changes.
"""
