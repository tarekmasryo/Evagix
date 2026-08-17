from __future__ import annotations

from pathlib import Path

import pytest

from evagix.cli import main
from evagix.fixes import FixPlan, apply_fix, plan_fix, render_fix_plan


def test_plan_fix_creates_evagix_ci_workflow() -> None:
    plan = plan_fix(Path.cwd(), "missing-ci", fail_under=90)

    assert plan.safe_to_apply
    assert ".github/workflows/evagix.yml" in plan.files
    assert "evagix check ." in plan.files[".github/workflows/evagix.yml"]
    assert "--fail-under 90" in plan.files[".github/workflows/evagix.yml"]


def test_plan_fix_creates_eval_and_typecheck_guides() -> None:
    eval_plan = plan_fix(Path.cwd(), "missing-llm-eval")
    typecheck_plan = plan_fix(Path.cwd(), "missing-typecheck")

    assert eval_plan.safe_to_apply
    assert "EVAGIX_AI_EVAL_GUIDE.md" in eval_plan.files
    assert typecheck_plan.safe_to_apply
    assert "EVAGIX_TYPECHECK_GUIDE.md" in typecheck_plan.files


def test_plan_fix_marks_generated_context_fixes_as_advisory() -> None:
    for code in ["stale-target", "missing-target"]:
        plan = plan_fix(Path.cwd(), code)
        rendered = render_fix_plan(plan)

        assert not plan.safe_to_apply
        assert plan.files == {}
        assert "advisory" in rendered


def test_plan_fix_unknown_code_is_manual_only() -> None:
    plan = plan_fix(Path.cwd(), "unknown-code")

    assert not plan.safe_to_apply
    assert plan.title == "No automatic fix available"
    assert plan.files == {}


def test_apply_fix_writes_files_and_respects_force(tmp_path: Path) -> None:
    plan = FixPlan(
        code="demo",
        title="Demo",
        actions=["Create demo file."],
        files={"nested/demo.txt": "first\n"},
    )

    assert apply_fix(tmp_path, plan) == ["nested/demo.txt"]
    assert (tmp_path / "nested" / "demo.txt").read_text(encoding="utf-8") == "first\n"

    with pytest.raises(FileExistsError):
        apply_fix(tmp_path, plan)

    overwrite = FixPlan(
        code="demo",
        title="Demo",
        actions=["Overwrite demo file."],
        files={"nested/demo.txt": "second\n"},
    )
    assert apply_fix(tmp_path, overwrite, force=True) == ["nested/demo.txt"]
    assert (tmp_path / "nested" / "demo.txt").read_text(encoding="utf-8") == "second\n"


def test_apply_fix_skips_advisory_plans(tmp_path: Path) -> None:
    plan = FixPlan(
        code="manual",
        title="Manual only",
        actions=["Do this manually."],
        files={"SHOULD_NOT_WRITE.md": "nope\n"},
        safe_to_apply=False,
    )

    assert apply_fix(tmp_path, plan) == []
    assert not (tmp_path / "SHOULD_NOT_WRITE.md").exists()


def test_fix_command_requires_code(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["fix"]) == 2
    assert "Finding code required" in capsys.readouterr().err


def test_fix_command_dry_run_does_not_write(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["fix", "missing-ci", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "Dry-run only" in output
    assert not (tmp_path / ".github" / "workflows" / "evagix.yml").exists()


def test_fix_command_apply_writes_and_reports_conflict(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["fix", "missing-ci", str(tmp_path), "--apply"]) == 0
    assert (tmp_path / ".github" / "workflows" / "evagix.yml").exists()
    assert "Written:" in capsys.readouterr().out

    assert main(["fix", "missing-ci", str(tmp_path), "--apply"]) == 1
    assert "already exists" in capsys.readouterr().err


def test_fix_command_plan_is_repository_level(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["fix", str(tmp_path), "--plan"]) == 0
    output = capsys.readouterr().out
    assert "Evagix Fix Plan" in output
    assert "does not edit README" in output
