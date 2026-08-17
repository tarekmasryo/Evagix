from __future__ import annotations

import json
from pathlib import Path

from evagix.cli import main
from evagix.decide import decide_repo
from evagix.readme_audit import audit_readme
from evagix.scanner import scan_repo


def _repo(root: Path) -> None:
    (root / "README.md").write_text(
        "# Demo\n\nProduction-ready FastAPI service with Dockerized CI/CD monitoring and tests.\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["fastapi", "pytest", "ruff"]\n',
        encoding="utf-8",
    )
    (root / "tests").mkdir()


def test_decide_is_project_aware_for_ml_dashboards(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# ML Dashboard\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text(
        "streamlit\npandas\nscikit-learn\nplotly\npytest\nruff\n", encoding="utf-8"
    )
    (tmp_path / "Makefile").write_text(
        "test:\n\tpytest\nlint:\n\truff check .\nrun:\n\tstreamlit run app.py\n", encoding="utf-8"
    )
    facts = scan_repo(tmp_path)
    decision = decide_repo(tmp_path, facts)
    joined = " ".join(decision.next_best_actions + decision.hardening_steps)
    assert "dashboard/model smoke" in joined or "ML/dashboard smoke" in joined
    assert any("Dataset, label, split, metric" in item for item in decision.needs_human_approval)


def test_decide_does_not_request_lockfile_for_pnpm_workspace(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Workspace\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {"test": "vitest", "lint": "eslint .", "typecheck": "tsc --noEmit"},
                "workspaces": ["packages/*"],
                "devDependencies": {"typescript": "latest", "vitest": "latest", "eslint": "latest"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    package = tmp_path / "packages" / "app"
    package.mkdir(parents=True)
    (package / "package.json").write_text(
        json.dumps(
            {
                "scripts": {"test": "vitest", "lint": "eslint ."},
                "devDependencies": {"typescript": "latest", "vitest": "latest", "eslint": "latest"},
            }
        ),
        encoding="utf-8",
    )
    facts = scan_repo(tmp_path)
    decision = decide_repo(tmp_path, facts)
    assert all("lockfile" not in action.lower() for action in decision.next_best_actions)


def test_readme_audit_and_decision_plan_are_evidence_based(tmp_path: Path) -> None:
    _repo(tmp_path)
    facts = scan_repo(tmp_path)
    report = audit_readme(tmp_path, facts)
    assert report.score < 100
    assert {item.claim for item in report.unsupported} >= {"dockerized", "ci/cd", "monitoring"}

    decision = decide_repo(tmp_path, facts)
    assert decision.next_best_actions
    assert decision.needs_human_approval
    assert decision.risk_level in {"low", "medium", "high"}


def test_docs_tutorial_repo_does_not_get_app_style_validation_penalties(tmp_path: Path, capsys) -> None:
    import json

    (tmp_path / "README.md").write_text(
        "# AI Agents for Beginners\n\nA course with tutorials, lessons, examples, and notebooks for learning agents.\n",
        encoding="utf-8",
    )
    (tmp_path / "lessons").mkdir()
    (tmp_path / "notebooks").mkdir()
    (tmp_path / "AGENTS.md").write_text(
        "# Agent notes\n\nUse this repository as learning material.\n",
        encoding="utf-8",
    )

    assert main(["eval-context", str(tmp_path), "--strict", "--fail-on", "high", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    findings = payload["evaluation"]["findings"]
    assert payload["evaluation"]["score"] is None
    assert payload["evaluation"]["score_type"] == "unscored_external_context"
    assert all(item["severity"] != "high" for item in findings if item["id"] == "agent-context.missing-test")


def test_decide_prioritizes_tampered_or_stale_agent_files(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8")
    assert main(["compile", str(tmp_path), "--target", "agents"]) == 0
    (tmp_path / "AGENTS.md").write_text("manual instructions\n", encoding="utf-8")
    facts = scan_repo(tmp_path)
    decision = decide_repo(tmp_path, facts)
    assert decision.next_best_actions
    assert all("tampered" not in action.lower() for action in decision.next_best_actions)
