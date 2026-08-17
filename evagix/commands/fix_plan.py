from __future__ import annotations

from pathlib import Path

from evagix.commands.prepare import PROTECTED_PROJECT_FILES, SAFE_EVAGIX_WRITES
from evagix.core.constants import EXPERIMENTAL_WARNING
from evagix.scanner import scan_repo
from evagix.security.output import redacted_text_output


@redacted_text_output
def render_repository_fix_plan(root: Path) -> str:
    facts = scan_repo(root)
    lines = [
        "Evagix Fix Plan",
        "",
        f"Experimental: plan only. {EXPERIMENTAL_WARNING} This command does not edit README or agent instruction files.",
        "",
        "Can plan:",
        "- create AGENTS.md suggestion",
        "- create Copilot instruction suggestion",
        "- write evidence/context/risk artifacts inside .evagix/ in a future safe apply mode",
        "- add safety banner suggestion for Evagix-generated files",
        "- normalize Evagix-generated files only",
        "",
        "Safe .evagix outputs:",
    ]
    for path in SAFE_EVAGIX_WRITES:
        lines.append(f"- {path}")
    lines.extend(["", "Cannot auto-fix in this release:"])
    for path in PROTECTED_PROJECT_FILES:
        lines.append(f"- {path}")
    if not facts.commands:
        lines.extend(
            [
                "",
                "Known limitation:",
                "- No evidence-backed commands were detected; command fixes require manual review.",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
