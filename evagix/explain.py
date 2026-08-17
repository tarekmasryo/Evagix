from __future__ import annotations

from dataclasses import dataclass

from evagix.rules.registry import get_rule


@dataclass(frozen=True)
class Explanation:
    code: str
    title: str
    meaning: str
    why_it_matters: str
    recommended_fix: str
    severity_hint: str = "info"


EXPLANATIONS: dict[str, Explanation] = {
    "missing-ci": Explanation(
        "missing-ci",
        "No CI workflow detected",
        "The repository has no detected GitHub Actions/GitLab/CircleCI workflow.",
        "Generated agent instructions can drift when important files change unless check/doctor run in CI.",
        "Run `evagix init-ci . --fail-under 80`, review the workflow, then commit it.",
        "warning",
    ),
    "missing-typecheck": Explanation(
        "missing-typecheck",
        "No typecheck command detected",
        "The scanner did not find mypy, pyright, tsc, or an equivalent typecheck command.",
        "AI coding agents often make type-shaped mistakes that unit tests may not catch.",
        "Add a typecheck command such as `mypy .`, `pyright`, or a scoped frontend script, then regenerate context.",
        "info",
    ),
    "missing-llm-eval": Explanation(
        "missing-llm-eval",
        "No AI/Retrieval smoke or eval command detected",
        "AI/Retrieval libraries were detected, but no eval/smoke/doctor command was found.",
        "Prompt, retrieval, chunking, embedding, and index changes can alter product behavior without failing normal tests.",
        "Add a small deterministic eval/smoke command and declare it in `evagix.toml` under `[commands]`.",
        "info",
    ),
    "generated-context-drift": Explanation(
        "generated-context-drift",
        "Generated context exports are stale",
        "One or more generated Evagix context files no longer match the current repository fingerprint.",
        "Coding agents may follow outdated commands, repository facts, architecture notes, or safety constraints.",
        "Run `evagix compile .`, inspect the diff, then commit the refreshed generated context exports.",
        "error",
    ),
    "stale-target": Explanation(
        "stale-target",
        "Generated instruction file is stale",
        "At least one generated file fingerprint no longer matches the current repository facts.",
        "Coding agents may follow outdated commands, architecture rules, or safety constraints.",
        "Run `evagix compile .`, inspect the diff, then commit the refreshed generated files.",
        "error",
    ),
    "missing-lint": Explanation(
        "missing-lint",
        "No lint command detected",
        "The repository has no obvious lint command for coding agents to run after style or structural edits.",
        "Without linting, generated edits may introduce style, import, or static quality issues.",
        "Add a lint command such as `ruff check .`, `eslint`, `golangci-lint run`, or a Makefile target.",
        "warning",
    ),
    "frontend-install-not-deterministic": Explanation(
        "frontend-install-not-deterministic",
        "Frontend install is not deterministic",
        "A Node project was detected without a lockfile, so the tool fell back to `npm install`.",
        "Non-deterministic installs make AI-assisted validation harder to reproduce.",
        "Commit a lockfile or switch to a deterministic package manager command.",
        "info",
    ),
}


def explain_finding(code: str) -> Explanation:
    key = code.strip()
    if key in EXPLANATIONS:
        return EXPLANATIONS[key]
    rule = get_rule(key)
    if rule is not None:
        return Explanation(
            key,
            rule.title,
            rule.description,
            "This finding is part of Evagix's evidence-first rule registry.",
            rule.remediation,
            rule.severity,
        )
    return Explanation(
        key,
        "Unknown finding code",
        "This code is not in the built-in explanation or rule registry.",
        "It may come from a future version, a custom policy, or a typo.",
        "Run `evagix doctor . --format json` to inspect active findings and check spelling.",
    )
