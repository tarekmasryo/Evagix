from __future__ import annotations

import sys
from pathlib import Path

from evagix.commands.common import _normalize_existing_root
from evagix.commands.fix_plan import render_repository_fix_plan
from evagix.fixes import apply_fix, plan_fix, render_fix_plan


def _cmd_fix(root: Path, code: str | None, plan: bool, apply_changes: bool, force: bool, fail_under: int) -> int:
    if plan:
        # `evagix fix . --plan` is a repository-level experimental plan.
        # Keep existing `evagix fix <code> [path]` behavior unchanged when --plan is absent.
        repo_root = Path(code) if code and root == Path(".") else root
        repo_root = _normalize_existing_root(repo_root)
        print(render_repository_fix_plan(repo_root), end="")
        return 0
    if not code:
        print(
            "Finding code required. Example: `evagix fix missing-ci .` or use `evagix fix . --plan`.",
            file=sys.stderr,
        )
        return 2
    root = _normalize_existing_root(root)
    fix_plan = plan_fix(root, code, fail_under=fail_under)
    print(render_fix_plan(fix_plan))
    if not apply_changes:
        print("\nDry-run only. Re-run with --apply to write safe fix files.")
        return 0
    try:
        written = apply_fix(root, fix_plan, force=force)
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if written:
        print("\nWritten:")
        for relative_path in written:
            print(f"  - {relative_path}")
    else:
        print("\nNo files were written.")
    return 0
