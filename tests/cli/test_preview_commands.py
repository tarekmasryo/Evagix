from __future__ import annotations

from pathlib import Path

from evagix.commands.preview_cmds import _cmd_agents, _cmd_context_pack, _cmd_mcp, _cmd_prepare


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "README.md").write_text("# Demo\n\nRun `python -m pytest`.\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    return tmp_path


def test_agents_preview_text_and_json(tmp_path: Path, capsys) -> None:
    root = _repo(tmp_path)
    assert _cmd_agents(root, "text") == 0
    text_out = capsys.readouterr().out
    assert "Agent" in text_out or "agent" in text_out

    assert _cmd_agents(root, "json") == 0
    json_out = capsys.readouterr().out
    assert '"schema_version": "0.1-preview"' in json_out
    assert '"agent_files"' in json_out


def test_prepare_requires_plan_and_renders_plan(tmp_path: Path, capsys) -> None:
    root = _repo(tmp_path)
    assert _cmd_prepare(root, plan=False) == 2
    err = capsys.readouterr().err
    assert "only supports --plan" in err

    assert _cmd_prepare(root, plan=True) == 0
    out = capsys.readouterr().out
    assert "Evagix Prepare Plan" in out
    assert "Context pack preview" in out


def test_context_pack_preview_outputs_source_grounded_pack(tmp_path: Path, capsys) -> None:
    root = _repo(tmp_path)
    assert _cmd_context_pack(root) == 0
    out = capsys.readouterr().out
    assert "# Evagix Context Pack" in out
    assert "Repository" in out


def test_mcp_preview_text_and_json(tmp_path: Path, capsys) -> None:
    root = _repo(tmp_path)
    assert _cmd_mcp(root, "text") == 0
    text_out = capsys.readouterr().out
    assert "Evagix MCP Config Detection" in text_out

    assert _cmd_mcp(root, "json") == 0
    json_out = capsys.readouterr().out
    assert '"schema_version": "0.1-experimental"' in json_out
    assert '"mcp_configs"' in json_out
