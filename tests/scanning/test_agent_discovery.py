from __future__ import annotations

from pathlib import Path

import pytest

from evagix.commands.agents import run_agents
from evagix.commands.mcp import run_mcp
from evagix.scanners.agent_files import (
    discover_agent_files,
    render_agent_discovery_markdown,
    render_agent_discovery_text,
)
from evagix.scanners.mcp import discover_mcp_configs


def test_agent_file_discovery_is_preview_only(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Instructions\n", encoding="utf-8")
    (tmp_path / "CODEX.md").write_text("# Generic notes\n", encoding="utf-8")
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "copilot-instructions.md").write_text("# Copilot\n", encoding="utf-8")

    facts = discover_agent_files(tmp_path)
    paths = [item.path for item in facts]

    assert paths == [".github/copilot-instructions.md", "AGENTS.md"]
    assert "CODEX.md" not in paths

    rendered, code = run_agents(tmp_path, output_format="text")
    assert code == 0
    assert "Preview: discovery only" in rendered
    assert "Detected agent context files" in rendered


def test_mcp_detection_is_conservative(tmp_path: Path) -> None:
    (tmp_path / ".cursor").mkdir()
    (tmp_path / ".cursor" / "mcp.json").write_text('{"servers": {}}\n', encoding="utf-8")

    configs = discover_mcp_configs(tmp_path)

    assert [item.path for item in configs] == [".cursor/mcp.json"]
    assert "does not audit MCP security yet" in configs[0].message

    rendered, code = run_mcp(tmp_path)
    assert code == 0
    assert "Experimental: detection only" in rendered
    assert "MCP config detected" in rendered


def test_agent_file_discovery_prunes_skipped_directories_and_caps_results(tmp_path: Path) -> None:
    instructions = tmp_path / ".github" / "instructions"
    instructions.mkdir(parents=True)
    (instructions / "kept.instructions.md").write_text("Review safely.\n", encoding="utf-8")
    skipped = instructions / "node_modules" / "pkg"
    skipped.mkdir(parents=True)
    (skipped / "ignored.instructions.md").write_text("Ignore this.\n", encoding="utf-8")

    facts = discover_agent_files(tmp_path)

    assert [item.path for item in facts] == [".github/instructions/kept.instructions.md"]


def test_agent_file_discovery_handles_files_dirs_symlinks_and_renderers(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Agent instructions\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# Claude\n", encoding="utf-8")
    (tmp_path / "CODEX.md").write_text("# Generic optional context\n", encoding="utf-8")
    (tmp_path / "GEMINI.md").write_text("# Gemini\n", encoding="utf-8")
    (tmp_path / ".github" / "instructions").mkdir(parents=True)
    (tmp_path / ".github" / "instructions" / "review.instructions.md").write_text("Review safely.\n", encoding="utf-8")
    (tmp_path / ".github" / "instructions" / "node_modules").mkdir()
    (tmp_path / ".github" / "instructions" / "node_modules" / "skip.md").write_text("skip\n", encoding="utf-8")
    (tmp_path / ".clinerules").write_text("# Cline\n", encoding="utf-8")
    (tmp_path / "real.md").write_text("target\n", encoding="utf-8")
    try:
        (tmp_path / "AGENTS.override.md").symlink_to(tmp_path / "real.md")
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is unavailable without platform support or Windows Developer Mode")

    facts = discover_agent_files(tmp_path)
    paths = [fact.path for fact in facts]
    assert paths == [
        ".clinerules",
        ".github/instructions/review.instructions.md",
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
    ]
    assert "CODEX.md" not in paths
    assert next(fact for fact in facts if fact.path == ".clinerules").tool == "Cline"
    assert "Detected agent context files" in render_agent_discovery_text(facts)
    assert "| `AGENTS.md` |" in render_agent_discovery_markdown(facts)
    assert "No common agent-context files" in render_agent_discovery_text([])
    assert "No common agent-context files" in render_agent_discovery_markdown([])
