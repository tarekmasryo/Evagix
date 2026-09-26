from __future__ import annotations

import json
import shlex
import shutil
from pathlib import Path

import pytest

from evagix.cli import main

ROOT = Path(__file__).resolve().parents[2]


def _published_doctor_arguments() -> list[str]:
    manifest = (ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8")
    doctor = manifest.split("- id: evagix-doctor\n", 1)[1].split("\n- id:", 1)[0]
    entry = next(
        line.strip().removeprefix("entry: ") for line in doctor.splitlines() if line.strip().startswith("entry: ")
    )
    arguments = shlex.split(entry)
    assert arguments[:2] == ["evagix", "doctor"]
    assert "--strict" in arguments
    return arguments[1:]


@pytest.mark.parametrize(
    ("configured", "override", "expected_threshold", "expected_exit"),
    [(100, None, 100, 1), (100, 80, 80, 0), (80, 100, 100, 1)],
    ids=["hook-respects-project-100", "explicit-cli-lowers-threshold", "explicit-cli-raises-threshold"],
)
def test_doctor_hook_and_explicit_cli_threshold_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    configured: int,
    override: int | None,
    expected_threshold: int,
    expected_exit: int,
) -> None:
    shutil.copytree(ROOT / "tests/fixtures/basic-python", tmp_path, dirs_exist_ok=True)
    (tmp_path / "evagix.toml").write_text(f"[policy]\nfail_under = {configured}\n", encoding="utf-8")
    assert main(["compile", str(tmp_path)]) == 0
    capsys.readouterr()
    monkeypatch.chdir(tmp_path)

    arguments = (
        _published_doctor_arguments() if override is None else ["doctor", "--strict", "--fail-under", str(override)]
    )
    result = main([*arguments, "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert 80 < payload["score"] < 100
    assert all(finding["severity"] != "error" for finding in payload["findings"])
    assert payload["fail_under"] == expected_threshold
    assert result == expected_exit
    assert payload["ok"] is (expected_exit == 0)
