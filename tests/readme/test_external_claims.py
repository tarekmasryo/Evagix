from __future__ import annotations

from pathlib import Path

from evagix.readme_audit import audit_readme
from evagix.scanner import scan_repo


def _write_python_package(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = []\n',
        encoding="utf-8",
    )
    package = root / "demo"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")


def test_published_package_claim_requires_external_review(tmp_path: Path) -> None:
    _write_python_package(tmp_path)
    (tmp_path / "README.md").write_text(
        "# Demo\n\nInstall the published package from PyPI.\n",
        encoding="utf-8",
    )

    report = audit_readme(tmp_path, scan_repo(tmp_path), strict=True)
    claim = next(item for item in report.claims if item.claim == "package-installable")

    assert claim.verdict == "manual_review_required"
    assert any("External package publication" in item for item in claim.missing_evidence)
    assert "public package page" in claim.suggestion
    assert claim.suggested_replacement == ""


def test_version_matrix_claim_requires_runtime_review(tmp_path: Path) -> None:
    _write_python_package(tmp_path)
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_demo.py").write_text("def test_demo():\n    assert True\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "# Demo\n\nTested on Python 3.11, 3.12, and 3.13.\n",
        encoding="utf-8",
    )

    report = audit_readme(tmp_path, scan_repo(tmp_path), strict=True)
    claim = next(item for item in report.claims if item.claim == "tested")

    assert claim.verdict == "manual_review_required"
    assert any("Runtime and platform test claims" in item for item in claim.missing_evidence)
    assert "successful CI run evidence" in claim.suggestion
    assert claim.suggested_replacement == ""


def test_general_test_claim_can_still_use_local_evidence(tmp_path: Path) -> None:
    _write_python_package(tmp_path)
    (tmp_path / "requirements-dev.txt").write_text("pytest\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_demo.py").write_text("def test_demo():\n    assert True\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Demo\n\nThis project is tested.\n", encoding="utf-8")

    report = audit_readme(tmp_path, scan_repo(tmp_path), strict=True)
    claim = next(item for item in report.claims if item.claim == "tested")

    assert claim.verdict == "supported"
