from __future__ import annotations

from pathlib import Path

from evagix.model import RepoFacts
from evagix.report_models import AuditFinding
from evagix.security.output import redacted_text_output
from evagix.utils import format_csv
from evagix.validation.audit_actions import _uses_plain_npm_install, suggest_actions
from evagix.validation.audit_rules import audit_repo


@redacted_text_output
def render_audit_markdown(root: Path, facts: RepoFacts) -> str:
    findings = audit_repo(root, facts)
    lines = [
        "# Evagix Audit",
        "",
        f"- Repository: `{facts.root_name}`",
        f"- Profiles: {format_csv(facts.active_profiles)}",
        "",
        "## Findings",
        "",
    ]
    if findings:
        for item in findings:
            lines.append(f"- **{item.severity}** `{item.code}`: {item.message}")
    else:
        lines.append("- No audit findings.")
    lines.extend(["", "## Recommended Validation Commands", ""])
    if facts.commands:
        for name, command in facts.commands.items():
            validation_names = {
                "test",
                "lint",
                "typecheck",
                "build",
                "frontend_build",
                "frontend_test",
                "smoke",
                "doctor",
                "eval",
            }
            if name in validation_names or name.endswith(("_test", "_lint", "_typecheck", "_build")):
                lines.append(f"- `{name}`: `{command}`")
    else:
        lines.append("- No validation commands detected.")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "AuditFinding",
    "_uses_plain_npm_install",
    "audit_repo",
    "render_audit_markdown",
    "suggest_actions",
]
