from __future__ import annotations

import runpy
import sys
import tomllib
from pathlib import Path

import pytest
from pytest import CaptureFixture

from evagix.cli import main


def test_check_help_clarifies_scope(capsys: CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["check", "--help"])

    captured = capsys.readouterr()
    assert exc.value.code == 0
    assert "generated context freshness" in captured.out
    assert "self-governance" in captured.out


def test_preview_and_fix_messages_do_not_hardcode_release_version(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["prepare", str(tmp_path)]) == 2
    assert "v0.1.0" not in capsys.readouterr().err

    assert main(["fix", str(tmp_path), "--plan"]) == 0
    assert "v0.1.0" not in capsys.readouterr().out


def test_cli_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "evagix 0.1.1" in capsys.readouterr().out


def test_short_cli_alias_is_registered() -> None:
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    scripts = metadata["project"]["scripts"]
    assert scripts["evagix"] == "evagix.cli:main"
    assert scripts["evgx"] == "evagix.cli:main"


def test_python_module_entrypoint_prints_help(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["evagix", "--help"])
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("evagix", run_name="__main__")
    assert excinfo.value.code == 0
    assert "Build, validate, and govern" in capsys.readouterr().out


def test_cli_explain_smoke(capsys: CaptureFixture[str]):
    assert main(["explain", "missing-ci"]) == 0
    out = capsys.readouterr().out
    assert "No CI workflow" in out


def test_unknown_profile_returns_clean_error(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["compile", str(tmp_path), "--profile", "not-a-profile"])

    captured = capsys.readouterr()
    assert exc.value.code == 2
    assert "Unknown profile" in captured.err
    assert "Traceback" not in captured.err
