from __future__ import annotations

from pathlib import Path

from evagix.cli import main
from evagix.commands.context_pack import run_context_pack
from evagix.commands.fix_plan import render_repository_fix_plan
from evagix.commands.prepare import render_prepare_plan
from evagix.reports.context_pack import render_context_pack
from evagix.scanner import scan_repo


def test_prepare_plan_and_fix_plan_do_not_write_project_files(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))

    prepare_plan = render_prepare_plan(tmp_path)
    fix_plan = render_repository_fix_plan(tmp_path)

    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert before == after
    assert "This command does not modify project files" in prepare_plan
    assert "Will not touch" in prepare_plan
    assert "README.md" in prepare_plan
    assert "does not edit README" in fix_plan
    assert ".github/copilot-instructions.md" in fix_plan


def test_context_pack_is_source_grounded(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'demo'\n[project.optional-dependencies]\ndev = ['pytest']\n", encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_demo.py").write_text("def test_demo():\n    assert True\n", encoding="utf-8")
    facts = scan_repo(tmp_path)

    rendered = render_context_pack(tmp_path, facts)

    assert "# Evagix Context Pack" in rendered
    assert "Source:" in rendered or "evidence:" in rendered
    assert "Unknowns are not guessed" in rendered


def test_optional_agent_adapters_compile(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\ndependencies = ["pytest"]\n', encoding="utf-8")
    assert (
        main(
            [
                "compile",
                str(tmp_path),
                "--target",
                "cline",
                "--target",
                "roo",
                "--target",
                "aider",
                "--target",
                "openhands",
            ]
        )
        == 0
    )
    assert (tmp_path / ".clinerules").exists()
    assert (tmp_path / ".roo" / "rules" / "evagix.md").exists()
    assert (tmp_path / "CONVENTIONS.md").exists()
    assert (tmp_path / ".openhands" / "skills" / "repository" / "SKILL.md").exists()
    assert "Aider Conventions" in (tmp_path / "CONVENTIONS.md").read_text(encoding="utf-8")
    assert "OpenHands Repository Skill" in (tmp_path / ".openhands" / "skills" / "repository" / "SKILL.md").read_text(
        encoding="utf-8"
    )


def test_compile_generates_gemini_and_windsurf_targets(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.1.0"
dependencies = ["pytest", "ruff"]
""".strip(),
        encoding="utf-8",
    )

    assert main(["compile", str(tmp_path), "--target", "gemini", "--target", "windsurf"]) == 0

    assert (tmp_path / "GEMINI.md").exists()
    assert (tmp_path / ".windsurf" / "rules" / "evagix.md").exists()


def test_context_pack_uses_configured_commands(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8")
    (tmp_path / "evagix.toml").write_text('[commands]\ntest = "python -m pytest"\n', encoding="utf-8")

    output = run_context_pack(tmp_path)

    assert "`test`: `python -m pytest`" in output


def test_agent_tasks_target_generates_task_templates(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\ndependencies = ["pytest"]\n', encoding="utf-8")

    assert main(["compile", str(tmp_path), "--target", "agent_tasks"]) == 0
    expected = [
        ".agent_tasks/README.md",
        ".agent_tasks/bugfix.md",
        ".agent_tasks/refactor.md",
        ".agent_tasks/add-feature.md",
        ".agent_tasks/write-tests.md",
        ".agent_tasks/security-review.md",
    ]
    for relative_path in expected:
        path = tmp_path / relative_path
        assert path.exists(), relative_path
        assert "evagix:generated" in path.read_text(encoding="utf-8")


def test_sync_plan_does_not_suggest_optional_agent_vendors_by_default(tmp_path: Path, capsys) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")

    assert main(["sync", str(tmp_path), "--plan"]) == 0
    out = capsys.readouterr().out
    assert ".evagix/context.md" in out
    assert ".evagix/context.json" in out
    assert "AGENTS.md" not in out
    assert "CLAUDE.md" not in out
    assert "GEMINI.md" not in out
    assert ".github/copilot-instructions.md" not in out


def test_compile_default_exports_only_universal_context(tmp_path: Path, capsys) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")

    assert main(["compile", str(tmp_path), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert ".evagix/context.md" in out
    assert ".evagix/context.json" in out
    assert "AGENTS.md" not in out
    assert "CLAUDE.md" not in out
    assert "GEMINI.md" not in out
