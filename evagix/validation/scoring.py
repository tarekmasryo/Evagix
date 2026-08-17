from __future__ import annotations

from evagix.report_models import CategoryScore, DoctorFinding, DoctorReport


def _score_report(findings: list[DoctorFinding]) -> DoctorReport:
    raw_score = 100 - sum(max(0, item.penalty) for item in findings)
    bounded_score = max(0, min(100, raw_score))
    categories = _category_scores(findings)
    final_score = _calibrated_final_score(bounded_score, findings, categories)
    return DoctorReport(
        score=final_score,
        findings=findings,
        categories=categories,
        domain_scores=_domain_scores(categories),
        maturity_level=_maturity_level(final_score, findings),
    )


def _calibrated_final_score(raw_score: int, findings: list[DoctorFinding], categories: dict[str, CategoryScore]) -> int:
    """Blend additive penalties with category health for large real-world repos.

    Strict mode can legitimately produce many low/medium findings in monorepos,
    docs-heavy projects, and AI libraries. A simple sum of all penalties can make
    a repo with strong CI, command, and safety evidence look worse than its
    category breakdown. Keep errors and safety findings authoritative, but avoid
    collapsing the final score solely from many advisory findings.
    """
    if not findings:
        return raw_score
    if any(item.severity == "error" for item in findings):
        return raw_score
    if any(_is_blocking_safety_finding(item.code) for item in findings):
        return raw_score

    reliability_keys = ("commands", "ci", "safety")
    reliability_scores = [categories[key].score for key in reliability_keys]
    reliability = round(sum(reliability_scores) / len(reliability_scores))
    if reliability < 90 or min(reliability_scores) < 95:
        return raw_score

    category_values = [item.score for item in categories.values()]
    category_average = round(sum(category_values) / len(category_values)) if category_values else raw_score
    warning_count = sum(1 for item in findings if item.severity == "warning")
    advisory_penalty = min(18, warning_count * 3)
    category_floor = max(0, min(88, category_average - advisory_penalty))

    return max(raw_score, category_floor)


def score_explanations(report: DoctorReport) -> list[str]:
    """Return concise reasons explaining the final score/capping behavior."""
    explanations: list[str] = []
    if not report.findings:
        return ["No readiness findings were detected."]
    for item in report.findings:
        if item.penalty > 0:
            explanations.append(f"-{item.penalty} {item.code}: {item.message}")
    if any(item.severity == "error" for item in report.findings):
        explanations.append("Final score remains strict because at least one error-severity finding is present.")
    elif any(_is_blocking_safety_finding(item.code) for item in report.findings):
        explanations.append("Final score remains strict because a blocking safety/context finding is present.")
    elif report.score >= 80:
        explanations.append("Final score was calibrated against healthy command, CI, and safety category evidence.")
    return explanations[:20]


def _is_blocking_safety_finding(code: str) -> bool:
    return (
        code.startswith("dangerous-command.")
        or code.startswith("context-poisoning.")
        or code
        in {
            "generated-context-drift",
            "generated-context-tampered",
            "tampered-target",
        }
    )


def _category_scores(findings: list[DoctorFinding]) -> dict[str, CategoryScore]:
    buckets: dict[str, list[DoctorFinding]] = {
        "agent_context": [],
        "commands": [],
        "ci": [],
        "docs_onboarding": [],
        "safety": [],
        "project_specific": [],
    }
    for item in findings:
        buckets[_category_for_finding(item.code)].append(item)
    return {
        name: CategoryScore(
            score=max(0, min(100, 100 - sum(max(0, item.penalty) for item in items))),
            status=_category_status(items),
            findings=[item.code for item in items],
        )
        for name, items in buckets.items()
    }


def _domain_scores(categories: dict[str, CategoryScore]) -> dict[str, CategoryScore]:
    groups = {
        "repository_readiness": ("commands", "ci", "docs_onboarding", "project_specific"),
        "agent_context_governance": ("agent_context", "safety"),
        "pr_risk_readiness": ("ci", "safety", "commands"),
    }
    return {name: _combine_category_scores(categories, keys) for name, keys in groups.items()}


def _combine_category_scores(categories: dict[str, CategoryScore], keys: tuple[str, ...]) -> CategoryScore:
    selected = [categories[key] for key in keys if key in categories]
    if not selected:
        return CategoryScore(score=100, status="pass", findings=[])
    score = round(sum(item.score for item in selected) / len(selected))
    statuses = {item.status for item in selected}
    if "fail" in statuses:
        status = "fail"
    elif "warn" in statuses:
        status = "warn"
    elif "info" in statuses:
        status = "info"
    else:
        status = "pass"
    findings: list[str] = []
    for item in selected:
        findings.extend(item.findings)
    return CategoryScore(score=max(0, min(100, score)), status=status, findings=sorted(set(findings)))


def _category_for_finding(code: str) -> str:
    if (
        code in {"missing-target", "stale-target", "generated-context-drift", "tampered-target"}
        or code.startswith("agent-context.")
        or code.startswith("context-poisoning.")
    ):
        return "agent_context"
    if code in {
        "missing-install",
        "missing-test",
        "missing-lint",
        "missing-typecheck",
        "formatter-only-lint",
        "inferred-install-command",
        "inferred-test-command",
        "frontend-install-not-deterministic",
    }:
        return "commands"
    if code in {"missing-ci"}:
        return "ci"
    if code in {
        "missing-readme",
        "readme-command-gap",
        "missing-onboarding-pack",
        "readme-unsupported-claims",
        "readme-partial-claims",
    } or code.startswith("readme-evidence."):
        return "docs_onboarding"
    if (
        code.startswith("dangerous-command.")
        or "security" in code
        or "risk" in code
        or "env" in code
        or "terraform" in code
        or "kubernetes" in code
    ):
        return "safety"
    return "project_specific"


def _category_status(items: list[DoctorFinding]) -> str:
    if any(item.severity == "error" for item in items):
        return "fail"
    if any(item.severity == "warning" for item in items):
        return "warn"
    if items:
        return "info"
    return "pass"


def _maturity_level(score: int, findings: list[DoctorFinding]) -> str:
    has_error = any(item.severity == "error" for item in findings)
    if score >= 90 and not has_error:
        return "clear"
    if score >= 80 and not has_error:
        return "ready"
    if score >= 60:
        return "limited"
    if score >= 40:
        return "early"
    return "not-ready"


def _format_target_list(targets: list[str], *, limit: int = 8) -> str:
    shown = targets[:limit]
    suffix = f" (+{len(targets) - limit} more)" if len(targets) > limit else ""
    return ", ".join(f"`{target}`" for target in shown) + suffix
