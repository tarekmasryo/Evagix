from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from evagix.changes import (
    ChangedFileRisk,
    ChangedReport,
    _classify_changed_path,
    _git_changed_files,
    _required_gates,
    render_changed_github_annotations,
    render_changed_text,
)
from evagix.cli import main


def test_changed_renderers_handle_empty_reports() -> None:
    report = ChangedReport(base="main", files=[], required_gates=["evagix check"])
    assert "No changed files detected" in render_changed_text(report)
    assert "::notice title=Evagix changed-file risk::No changed files detected" in render_changed_github_annotations(
        report
    )


def test_changed_path_classifier_covers_risk_edges() -> None:
    assert _classify_changed_path("").reason == "empty path"
    assert _classify_changed_path("migrations/001_init.py").risk == "HIGH"
    assert (
        _classify_changed_path("auth/login.py").reason
        == "security, auth, billing, permissions, or deployment-sensitive path"
    )
    assert _classify_changed_path("app/auth/security.py").risk == "HIGH"
    assert _classify_changed_path("src/security/tokens.py").risk == "HIGH"
    assert _classify_changed_path("backend/payments/service.py").risk == "HIGH"
    assert _classify_changed_path("docker-compose.yml").reason == "container or runtime orchestration change"
    assert _classify_changed_path("config/.env.local").reason == "secret-bearing or environment-sensitive path"
    assert _classify_changed_path("evagix.toml").risk == "MEDIUM"
    assert _classify_changed_path("src/app.py").risk == "MEDIUM"
    assert _classify_changed_path("docs/usage.md").risk == "LOW"


def test_changed_required_gates_cover_no_files_python_and_tests() -> None:
    assert _required_gates([]) == ["evagix check"]
    gates = _required_gates(
        [
            ChangedFileRisk(path="evagix/cli.py", risk="MEDIUM", reason="source"),
            ChangedFileRisk(path="tests/test_cli.py", risk="LOW", reason="tests"),
        ]
    )
    assert gates == ["evagix check", "ruff check .", "mypy .", "pytest"]


def test_changed_required_gates_use_configured_commands() -> None:
    gates = _required_gates(
        [ChangedFileRisk(path="evagix/cli.py", risk="MEDIUM", reason="source")],
        commands={
            "lint": "python -m ruff check .",
            "typecheck": "python -m mypy evagix",
            "test": "python -m pytest",
        },
    )

    assert gates == [
        "evagix check",
        "python -m ruff check .",
        "python -m mypy evagix",
        "python -m pytest",
    ]
    assert "mypy ." not in gates


def test_changed_cli_uses_evagix_toml_command_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["pytest", "ruff", "mypy"]\n',
        encoding="utf-8",
    )
    (tmp_path / "evagix.toml").write_text(
        '[commands]\ntest = "python -m pytest"\nlint = "python -m ruff check ."\ntypecheck = "python -m mypy evagix"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "evagix.changes._git_changed_files",
        lambda root, base, head="HEAD": ["evagix/cli.py"],
    )

    assert main(["changed", str(tmp_path), "--base", "main"]) == 0
    output = capsys.readouterr().out

    assert "python -m ruff check ." in output
    assert "python -m mypy evagix" in output
    assert "python -m pytest" in output
    assert "  - mypy ." not in output


def test_changed_git_errors_are_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FailedProcess:
        returncode = 1
        stdout = ""
        stderr = "fatal: bad revision"

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FailedProcess())
    with pytest.raises(RuntimeError, match="Could not inspect changed files"):
        _git_changed_files(tmp_path, "missing-base")


def test_changed_rejects_git_option_like_refs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="base ref contains unsafe characters"):
        _git_changed_files(tmp_path, "--output=/tmp/evagix-pwned")
    with pytest.raises(ValueError, match="head ref contains unsafe characters"):
        _git_changed_files(tmp_path, "main", head="--output=/tmp/evagix-pwned")


def test_changed_cli_rejects_git_option_injection_without_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "evagix-option-injected"
    result = main(["changed", str(tmp_path), f"--base=--output={output}"])
    captured = capsys.readouterr()
    assert result == 1
    assert "base ref contains unsafe characters" in captured.err
    assert not output.exists()
    assert not Path(f"{output}...HEAD").exists()


def test_pr_risk_cli_rejects_git_option_injection_without_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "evagix-pr-option-injected"
    result = main(["pr-risk", str(tmp_path), f"--base=--output={output}"])
    captured = capsys.readouterr()
    assert result == 1
    assert "base ref contains unsafe characters" in captured.err
    assert not output.exists()
    assert not Path(f"{output}...HEAD").exists()
