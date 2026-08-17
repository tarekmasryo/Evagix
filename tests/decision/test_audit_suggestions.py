from pathlib import Path

from evagix.scanner import scan_repo
from evagix.validators import audit_repo, suggest_actions


def test_audit_and_suggestions(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("fastapi\nlangchain\n", encoding="utf-8")
    facts = scan_repo(tmp_path)
    audit = audit_repo(tmp_path, facts)
    assert any(item.code == "llm-eval-gap" for item in audit)
    suggestions = suggest_actions(tmp_path, facts)
    assert suggestions
