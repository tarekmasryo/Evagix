from __future__ import annotations

import argparse
import io
import re
import stat
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

FORBIDDEN_COMPONENTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
}
FORBIDDEN_FILES = {".coverage"}
WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
REQUIRED_PROJECT_FILES = {
    "LICENSE",
    "README.md",
    "evagix/__init__.py",
    "pyproject.toml",
}


def _validate_member(info: zipfile.ZipInfo, seen: set[str]) -> None:
    name = info.filename
    if not name or name in seen:
        raise ValueError(f"Duplicate or empty archive entry: {name!r}")
    seen.add(name)

    if "\\" in name or name.startswith(("/", "\\")) or WINDOWS_DRIVE.match(name):
        raise ValueError(f"Unsafe archive path: {name}")
    path = PurePosixPath(name)
    if any(component in {"", ".", ".."} for component in path.parts):
        raise ValueError(f"Unsafe archive path: {name}")

    normalized = [component.casefold() for component in path.parts]
    if any(component in FORBIDDEN_COMPONENTS or component.endswith(".egg-info") for component in normalized):
        raise ValueError(f"Forbidden generated/cache path in source archive: {name}")
    if normalized[-1] in FORBIDDEN_FILES or normalized[-1].endswith((".pyc", ".pyo")):
        raise ValueError(f"Forbidden generated/cache file in source archive: {name}")

    unix_mode = info.external_attr >> 16
    if stat.S_IFMT(unix_mode) == stat.S_IFLNK:
        raise ValueError(f"Symbolic links are not allowed in the source archive: {name}")


def _normalized_prefix(infos: list[zipfile.ZipInfo], expected_prefix: str | None) -> str:
    if expected_prefix is not None:
        prefix = expected_prefix.rstrip("/") + "/"
        if "\\" in prefix or prefix.startswith(("/", "\\")) or ".." in PurePosixPath(prefix).parts:
            raise ValueError(f"Unsafe expected archive prefix: {expected_prefix}")
        return prefix
    roots = {PurePosixPath(info.filename).parts[0] for info in infos if PurePosixPath(info.filename).parts}
    if len(roots) != 1:
        raise ValueError("Source archive must contain exactly one top-level project directory")
    return next(iter(roots)) + "/"


def _project_files(infos: list[zipfile.ZipInfo], prefix: str) -> set[str]:
    files: set[str] = set()
    for info in infos:
        name = info.filename
        if name == prefix and info.is_dir():
            continue
        if not name.startswith(prefix):
            raise ValueError(f"Archive entry is outside the expected project prefix {prefix!r}: {name}")
        if info.is_dir():
            continue
        relative = name.removeprefix(prefix)
        if not relative:
            raise ValueError(f"Archive contains an empty project-relative file path: {name}")
        files.add(relative)
    return files


def _validate_project_completeness(files: set[str]) -> None:
    missing = sorted(REQUIRED_PROJECT_FILES - files)
    if missing:
        raise ValueError("Source archive is missing required project files: " + ", ".join(missing))
    if not any(name.startswith("evagix/schemas/") and name.endswith(".json") for name in files):
        raise ValueError("Source archive is missing required project files: evagix/schemas/*.json")


def _validate_expected_files(files: set[str], expected_files: set[str]) -> None:
    if files == expected_files:
        return
    missing = sorted(expected_files - files)
    unexpected = sorted(files - expected_files)
    details: list[str] = []
    if missing:
        details.append("missing: " + ", ".join(missing[:5]))
    if unexpected:
        details.append("unexpected: " + ", ".join(unexpected[:5]))
    raise ValueError("Source archive does not match the expected Git tree (" + "; ".join(details) + ")")


def _validate_expected_contents(
    archive: zipfile.ZipFile,
    infos: list[zipfile.ZipInfo],
    prefix: str,
    expected_contents: dict[str, bytes],
) -> None:
    mismatched: list[str] = []
    for info in infos:
        if info.is_dir() or not info.filename.startswith(prefix):
            continue
        relative = info.filename.removeprefix(prefix)
        expected = expected_contents.get(relative)
        if expected is None:
            continue
        if archive.read(info) != expected:
            mismatched.append(relative)
    if mismatched:
        raise ValueError(
            "Source archive file content does not match the expected Git revision: " + ", ".join(sorted(mismatched)[:5])
        )


def _git_tracked_contents(repository: Path, revision: str) -> dict[str, bytes]:
    result = subprocess.run(
        ["git", "-C", str(repository), "archive", "--format=tar", revision],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        error = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"Could not read expected files from Git revision {revision!r}: {error}")

    contents: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
            for member in archive.getmembers():
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError(f"Git revision {revision!r} contains a non-regular archive entry: {member.name}")
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise ValueError(f"Could not read Git archive entry: {member.name}")
                contents[member.name] = extracted.read()
    except tarfile.TarError as exc:
        raise ValueError(f"Could not parse Git archive for revision {revision!r}") from exc
    return contents


def verify_source_archive(
    archive_path: Path,
    *,
    expected_files: set[str] | None = None,
    expected_contents: dict[str, bytes] | None = None,
    expected_prefix: str | None = None,
) -> int:
    if not archive_path.is_file():
        raise ValueError(f"Source archive not found: {archive_path}")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            seen: set[str] = set()
            infos = archive.infolist()
            for info in infos:
                _validate_member(info, seen)
            corrupt = archive.testzip()
            if corrupt is not None:
                raise ValueError(f"Corrupt source archive entry: {corrupt}")
            prefix = _normalized_prefix(infos, expected_prefix)
            files = _project_files(infos, prefix)
            _validate_project_completeness(files)
            if expected_files is not None:
                _validate_expected_files(files, expected_files)
            if expected_contents is not None:
                _validate_expected_contents(archive, infos, prefix, expected_contents)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Invalid source ZIP: {archive_path}") from exc
    return len(seen)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify that an Evagix source ZIP is clean and safe to publish.")
    parser.add_argument("archive", type=Path, help="Source ZIP produced from the immutable release commit.")
    parser.add_argument(
        "--repository", type=Path, default=Path("."), help="Git repository containing the release tree."
    )
    parser.add_argument("--revision", help="Git revision whose tracked files must exactly match the archive.")
    parser.add_argument("--prefix", help="Expected top-level archive prefix, for example evagix-0.1.0/.")
    args = parser.parse_args()
    try:
        expected_contents = _git_tracked_contents(args.repository.resolve(), args.revision) if args.revision else None
        entries = verify_source_archive(
            args.archive.resolve(),
            expected_files=set(expected_contents) if expected_contents is not None else None,
            expected_contents=expected_contents,
            expected_prefix=args.prefix,
        )
    except ValueError as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(f"Verified complete and clean source archive: {args.archive} ({entries} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
