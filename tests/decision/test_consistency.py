from __future__ import annotations

import json
from pathlib import Path

from evagix.decide import decide_repo
from evagix.scanner import scan_repo


def test_decide_does_not_say_ready_when_generated_targets_are_missing(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# App\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {"test": "vitest", "lint": "eslint .", "typecheck": "tsc --noEmit"},
                "devDependencies": {"typescript": "latest", "vitest": "latest", "eslint": "latest"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}\n", encoding="utf-8")
    facts = scan_repo(tmp_path)
    decision = decide_repo(tmp_path, facts)
    assert decision.readiness != "ready"
    assert all("repository looks ready" not in action.lower() for action in decision.next_best_actions)
    assert decision.next_best_actions


def test_decide_deduplicates_lint_recommendations_for_bare_repo(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Bare Python repo\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('hello')\n", encoding="utf-8")
    facts = scan_repo(tmp_path)
    decision = decide_repo(tmp_path, facts)
    lint_actions = [action for action in decision.next_best_actions if "lint" in action.lower()]
    assert lint_actions == ["Add an explicit lint command for safe automated review."]
