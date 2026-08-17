from __future__ import annotations

import json
import subprocess
from pathlib import Path

from evagix.changes import (
    build_changed_report,
    render_changed_github_annotations,
    render_changed_json,
    render_changed_text,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def test_changed_report_classifies_high_and_low_risk_files(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")
    _git(tmp_path, "branch", "-M", "main")

    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: CI\n", encoding="utf-8")
    tests = tmp_path / "tests" / "test_demo.py"
    tests.parent.mkdir()
    tests.write_text("def test_demo():\n    assert True\n", encoding="utf-8")

    report = build_changed_report(tmp_path, base="main")

    by_path = {item.path: item for item in report.files}
    assert by_path[".github/workflows/ci.yml"].risk == "HIGH"
    assert by_path["tests/test_demo.py"].risk == "LOW"
    assert "workflow review" in report.required_gates
    assert "evagix doctor" in report.required_gates


def test_changed_renderers_are_machine_and_ci_friendly(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")
    _git(tmp_path, "branch", "-M", "main")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")

    report = build_changed_report(tmp_path, base="main")
    text = render_changed_text(report)
    payload = json.loads(render_changed_json(report))
    annotations = render_changed_github_annotations(report)

    assert "pyproject.toml" in text
    assert payload["has_high_risk"] is True
    assert "::error file=pyproject.toml" in annotations


def test_changed_report_suggests_existing_branch_when_base_is_missing(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")
    _git(tmp_path, "branch", "-M", "master")

    try:
        build_changed_report(tmp_path, base="main")
    except RuntimeError as exc:
        message = str(exc)
    else:  # pragma: no cover - defensive guard for unexpected git behavior
        raise AssertionError("expected missing base ref to fail")

    assert "Base ref `main` was not found" in message
    assert "Try: --base master" in message


def test_documentation_tests_and_examples_override_sensitive_path_keywords() -> None:
    from evagix.changes import _classify_changed_path

    for path in [
        "docs/security/auth.md",
        "tests/migrations/test_001.py",
        "examples/deploy/demo.yml",
    ]:
        result = _classify_changed_path(path)
        assert result.risk == "LOW", path
        assert result.reason == "documentation, tests, or examples"


def test_git_nul_output_preserves_newline_in_file_name(tmp_path: Path) -> None:
    import os

    import pytest

    if os.name == "nt":
        pytest.skip("Windows does not support this repository filename fixture")

    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")
    _git(tmp_path, "branch", "-M", "main")

    unusual = "odd\nname.py"
    (tmp_path / unusual).write_text("print('safe')\n", encoding="utf-8")

    report = build_changed_report(tmp_path, base="main")

    assert [item.path for item in report.files] == [unusual]


def test_git_nul_output_handles_non_utf8_file_name_bytes(tmp_path: Path) -> None:
    import errno
    import os

    import pytest

    if os.name == "nt":
        pytest.skip("Windows does not support this repository filename fixture")

    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")
    _git(tmp_path, "branch", "-M", "main")

    raw_path = os.fsencode(tmp_path) + b"/odd-\xff.py"
    try:
        descriptor = os.open(
            raw_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except OSError as exc:
        if exc.errno == errno.EILSEQ:
            pytest.skip("Filesystem rejects the non-UTF-8 filename byte fixture")
        raise
    try:
        os.write(descriptor, b"print('safe')\n")
    finally:
        os.close(descriptor)

    report = build_changed_report(tmp_path, base="main")

    assert [item.path for item in report.files] == ["odd-\ufffd.py"]
    assert json.loads(render_changed_json(report))["files"][0]["path"] == "odd-\ufffd.py"
