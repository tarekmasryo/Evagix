from __future__ import annotations

import stat
import warnings
import zipfile
from pathlib import Path

import pytest

from scripts.verify_source_archive import _validate_member, verify_source_archive


def _write_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)


def test_clean_source_archive_is_accepted(tmp_path: Path) -> None:
    archive = tmp_path / "source.zip"
    _write_zip(
        archive,
        {
            "evagix-0.1.0/README.md": b"# Evagix\n",
            "evagix-0.1.0/pyproject.toml": b"[project]\nname='evagix'\n",
            "evagix-0.1.0/LICENSE": b"Apache-2.0\n",
            "evagix-0.1.0/evagix/__init__.py": b"__version__ = '0.1.0'\n",
            "evagix-0.1.0/evagix/schemas/readme-audit.schema.json": b"{}\n",
        },
    )

    assert verify_source_archive(archive) == 5


def test_incomplete_project_archive_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "source.zip"
    _write_zip(archive, {"evagix-0.1.0/README.md": b"# Evagix\n"})

    with pytest.raises(ValueError, match="missing required project files"):
        verify_source_archive(archive)


def test_archive_must_match_expected_git_tree_files(tmp_path: Path) -> None:
    archive = tmp_path / "source.zip"
    members = {
        "evagix-0.1.0/README.md": b"# Evagix\n",
        "evagix-0.1.0/pyproject.toml": b"[project]\nname='evagix'\n",
        "evagix-0.1.0/LICENSE": b"Apache-2.0\n",
        "evagix-0.1.0/evagix/__init__.py": b"__version__ = '0.1.0'\n",
        "evagix-0.1.0/evagix/schemas/readme-audit.schema.json": b"{}\n",
    }
    _write_zip(archive, members)
    expected = {name.removeprefix("evagix-0.1.0/") for name in members}

    assert verify_source_archive(archive, expected_files=expected, expected_prefix="evagix-0.1.0/") == 5
    with pytest.raises(ValueError, match="does not match the expected Git tree"):
        verify_source_archive(
            archive,
            expected_files={*expected, "CHANGELOG.md"},
            expected_prefix="evagix-0.1.0/",
        )


def test_archive_must_match_expected_git_tree_content(tmp_path: Path) -> None:
    archive = tmp_path / "source.zip"
    members = {
        "evagix-0.1.0/README.md": b"# Evagix\n",
        "evagix-0.1.0/pyproject.toml": b"[project]\nname='evagix'\n",
        "evagix-0.1.0/LICENSE": b"Apache-2.0\n",
        "evagix-0.1.0/evagix/__init__.py": b"__version__ = '0.1.0'\n",
        "evagix-0.1.0/evagix/schemas/readme-audit.schema.json": b"{}\n",
    }
    _write_zip(archive, members)
    expected_contents = {name.removeprefix("evagix-0.1.0/"): content for name, content in members.items()}

    assert (
        verify_source_archive(
            archive,
            expected_files=set(expected_contents),
            expected_contents=expected_contents,
            expected_prefix="evagix-0.1.0/",
        )
        == 5
    )

    tampered = dict(members)
    tampered["evagix-0.1.0/README.md"] = b"# Tampered\n"
    _write_zip(archive, tampered)
    with pytest.raises(ValueError, match="content does not match"):
        verify_source_archive(
            archive,
            expected_files=set(expected_contents),
            expected_contents=expected_contents,
            expected_prefix="evagix-0.1.0/",
        )


@pytest.mark.parametrize(
    "member",
    [
        "evagix-0.1.0/.ruff_cache/state.json",
        "evagix-0.1.0/evagix/__pycache__/module.pyc",
        "evagix-0.1.0/evagix.egg-info/PKG-INFO",
        "../outside.txt",
        "C:/outside.txt",
    ],
)
def test_generated_or_unsafe_paths_are_rejected(tmp_path: Path, member: str) -> None:
    archive = tmp_path / "source.zip"
    _write_zip(archive, {member: b"unsafe"})

    with pytest.raises(ValueError):
        verify_source_archive(archive)


def test_windows_style_archive_path_is_rejected() -> None:
    info = zipfile.ZipInfo("safe-name")
    info.filename = "evagix-0.1.0\\README.md"

    with pytest.raises(ValueError, match="Unsafe archive path"):
        _validate_member(info, set())


def test_duplicate_entries_are_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "source.zip"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("evagix-0.1.0/README.md", b"first")
            output.writestr("evagix-0.1.0/README.md", b"second")

    with pytest.raises(ValueError, match="Duplicate"):
        verify_source_archive(archive)


def test_symbolic_link_entries_are_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "source.zip"
    link = zipfile.ZipInfo("evagix-0.1.0/README.md")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(link, "target.md")

    with pytest.raises(ValueError, match="Symbolic links"):
        verify_source_archive(archive)
