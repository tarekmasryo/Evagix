from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from evagix.constants import DEFAULT_GITHUB_REF, DEFAULT_GITHUB_REPO
from evagix.core.io import apply_write_plan, build_write_plan
from evagix.security.output import redacted_text_output
from evagix.templates import (
    AI_EVAL_GUIDE_TEMPLATE,
    TYPECHECK_GUIDE_TEMPLATE,
    evagix_ci_workflow,
)
from evagix.thresholds import ScoreThreshold


@dataclass(frozen=True)
class FixPlan:
    code: str
    title: str
    actions: list[str]
    files: dict[str, str]
    safe_to_apply: bool = True


def plan_fix(root: Path, code: str, *, fail_under: int = 80) -> FixPlan:
    root = root.resolve()
    fail_under = ScoreThreshold.parse(fail_under).value
    if code == "missing-ci":
        install_command = (
            f'python -m pip install "git+https://github.com/{DEFAULT_GITHUB_REPO}.git@{DEFAULT_GITHUB_REF}"'
        )
        content = evagix_ci_workflow(install_command=install_command, fail_under=fail_under)
        return FixPlan(
            code=code,
            title="Create Evagix Governance workflow",
            actions=[
                "Create .github/workflows/evagix.yml",
                "Review permissions and branch names before commit.",
            ],
            files={".github/workflows/evagix.yml": content},
        )
    if code == "missing-llm-eval":
        content = AI_EVAL_GUIDE_TEMPLATE
        return FixPlan(
            code=code,
            title="Create AI/Retrieval eval notes",
            actions=["Create EVAGIX_AI_EVAL_GUIDE.md with suggested evaluation commands."],
            files={"EVAGIX_AI_EVAL_GUIDE.md": content},
        )
    if code == "missing-typecheck":
        content = TYPECHECK_GUIDE_TEMPLATE
        return FixPlan(
            code=code,
            title="Create typecheck guide",
            actions=["Create EVAGIX_TYPECHECK_GUIDE.md."],
            files={"EVAGIX_TYPECHECK_GUIDE.md": content},
        )
    if code in {"stale-target", "generated-context-drift", "missing-target"}:
        return FixPlan(
            code=code,
            title="Refresh generated files",
            actions=["Run `evagix compile .` and review the diff."],
            files={},
            safe_to_apply=False,
        )
    return FixPlan(
        code=code,
        title="No automatic fix available",
        actions=["Use `evagix explain <code>` and address the finding manually."],
        files={},
        safe_to_apply=False,
    )


@redacted_text_output
def render_fix_plan(plan: FixPlan) -> str:
    lines = [f"Fix plan for `{plan.code}`: {plan.title}", ""]
    if plan.actions:
        lines.append("Actions:")
        for action in plan.actions:
            lines.append(f"  - {action}")
        lines.append("")
    if plan.files:
        lines.append("Files:")
        for path in plan.files:
            lines.append(f"  - {path}")
    else:
        lines.append("No files would be written by this fix.")
    if not plan.safe_to_apply:
        lines.append("\nThis fix is advisory and must be applied manually.")
    return "\n".join(lines)


def apply_fix(root: Path, plan: FixPlan, *, force: bool = False) -> list[str]:
    if not plan.safe_to_apply:
        return []
    write_plan = build_write_plan(root, plan.files, force=force)
    if write_plan.conflicts:
        conflict = write_plan.conflicts[0]
        raise FileExistsError(f"{conflict} already exists. Re-run with --force to overwrite.")
    return apply_write_plan(write_plan)
