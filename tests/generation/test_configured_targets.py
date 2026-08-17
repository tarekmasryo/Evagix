from __future__ import annotations

import json
from pathlib import Path

import pytest
from pytest import CaptureFixture

from evagix.cli import main
from evagix.config import load_config, selected_targets


def _make_repo(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["pytest", "ruff"]\n',
        encoding="utf-8",
    )
    (root / "tests").mkdir()


def test_all_targets_false_generates_no_files(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    _make_repo(tmp_path)
    (tmp_path / "evagix.toml").write_text(
        "\n".join(
            [
                "[targets]",
                "universal_md = false",
                "universal_json = false",
                "agents = false",
                "claude = false",
                "gemini = false",
                "cursor = false",
                "copilot = false",
                "windsurf = false",
                "continue = false",
                "generic = false",
            ]
        ),
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert selected_targets(config, None) == []
    assert main(["compile", str(tmp_path), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "AGENTS.md" not in out
    assert "context.md" not in out


def test_output_path_must_stay_inside_repo(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    _make_repo(tmp_path)

    with pytest.raises(SystemExit) as exc:
        main(["report", str(tmp_path), "-o", "../escape.md", "--force"])
    assert exc.value.code == 1
    assert "Output path must stay inside repository root" in capsys.readouterr().err


def test_universal_context_and_custom_json_target(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    (tmp_path / "evagix.toml").write_text(
        """
[targets]
universal_md = true
universal_json = true
agents = false
claude = false
gemini = false
cursor = false
copilot = false
windsurf = false

[[targets.custom]]
name = "local_agent"
path = ".evagix/local-agent.json"
format = "json"
include = ["facts", "commands", "risks", "policies", "repo_map"]
""".strip(),
        encoding="utf-8",
    )

    assert main(["compile", str(tmp_path)]) == 0
    assert (tmp_path / ".evagix" / "context.md").exists()
    payload = json.loads((tmp_path / ".evagix" / "context.json").read_text(encoding="utf-8"))
    custom_payload = json.loads((tmp_path / ".evagix" / "local-agent.json").read_text(encoding="utf-8"))
    assert payload["_evagix_generated"] == "evagix:generated"
    assert payload["export_model"] == "universal_context_with_tool_specific_adapters"
    assert custom_payload["custom_target"]["name"] == "local_agent"
