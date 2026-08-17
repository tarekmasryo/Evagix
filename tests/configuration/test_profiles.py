from pathlib import Path

from evagix.cli import main
from evagix.renderers import render_agents_md
from evagix.scanner import scan_repo


def test_init_does_not_force_python_backend_for_docs_only_repo(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")

    assert main(["init", str(tmp_path)]) == 0

    config = (tmp_path / "evagix.toml").read_text(encoding="utf-8")
    assert "profiles = []" in config
    assert "profiles = ['python-backend']" not in config


def test_init_infers_detected_profile_when_available(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("fastapi\npytest\n", encoding="utf-8")

    assert main(["init", str(tmp_path)]) == 0

    config = (tmp_path / "evagix.toml").read_text(encoding="utf-8")
    assert "'python-backend'" in config


def test_policy_profiles_are_inferred_for_rag_backend(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("fastapi\nlangchain\nqdrant-client\nsqlalchemy\n", encoding="utf-8")
    facts = scan_repo(tmp_path)
    assert "python-backend" in facts.active_profiles
    assert "ai-service" in facts.active_profiles
    rendered = render_agents_md(facts)
    assert "Active Policy Profiles" in rendered
    assert "AI / Retrieval Service" in rendered
    assert "Profile-Specific Rules" in rendered


def test_evagix_toml_profiles_are_persistent(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.1.0'\n", encoding="utf-8")
    (tmp_path / "evagix.toml").write_text("[profiles]\nprofiles = ['ai-service']\n", encoding="utf-8")
    facts = scan_repo(tmp_path)
    assert "ai-service" in facts.active_profiles
