from __future__ import annotations

from pathlib import Path

import pytest
from pytest import CaptureFixture

from evagix.cli import main


def test_scan_rejects_missing_repository_path(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    missing = tmp_path / "does-not-exist"

    with pytest.raises(SystemExit) as excinfo:
        main(["scan", str(missing)])

    assert excinfo.value.code == 1
    assert "repository path does not exist" in capsys.readouterr().err


def test_compile_rejects_missing_repository_path(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    missing = tmp_path / "does-not-exist"

    with pytest.raises(SystemExit) as excinfo:
        main(["compile", str(missing), "--dry-run"])

    assert excinfo.value.code == 1
    assert "repository path does not exist" in capsys.readouterr().err


def test_scan_rejects_file_path(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    file_path = tmp_path / "README.md"
    file_path.write_text("# Demo\n", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        main(["scan", str(file_path)])

    assert excinfo.value.code == 1
    assert "repository path is not a directory" in capsys.readouterr().err


def test_init_ci_rejects_shell_injection_in_repo(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    result = main(["init-ci", str(tmp_path), "--repo", 'owner/repo"; echo INJECTED #', "--ref", "v0.1.0"])

    assert result == 2
    assert "repo must be a GitHub slug" in capsys.readouterr().err
    assert not (tmp_path / ".github" / "workflows" / "evagix.yml").exists()


def test_init_ci_rejects_shell_injection_in_ref(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    result = main(["init-ci", str(tmp_path), "--repo", "owner/repo", "--ref", 'v0.1.0"; echo INJECTED #'])

    assert result == 2
    assert "ref contains unsafe characters" in capsys.readouterr().err
    assert not (tmp_path / ".github" / "workflows" / "evagix.yml").exists()


def test_init_ci_rejects_shell_injection_in_package_version(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    result = main(["init-ci", str(tmp_path), "--install-mode", "pypi", "--package-version", '0.1.0"; echo INJECTED #'])

    assert result == 2
    assert "package version contains unsafe characters" in capsys.readouterr().err
    assert not (tmp_path / ".github" / "workflows" / "evagix.yml").exists()


def test_init_ci_accepts_safe_github_url_and_ref(tmp_path: Path) -> None:
    result = main(["init-ci", str(tmp_path), "--repo", "https://github.com/owner/repo.git", "--ref", "release/v0.1.0"])

    assert result == 0
    workflow = (tmp_path / ".github" / "workflows" / "evagix.yml").read_text(encoding="utf-8")
    assert "python -m pip install git+https://github.com/owner/repo.git@release/v0.1.0" in workflow
    assert "INJECTED" not in workflow


def test_doctor_rejects_negative_fail_under(capsys: CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["doctor", ".", "--fail-under", "-1"])

    assert excinfo.value.code == 2
    assert "--fail-under must be between 0 and 100" in capsys.readouterr().err


def test_init_ci_rejects_out_of_range_fail_under(capsys: CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["init-ci", ".", "--fail-under", "101"])

    assert excinfo.value.code == 2
    assert "--fail-under must be between 0 and 100" in capsys.readouterr().err
