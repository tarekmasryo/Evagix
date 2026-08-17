from __future__ import annotations

import json
from pathlib import Path

import pytest
from pytest import CaptureFixture

from evagix.cli import main


def _minimal_repo(root: Path) -> None:
    (root / "README.md").write_text("# Demo\n\nPython package with tests.\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["pytest", "ruff"]\n',
        encoding="utf-8",
    )
    (root / "tests").mkdir()


def _make_configured_repo(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["pytest", "ruff"]\n',
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    (root / "evagix.toml").write_text(
        "\n".join(
            [
                "[policy]",
                "fail_under = 80",
                "fail_on_stale = true",
                "",
                "[commands]",
                'test = "python -m pytest"',
                'lint = "python -m ruff check ."',
                "",
                "[targets]",
                "universal_md = true",
                "universal_json = true",
                "agents = true",
                "claude = true",
            ]
        ),
        encoding="utf-8",
    )


def test_drift_reports_in_sync_when_no_evagix_managed_targets_exist(tmp_path: Path) -> None:
    _minimal_repo(tmp_path)
    output = tmp_path / "drift.json"
    assert main(["drift", str(tmp_path), "--format", "json", "-o", output.name]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["report_type"] == "drift"
    assert payload["status"] == "in-sync"
    assert payload["missing_targets"] == []


def test_drift_passes_after_sync(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    _minimal_repo(tmp_path)
    assert main(["sync", str(tmp_path)]) == 0
    assert main(["drift", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Status: `in-sync`" in out
    assert "No generated Evagix drift detected" in out


def test_eval_context_detects_stale_generated_context(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _make_configured_repo(tmp_path)
    assert main(["compile", str(tmp_path)]) == 0
    capsys.readouterr()

    config = tmp_path / "evagix.toml"
    config.write_text(
        config.read_text(encoding="utf-8").replace("python -m pytest", "python -m pytest -q"), encoding="utf-8"
    )

    assert main(["eval-context", str(tmp_path), "--strict", "--fail-under", "80", "--format", "json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    evaluation = payload["evaluation"]
    assert evaluation["ok"] is False
    assert evaluation["score"] < 80
    assert any(item["id"] == "generated-context-drift" for item in evaluation["findings"])
    drift = next(item for item in evaluation["findings"] if item["id"] == "generated-context-drift")
    assert set(drift["metadata"]["affected_targets"]) >= {".evagix/context.md", ".evagix/context.json"}


def test_doctor_groups_generated_context_drift(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _make_configured_repo(tmp_path)
    assert main(["compile", str(tmp_path)]) == 0
    capsys.readouterr()

    config = tmp_path / "evagix.toml"
    config.write_text(
        config.read_text(encoding="utf-8").replace("python -m pytest", "python -m pytest -q"), encoding="utf-8"
    )

    assert main(["doctor", str(tmp_path), "--strict", "--format", "json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    codes = [item["code"] for item in payload["findings"]]
    assert codes.count("generated-context-drift") == 1
    assert "stale-target" not in codes
    message = next(item["message"] for item in payload["findings"] if item["code"] == "generated-context-drift")
    assert ".evagix/context.md" in message
    assert "AGENTS.md" in message
