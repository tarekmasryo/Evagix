from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import evagix.validation.generated_context as generated_context
from evagix.cli import main
from evagix.config import CustomTarget
from evagix.model import RepoFacts
from evagix.validation.generated_context import check_repo


def _facts(root: Path) -> RepoFacts:
    return RepoFacts(
        root_name=root.name,
        commands={"test": "python -m pytest", "lint": "python -m ruff check ."},
        ci_workflows=[".github/workflows/ci.yml"],
    )


def _symlink(link: Path, target: Path, *, directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks are unavailable in this environment: {exc}")


def _guard_external_reads(monkeypatch: pytest.MonkeyPatch, outside: Path) -> None:
    original_open = Path.open

    def guarded_open(path: Path, *args: Any, **kwargs: Any):
        resolved = path.resolve(strict=False)
        if resolved == outside or outside in resolved.parents:
            raise AssertionError(f"external path was opened: {path}")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)


@pytest.mark.parametrize(
    ("target_key", "relative_path", "symlink_parent"),
    [
        ("universal_md", ".evagix/context.md", ".evagix"),
        ("agents", "AGENTS.md", None),
        ("copilot", ".github/copilot-instructions.md", ".github"),
    ],
    ids=["evagix-parent", "agents-target", "github-parent"],
)
def test_unsafe_generated_targets_fail_without_following_external_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_key: str,
    relative_path: str,
    symlink_parent: str | None,
) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    outside_target = outside / Path(relative_path).name
    outside_content = "evagix:generated\nevagix:fingerprint=external\n"
    outside_target.write_text(outside_content, encoding="utf-8")
    if symlink_parent is None:
        _symlink(repo / relative_path, outside_target)
    else:
        _symlink(repo / symlink_parent, outside, directory=True)
    _guard_external_reads(monkeypatch, outside)

    result = check_repo(repo, _facts(repo), target_keys=[target_key])

    assert result.ok is False
    assert relative_path in result.unmanaged_targets
    assert any("unsafe" in warning.lower() and relative_path in warning for warning in result.warnings)


def test_generated_target_directory_is_a_controlled_failure(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    target.mkdir()

    result = check_repo(tmp_path, _facts(tmp_path), target_keys=["agents"])

    assert result.ok is False
    assert "AGENTS.md" in result.unmanaged_targets
    assert any("could not be read safely" in warning for warning in result.warnings)


@pytest.mark.parametrize("read_error", [PermissionError("denied"), OSError("unreadable")])
def test_generated_target_read_errors_are_controlled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    read_error: OSError,
) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text("evagix:generated\nevagix:fingerprint=test\n", encoding="utf-8")
    original_read = generated_context._read_generated_target

    def fail_target_read(root: Path, path: Path):
        if path == target:
            raise read_error
        return original_read(root, path)

    monkeypatch.setattr(generated_context, "_read_generated_target", fail_target_read)

    result = check_repo(tmp_path, _facts(tmp_path), target_keys=["agents"])

    assert result.ok is False
    assert "AGENTS.md" in result.unmanaged_targets
    assert any("could not be read safely" in warning for warning in result.warnings)


def test_custom_target_through_unsafe_symlink_is_a_controlled_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_target = outside / "context.md"
    outside_content = "evagix:generated\nevagix:fingerprint=external\n"
    outside_target.write_text(outside_content, encoding="utf-8")
    _symlink(tmp_path / "linked", outside, directory=True)
    _guard_external_reads(monkeypatch, outside)
    custom = CustomTarget(name="linked", path="linked/context.md")

    result = check_repo(tmp_path, _facts(tmp_path), target_keys=[], custom_targets=[custom])

    assert result.ok is False
    assert "linked/context.md" in result.unmanaged_targets
    assert any("unsafe" in warning.lower() for warning in result.warnings)


@pytest.mark.parametrize(
    "command",
    [
        ["check"],
        ["doctor", "--format", "json", "--fail-under", "0"],
        ["audit", "--format", "json"],
        ["drift", "--format", "json"],
    ],
    ids=["check", "doctor", "audit", "drift"],
)
def test_generated_context_consumers_report_unsafe_target_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: list[str],
) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        '[project]\nname="demo"\nversion="0.1.0"\ndependencies=[]\n',
        encoding="utf-8",
    )
    (repo / "evagix.toml").write_text(
        '[policy]\nfail_under=0\n[commands]\ntest="python -m pytest"\nlint="python -m ruff check ."\n'
        "[targets]\nagents=true\n",
        encoding="utf-8",
    )
    outside_target = outside / "AGENTS.md"
    outside_target.write_text("evagix:generated\nevagix:fingerprint=external\n", encoding="utf-8")
    _symlink(repo / "AGENTS.md", outside_target)
    _guard_external_reads(monkeypatch, outside)

    exit_code = main([*command, str(repo)])
    captured = capsys.readouterr()
    output = captured.out + captured.err

    assert exit_code == 1
    assert "Traceback" not in output
    assert output.strip()
