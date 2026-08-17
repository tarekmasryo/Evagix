from __future__ import annotations

from pathlib import Path

from scripts.verify_artifacts import (
    _isolated_pip_environment,
    _offline_toolchain_paths,
    _pip_install_command,
    _toolchain_upgrade_command,
)


def test_artifact_verifier_uses_invocation_local_pip_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PIP_CACHE_DIR", str(tmp_path / "protected-global-cache"))

    environment = _isolated_pip_environment(tmp_path / "verification")

    assert environment["PIP_CACHE_DIR"] == str(tmp_path / "verification" / "pip-cache")
    assert environment["PIP_DISABLE_PIP_VERSION_CHECK"] == "1"


def test_offline_artifact_install_is_index_and_cache_independent(tmp_path: Path) -> None:
    python = tmp_path / "python"

    command = _pip_install_command(python, offline=True)

    assert command == [
        python,
        "-m",
        "pip",
        "install",
        "--no-index",
        "--no-cache-dir",
        "--no-deps",
        "--no-build-isolation",
    ]


def test_online_artifact_install_keeps_normal_index_resolution(tmp_path: Path) -> None:
    python = tmp_path / "python"

    assert _pip_install_command(python, offline=False) == [python, "-m", "pip", "install"]


def test_artifact_verifier_applies_release_constraints(tmp_path: Path) -> None:
    constraints = tmp_path / "constraints-release.txt"
    constraints.write_text("setuptools==83.0.0\n", encoding="utf-8")

    environment = _isolated_pip_environment(tmp_path / "verification", constraints=constraints)

    assert environment["PIP_CONSTRAINT"] == str(constraints.resolve())
    assert _toolchain_upgrade_command(tmp_path / "python", constraints) == [
        tmp_path / "python",
        "-m",
        "pip",
        "install",
        "--upgrade",
        "-c",
        constraints.resolve(),
        "pip",
        "setuptools",
        "wheel",
    ]


def test_latest_toolchain_probe_is_explicitly_unconstrained(tmp_path: Path) -> None:
    python = tmp_path / "python"

    assert _toolchain_upgrade_command(python, None) == [
        python,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "pip",
        "setuptools",
        "wheel",
    ]


def test_offline_toolchain_uses_the_resolved_distribution_location(tmp_path: Path, monkeypatch) -> None:
    user_site = tmp_path / "user-site"
    user_site.mkdir()

    class Distribution:
        version = "83.0.0"

        def locate_file(self, path: str) -> Path:
            return user_site / path

    monkeypatch.setattr("scripts.verify_artifacts.metadata.distribution", lambda _name: Distribution())

    assert _offline_toolchain_paths() == [str(user_site.resolve())]
