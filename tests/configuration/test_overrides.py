from __future__ import annotations

import json
from pathlib import Path

from pytest import CaptureFixture

from evagix.cli import main


def test_config_command_overrides_replace_detected_commands(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["pytest", "ruff"]\n',
        encoding="utf-8",
    )
    (tmp_path / "evagix.toml").write_text(
        '[commands]\ntest = "make ci-test"\nlint = "make ci-lint"\n',
        encoding="utf-8",
    )
    assert main(["scan", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["commands"]["test"] == "make ci-test"
    assert payload["commands"]["lint"] == "make ci-lint"
    assert payload["command_sources"]["test"]["source"] == "evagix.toml"


def test_config_ignored_paths_reduce_nested_node_noise(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    archived = tmp_path / "archive" / "web"
    archived.mkdir(parents=True)
    (archived / "package.json").write_text(
        '{"scripts":{"test":"vitest"},"dependencies":{"react":"latest"},"devDependencies":{"vite":"latest"}}',
        encoding="utf-8",
    )
    (tmp_path / "evagix.toml").write_text('[ignore]\npaths = ["archive/"]\n', encoding="utf-8")
    assert main(["scan", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "javascript/typescript" not in payload["languages"]
    assert not payload["subprojects"]
    assert not payload["commands"]


def test_config_ignored_paths_apply_to_top_level_scanners(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["pytest", "ruff"]\n',
        encoding="utf-8",
    )
    (tmp_path / "Makefile").write_text("test:\n\tpytest\n", encoding="utf-8")
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: CI\n", encoding="utf-8")
    (tmp_path / "evagix.toml").write_text(
        '[ignore]\npaths = ["pyproject.toml", "Makefile", ".github/"]\n',
        encoding="utf-8",
    )

    assert main(["scan", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert "python" not in payload["languages"]
    assert "pyproject.toml" not in payload["config_files"]
    assert payload["commands"] == {}
    assert payload["ci_workflows"] == []


def test_config_readme_audit_ignore_claims(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\nEnterprise-ready secure platform.\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8")
    (tmp_path / "evagix.toml").write_text(
        '[readme_audit]\nignore_claims = ["production-ready", "secure"]\n',
        encoding="utf-8",
    )
    assert main(["readme-audit", str(tmp_path), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert {item["claim"] for item in payload["waived_claims"]} == {"production-ready", "secure"}
    assert all(item["verdict"] == "waived" for item in payload["claims"])
    assert payload["score"] < 100


def test_policy_prints_config_overrides(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    (tmp_path / "evagix.toml").write_text(
        '[commands]\ntest = "make test"\n[ignore]\npaths = ["vendor/"]\n[readme_audit]\nignore_claims = ["secure"]\n',
        encoding="utf-8",
    )
    assert main(["policy", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Custom commands" in out
    assert "vendor/" in out
    assert "secure" in out


def test_invalid_config_fail_under_is_reported(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    (tmp_path / "evagix.toml").write_text("[policy]\nfail_under = 150\n", encoding="utf-8")

    assert main(["policy", str(tmp_path), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["fail_under"] == 80
    assert "policy.fail_under must be an integer from 0 to 100" in payload["parse_error"]


def test_policy_exposes_require_onboarding_pack(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    (tmp_path / "evagix.toml").write_text("[policy]\nrequire_onboarding_pack = true\n", encoding="utf-8")
    assert main(["policy", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["require_onboarding_pack"] is True
