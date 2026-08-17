from __future__ import annotations

from evagix.model import RepoFacts


def _coding_style(facts: RepoFacts) -> str:
    rules = [
        "## Coding Style",
        "",
        "- Prefer small, focused changes over broad rewrites.",
        "- Preserve the existing public API unless the task explicitly asks for a breaking change.",
        "- Do not introduce new dependencies unless the benefit clearly outweighs maintenance and security cost.",
        "- Keep generated, vendored, lock, migration, dataset, and model artifact files stable unless the task specifically requires updating them.",
    ]
    if "python" in facts.languages:
        rules.extend(
            [
                "- For Python, prefer typed, explicit functions and avoid hidden global state.",
                "- Keep imports organized and avoid unused compatibility shims.",
            ]
        )
    if "javascript/typescript" in facts.languages:
        rules.extend(
            [
                "- For JavaScript/TypeScript, preserve strict type checks and avoid suppressing type errors without justification.",
                "- Keep package-manager usage consistent with the detected lockfile and subproject path.",
            ]
        )
    if facts.is_dashboard_project or facts.is_frontend_project:
        rules.append("- Preserve user-facing flows and avoid UI rewrites that are not required by the task.")
    return "\n".join(rules)


def _testing_policy(facts: RepoFacts) -> str:
    lines = ["## Testing Policy", ""]
    if "test" in facts.commands:
        lines.append(f"- Run `{facts.commands['test']}` after behavior changes.")
    else:
        scoped_tests = [(k, v) for k, v in facts.commands.items() if k.endswith("_test")]
        if scoped_tests:
            for key, command in scoped_tests:
                lines.append(f"- Run `{command}` for `{key.removesuffix('_test')}` behavior changes.")
        else:
            lines.append("- No test command was detected; inspect the repository before claiming tests pass.")
    if "lint" in facts.commands:
        lines.append(f"- Run `{facts.commands['lint']}` after style or structural changes.")
    else:
        scoped_lints = [v for k, v in facts.commands.items() if k.endswith("_lint")]
        for command in scoped_lints[:3]:
            lines.append(f"- Run `{command}` after style changes in the matching subproject.")
    if "typecheck" in facts.commands:
        lines.append(f"- Run `{facts.commands['typecheck']}` after API or type-sensitive changes.")
    else:
        scoped_typechecks = [v for k, v in facts.commands.items() if k.endswith("_typecheck")]
        for command in scoped_typechecks[:3]:
            lines.append(f"- Run `{command}` after type-sensitive changes in the matching subproject.")
    if facts.is_ml_project:
        lines.append(
            "- For model or preprocessing changes, validate metrics on the documented split before reporting results."
        )
    if facts.is_backend_project:
        lines.append(
            "- For API changes, validate route behavior, request/response schemas, and backward compatibility."
        )
    lines.append("- Report any commands you could not run and the reason.")
    return "\n".join(lines)


def _change_review_policy(facts: RepoFacts) -> str:
    lines = [
        "## Change Review Policy",
        "",
        "- Prefer minimal diffs that solve the requested problem without unrelated refactors.",
        "- Before editing, inspect existing patterns, entrypoints, tests, and configuration files.",
        "- After editing, summarize changed files, validation commands run, and any commands that could not be run.",
    ]
    if facts.is_backend_project:
        lines.append("- For API changes, list affected routes, schemas, auth behavior, and compatibility risks.")
    if facts.is_frontend_project:
        lines.append("- For UI changes, state affected screens/components and whether build/typecheck was run.")
    if facts.is_llm_project:
        lines.append("- For AI/Retrieval behavior changes, state prompt/retrieval/index impact and any eval evidence.")
    if facts.is_ml_project:
        lines.append("- For ML/data changes, state dataset/split/metric impact and reproducibility assumptions.")
    return "\n".join(lines)


def _safety_policy(facts: RepoFacts) -> str:
    lines = ["## Safety Rules", ""]
    lines.extend(
        [
            "- Use read-only inspection before destructive operations.",
            "- Do not delete user data, migrations, secrets, logs, datasets, model artifacts, "
            "generated reports, or experiment runs unless explicitly requested.",
            "- Do not rotate credentials, rewrite git history, or force-push without explicit approval.",
            "- Do not run broad cleanup commands against the repository root.",
            "- Do not install or execute unknown global tools without clear justification.",
            "- Prefer deterministic commands and pinned versions for dependency changes.",
            "- Review dependency, lockfile, and lifecycle-script changes as supply-chain sensitive.",
        ]
    )
    if facts.databases:
        lines.append("- Treat database migrations and schema changes as high-risk; explain impact before editing them.")
    if "docker-compose" in facts.runtimes:
        lines.append("- Treat Docker volume deletion and container cleanup as destructive unless explicitly scoped.")
    if facts.is_ml_project:
        lines.append(
            "- Treat dataset edits, artifact regeneration, and metric changes as high-risk because they affect reproducibility."
        )
    if facts.is_llm_project:
        lines.append(
            "- Treat prompt, retrieval, index, and model changes as behavior-changing even when code diffs look small."
        )
    return "\n".join(lines)


def _forbidden_actions(facts: RepoFacts) -> str:
    lines = [
        "## Forbidden Actions",
        "",
        "- Do not commit secrets, tokens, API keys, private certificates, or local `.env` files.",
        "- Do not remove tests to make a failing suite pass.",
        "- Do not silence lint/type errors without fixing the underlying issue or documenting the tradeoff.",
        "- Do not replace the architecture with a larger framework unless the task explicitly requires it.",
        "- Do not claim validation passed unless the command was actually run successfully.",
    ]
    for rule in facts.custom_forbidden_actions:
        lines.append(f"- {rule}")
    return "\n".join(lines)


def _evidence(facts: RepoFacts) -> str:
    lines = ["## Evidence Used", ""]
    if not facts.command_sources:
        lines.append("No command evidence was detected.")
        return "\n".join(lines)
    for name, evidence in facts.command_sources.items():
        score = getattr(evidence, "confidence_score", None)
        score_text = f", score={score:.2f}" if isinstance(score, float) else ""
        location = f", path=`{evidence.path}`" if getattr(evidence, "path", "") else ""
        lines.append(
            f"- `{name}` from `{evidence.source}`: {evidence.detail} ({evidence.confidence}{score_text}{location})"
        )
    return "\n".join(lines)


def _warnings(facts: RepoFacts) -> str:
    lines = ["## Evagix Warnings", ""]
    for warning in facts.warnings:
        lines.append(f"- {warning}")
    return "\n".join(lines)


def _custom_rules(facts: RepoFacts) -> str:
    rules = facts.custom_rules
    if not rules:
        return ""
    lines = ["## Repository-Specific Rules", ""]
    for rule in rules:
        lines.append(f"- {rule}")
    return "\n".join(lines)
