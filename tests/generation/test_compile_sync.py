import json
from pathlib import Path

from evagix.cli import main
from evagix.scanner import scan_repo
from evagix.validators import check_repo


def _make_python_repo(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.1.0"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.6"]
""".strip(),
        encoding="utf-8",
    )
    (root / "tests").mkdir()


def test_compile_writes_targets_and_check_passes(tmp_path: Path) -> None:
    _make_python_repo(tmp_path)

    assert main(["compile", str(tmp_path)]) == 0

    assert (tmp_path / ".evagix" / "context.md").exists()
    assert (tmp_path / ".evagix" / "context.json").exists()
    assert not (tmp_path / "AGENTS.md").exists()

    facts = scan_repo(tmp_path)
    result = check_repo(tmp_path, facts)
    assert result.ok


def test_check_fails_when_generated_file_is_stale(tmp_path: Path) -> None:
    _make_python_repo(tmp_path)
    assert main(["compile", str(tmp_path)]) == 0

    (tmp_path / "docker-compose.yml").write_text("services:\n  redis:\n    image: redis:7\n", encoding="utf-8")

    assert main(["check", str(tmp_path)]) == 1


def test_compile_does_not_overwrite_manual_file_without_force(tmp_path: Path) -> None:
    _make_python_repo(tmp_path)
    (tmp_path / "AGENTS.md").write_text("# Manual instructions\n", encoding="utf-8")

    assert main(["compile", str(tmp_path), "--target", "agents"]) == 1
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "# Manual instructions\n"


def test_compile_preflight_avoids_partial_writes_on_manual_conflict(tmp_path: Path) -> None:
    _make_python_repo(tmp_path)
    (tmp_path / "AGENTS.md").write_text("# Manual instructions\n", encoding="utf-8")

    assert main(["compile", str(tmp_path), "--target", "agents"]) == 1

    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "# Manual instructions\n"
    assert not (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / "CODEX.md").exists()


def test_sync_does_not_overwrite_manual_agent_file(tmp_path: Path) -> None:
    _make_python_repo(tmp_path)
    (tmp_path / "AGENTS.md").write_text("manual instructions\n", encoding="utf-8")

    assert main(["sync", str(tmp_path)]) == 0

    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "manual instructions\n"
    assert not (tmp_path / "CLAUDE.md").exists()


def test_sync_updates_generated_stale_files(tmp_path: Path) -> None:
    _make_python_repo(tmp_path)
    assert main(["compile", str(tmp_path), "--target", "agents"]) == 0
    agent_path = tmp_path / "AGENTS.md"
    agent_path.write_text(agent_path.read_text(encoding="utf-8") + "\nSTALE MANUAL DRIFT\n", encoding="utf-8")

    assert main(["sync", str(tmp_path)]) == 0

    assert "STALE MANUAL DRIFT" not in agent_path.read_text(encoding="utf-8")


def test_compile_adds_specialized_rules(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        "fastapi\nsqlalchemy\nalembic\ncelery\nredis\nlangchain\npandas\nscikit-learn\npytest\nruff\n",
        encoding="utf-8",
    )
    (tmp_path / "alembic").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "build": "vite build",
                    "lint": "eslint .",
                    "typecheck": "tsc --noEmit",
                },
                "dependencies": {"react": "latest", "vite": "latest"},
                "devDependencies": {"typescript": "latest", "eslint": "latest"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: CI\n", encoding="utf-8")

    assert main(["compile", str(tmp_path), "--target", "agents"]) == 0
    content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")

    assert "Backend/API Rules" in content
    assert "Database & Migration Rules" in content
    assert "Worker/Queue Rules" in content
    assert "AI/Retrieval Rules" in content
    assert "ML/Data Project Rules" in content
    assert "Frontend Rules" in content
    assert " - high confidence" in content
    assert "—" not in content


def test_init_ci_writes_workflow(tmp_path: Path) -> None:
    assert main(["init-ci", str(tmp_path)]) == 0
    workflow = tmp_path / ".github" / "workflows" / "evagix.yml"
    assert workflow.exists()
    content = workflow.read_text(encoding="utf-8")
    assert "evagix check ." in content
    assert "git+https://github.com/tarekmasryo/Evagix.git@v0.1.1" in content
    assert "AGENTS.md" in content
    assert "CODEX.md" not in content
