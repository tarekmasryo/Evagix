from __future__ import annotations

import json
from pathlib import Path

from pytest import CaptureFixture

from evagix.cli import main


def test_readme_audit_suggests_python_install_replacement(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n\n```bash\nnpm install\nnpm test\n```\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["pytest"]\n',
        encoding="utf-8",
    )
    assert main(["readme-audit", str(tmp_path), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    command_claims = [item for item in payload["claims"] if item["claim"] == "readme-command"]
    assert command_claims
    assert any(item["phrase"] == "npm install" for item in command_claims)
    assert any("python -m pip" in item["suggested_replacement"] for item in command_claims)


def test_readme_audit_markdown_includes_suggested_fix(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\nEnterprise-ready secure platform.\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8")
    assert main(["readme-audit", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Suggested README fix" in out
    assert "production-oriented" in out or "security-conscious" in out


def test_readme_audit_does_not_treat_llm_prompt_wording_as_rag_claim(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\nThis tool exports context for LLM prompts.\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8")
    assert main(["readme-audit", str(tmp_path), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item for item in payload["claims"] if item["claim"] == "ai/llm"] == []


def test_doctor_penalizes_unsupported_readme_claims(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\nDocker Compose support.\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="demo"\ndependencies=["pytest", "ruff"]\n', encoding="utf-8"
    )

    assert main(["doctor", str(tmp_path), "--format", "json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    codes = {item["code"] for item in payload["findings"]}
    assert "readme-unsupported-claims" in codes
    assert payload["score"] < 100
