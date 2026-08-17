from __future__ import annotations

import json
from pathlib import Path

from evagix.cli import main


def test_evidence_ledger_records_checked_claims_even_without_findings(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "README.md").write_text("# Demo\n\nThis project is tested.\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_demo.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="demo"\nversion="0.0.0"\n[project.optional-dependencies]\ndev=["pytest"]\n', encoding="utf-8"
    )
    (tmp_path / "evagix.toml").write_text('[commands]\ntest = "pytest"\n', encoding="utf-8")
    assert main(["evidence", str(tmp_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["claims_checked"] >= 1
    assert payload["summary"]["supported"] >= 1
    assert payload["claims"]
    assert "findings" in payload


def test_strict_audit_fail_flags(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\nDocker supported.\n", encoding="utf-8")
    assert main(["readme-audit", str(tmp_path), "--strict", "--fail-on", "unsupported"]) == 1


def test_evidence_force_without_output_is_error(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    assert main(["evidence", str(tmp_path), "--force"]) == 1
    assert not (tmp_path / ".evagix" / "evidence.json").exists()


def test_evidence_ledger_includes_detected_agent_context_files(tmp_path: Path, capsys) -> None:
    import json

    (tmp_path / "AGENTS.md").write_text("# Agent context\n\nRun tests with `pytest`.\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# Claude\n\nDo not reveal secrets.\n", encoding="utf-8")
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "copilot-instructions.md").write_text("Use project evidence.", encoding="utf-8")

    assert main(["evidence", str(tmp_path), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    required = {"AGENTS.md", "CLAUDE.md", ".github/copilot-instructions.md"}
    paths = {item.get("path") for item in payload["agent_context"]}
    assert required.issubset(paths)
    indexed = {item.get("path"): item for item in payload["agent_context"] if item.get("path") in required}
    assert all(indexed[path].get("type") == "agent_context_file" for path in required)
