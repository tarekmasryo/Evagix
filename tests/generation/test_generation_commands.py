from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from evagix.commands import generation
from evagix.config import EvagixConfig
from evagix.model import RepoFacts
from evagix.report_models import DoctorReport


def _facts(**overrides: object) -> RepoFacts:
    facts = RepoFacts(root_name="demo")
    for key, value in overrides.items():
        setattr(facts, key, value)
    return facts


def test_generation_sync_plan_and_write_error_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    facts = _facts(root_name="demo")
    config = EvagixConfig()
    monkeypatch.setattr(generation, "_facts", lambda *args, **kwargs: (facts, config))
    monkeypatch.setattr(generation, "_targets", lambda config, target: None)
    monkeypatch.setattr(
        generation,
        "render_all",
        lambda facts, targets, custom_targets: {
            ".evagix/context.md": "evagix:generated\nevagix:fingerprint=new\nbody\n",
            ".evagix/context.json": "evagix:generated\nevagix:fingerprint=new\njson\n",
            "AGENTS.md": "evagix:generated\nevagix:fingerprint=new\nagent\n",
        },
    )
    (tmp_path / ".evagix").mkdir()
    (tmp_path / ".evagix" / "context.md").write_text(
        "evagix:generated\nevagix:fingerprint=old\nbody\n", encoding="utf-8"
    )
    (tmp_path / ".evagix" / "context.json").write_text("manual json\n", encoding="utf-8")

    assert generation._cmd_sync_plan(tmp_path) == 0
    output = capsys.readouterr().out
    assert "Evagix sync plan" in output
    assert "Will create:" in output
    assert "Existing non-Evagix files" in output

    monkeypatch.setattr(generation, "apply_write_plan", lambda plan: (_ for _ in ()).throw(OSError("blocked")))
    assert generation._cmd_compile(tmp_path, target=None, dry_run=False, force=True) == 1
    assert "ERROR: blocked" in capsys.readouterr().err


def test_generation_init_baseline_init_ci_and_scoped_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "evagix.toml").write_text("profiles = ['python-backend']\n", encoding="utf-8")
    assert generation._cmd_init(tmp_path, force=False) == 1
    assert "already exists" in capsys.readouterr().err
    assert generation._cmd_baseline(tmp_path, force=False) == 1
    assert "already exists" in capsys.readouterr().err

    (tmp_path / "evagix.toml").unlink()
    assert generation._cmd_init(tmp_path, force=True, profiles=["missing-profile"]) == 2
    assert "Unknown profile" in capsys.readouterr().err
    monkeypatch.setattr(
        generation,
        "_doctor",
        lambda *args, **kwargs: (_facts(root_name="demo"), SimpleNamespace(), DoctorReport(score=100)),
    )
    assert generation._cmd_baseline(tmp_path, force=True, profiles=["missing-profile"]) == 2
    assert "Unknown profile" in capsys.readouterr().err

    original_build_write_plan = generation.build_write_plan
    monkeypatch.setattr(
        generation, "build_write_plan", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("unsafe path"))
    )
    assert generation._cmd_init(tmp_path, force=True, profiles=["python-backend"]) == 1
    assert "ERROR: unsafe path" in capsys.readouterr().err
    assert generation._cmd_baseline(tmp_path, force=True, profiles=["python-backend"]) == 1
    assert "ERROR: unsafe path" in capsys.readouterr().err

    monkeypatch.setattr(generation, "build_write_plan", original_build_write_plan)

    workflow = tmp_path / ".github" / "workflows" / "evagix.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: existing\n", encoding="utf-8")
    assert generation._cmd_init_ci(tmp_path, force=False) == 1
    assert "already exists" in capsys.readouterr().err
    workflow.unlink()
    assert generation._cmd_init_ci(tmp_path, force=True, install_mode="github", repo="not-a-slug") == 2
    assert "ERROR:" in capsys.readouterr().err

    monkeypatch.setattr(generation, "_facts", lambda *args, **kwargs: (_facts(root_name="demo"), SimpleNamespace()))
    monkeypatch.setattr(generation, "scoped_outputs", lambda facts: {})
    assert generation._cmd_scoped(tmp_path, dry_run=False, force=False) == 0
    assert "No scoped" in capsys.readouterr().out
