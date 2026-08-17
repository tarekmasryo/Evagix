from __future__ import annotations

from pathlib import Path

from evagix.cli import main


def test_sync_generates_and_checks_agent_files(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["pytest", "ruff"]\n',
        encoding="utf-8",
    )
    assert main(["sync", str(tmp_path)]) == 0
    assert (tmp_path / ".evagix" / "context.md").exists()
    assert main(["check", str(tmp_path)]) == 0


def test_sync_preserves_cli_profile_during_check(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["pytest", "ruff"]\n',
        encoding="utf-8",
    )

    assert main(["sync", str(tmp_path), "--profile", "ai-service"]) == 0
    assert main(["check", str(tmp_path), "--profile", "ai-service"]) == 0


def test_generated_content_normalization_accepts_crlf_line_endings() -> None:
    from evagix.utils import normalize_generated_content

    assert normalize_generated_content("a\r\nb\r\n") == "a\nb\n"
    assert normalize_generated_content("a\rb\r") == "a\nb\n"
