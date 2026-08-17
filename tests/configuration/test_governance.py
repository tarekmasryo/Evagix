from pathlib import Path

from pytest import CaptureFixture

from evagix.cli import main


def test_init_defaults_to_universal_and_agents_only(tmp_path: Path):
    assert main(["init", str(tmp_path)]) == 0

    config = (tmp_path / "evagix.toml").read_text(encoding="utf-8")

    assert "universal_md = true" in config
    assert "universal_json = true" in config
    assert "agents = true" in config
    assert "claude = false" in config
    assert "codex" not in config
    assert "gemini = false" in config
    assert "cursor = false" in config
    assert "copilot = false" in config
    assert "windsurf = false" in config
    assert "agent_brief = false" in config
    assert "safety_policy = false" in config
    assert "repo_map = false" in config
    assert "agent_tasks = false" in config
    assert "continue = false" in config
    assert "cline = false" in config
    assert "roo = false" in config
    assert "aider = false" in config
    assert "openhands = false" in config
    assert "generic = false" in config


def test_config_custom_rules_and_targets(tmp_path: Path, capsys: CaptureFixture[str]):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="demo"\ndependencies=["pytest"]\n', encoding="utf-8")
    (tmp_path / "evagix.toml").write_text(
        """
[targets]
agents = true
claude = false

[profiles]
profiles = ["python-backend"]

[policy]
fail_under = 50
ignore_findings = ["missing-lint"]

[commands]
typecheck = "mypy ."

[rules]
general = ["Keep public API stable."]
forbidden = ["Do not edit generated SDK files."]
""".strip(),
        encoding="utf-8",
    )

    assert main(["compile", str(tmp_path)]) == 0
    content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "Keep public API stable" in content
    assert "Do not edit generated SDK files" in content
    assert "typecheck" in content
    assert not (tmp_path / "CLAUDE.md").exists()


def test_report_formats_and_policy_command(tmp_path: Path):
    (tmp_path / "requirements.txt").write_text("fastapi\npytest\n", encoding="utf-8")
    assert main(["init", str(tmp_path), "--force", "--profile", "python-backend"]) == 0
    assert main(["policy", str(tmp_path), "--json"]) == 0
    assert main(["compile", str(tmp_path)]) == 0
    assert main(["report", str(tmp_path), "--format", "sarif", "-o", "evagix.sarif", "--force"]) == 0
    assert "sarif" in (tmp_path / "evagix.sarif").read_text(encoding="utf-8").lower()
    assert main(["report", str(tmp_path), "--format", "pr-comment", "-o", "pr.md", "--force"]) == 0
    assert "Evagix Check" in (tmp_path / "pr.md").read_text(encoding="utf-8")
