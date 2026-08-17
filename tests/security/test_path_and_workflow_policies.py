from __future__ import annotations

from pathlib import Path

import pytest

from evagix.safety import EvagixSafetyError, RepositoryPathPolicy, WorkflowInstallInputPolicy


def test_repository_path_policy_normalizes_existing_directory(tmp_path: Path) -> None:
    assert RepositoryPathPolicy().normalize(tmp_path) == tmp_path.resolve()


def test_repository_path_policy_resolves_symlinked_root(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    link = tmp_path / "repository-link"
    try:
        link.symlink_to(repository, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"directory symlinks are not available in this environment: {exc}")

    assert RepositoryPathPolicy().normalize(link) == repository.resolve()


def test_repository_path_policy_rejects_missing_path(tmp_path: Path) -> None:
    with pytest.raises(EvagixSafetyError, match="does not exist"):
        RepositoryPathPolicy().normalize(tmp_path / "missing")


def test_repository_path_policy_rejects_file_path(tmp_path: Path) -> None:
    file_path = tmp_path / "README.md"
    file_path.write_text("# Demo\n", encoding="utf-8")

    with pytest.raises(EvagixSafetyError, match="not a directory"):
        RepositoryPathPolicy().normalize(file_path)


def test_workflow_policy_rejects_unsafe_repo_ref_and_package_version() -> None:
    policy = WorkflowInstallInputPolicy()

    with pytest.raises(EvagixSafetyError):
        policy.install_command("github", repo='owner/repo"; echo INJECTED #', ref="v0.1.0")
    with pytest.raises(EvagixSafetyError):
        policy.install_command("github", repo="owner/repo", ref='v0.1.0"; echo INJECTED #')
    with pytest.raises(EvagixSafetyError):
        policy.install_command("pypi", package_version='0.1.0"; echo INJECTED #')


def test_workflow_policy_renders_deterministic_safe_install_commands() -> None:
    policy = WorkflowInstallInputPolicy()

    assert policy.install_command("github", repo="https://github.com/owner/repo.git", ref="release/v0.1.0") == (
        "python -m pip install git+https://github.com/owner/repo.git@release/v0.1.0"
    )
    assert policy.install_command("pypi", package_version="0.1.0") == "python -m pip install evagix==0.1.0"
    assert policy.install_command("editable") == "python -m pip install -e ."
