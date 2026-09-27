from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from evagix import command_recipes
from evagix.cli import main
from evagix.command_recipes import scan_package_script_dangers, scan_task_recipe_dangers


def _package(root: Path, command: str, *, directory: str = ".") -> Path:
    package = root / directory
    package.mkdir(parents=True, exist_ok=True)
    (package / "package.json").write_text(json.dumps({"scripts": {"test": command}}), encoding="utf-8")
    return package


def _assert_incomplete(findings: list) -> None:
    assert any(item.id == "command-safety.scan-truncated" and item.status == "incomplete" for item in findings)


@pytest.mark.parametrize("case", ["package", "make"])
def test_gh03_confirmed_bypasses_block_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    (tmp_path / "evagix.toml").write_text("[targets]\nagents=true\n", encoding="utf-8")
    if case == "package":
        _package(tmp_path, "sh check.sh")
        (tmp_path / "check.sh").write_text("rm -rf .\n", encoding="utf-8")
    else:
        (tmp_path / "Makefile").write_text("test: ; rm -rf .\n", encoding="utf-8")
    before = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    def forbid_execution(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Discovered project commands must never execute")

    monkeypatch.setattr(subprocess, "run", forbid_execution)
    monkeypatch.setattr(subprocess, "Popen", forbid_execution)
    monkeypatch.setattr(os, "system", forbid_execution)
    assert main(["compile", str(tmp_path)]) == 1
    assert "Unsafe validation commands detected" in capsys.readouterr().err
    after = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert after == before


@pytest.mark.parametrize("command", ["sh check.sh", "./check.sh", 'sh "check file.sh"'])
@pytest.mark.parametrize("directory", [".", "packages/web"])
def test_gh03_references_use_package_directory(tmp_path: Path, command: str, directory: str) -> None:
    package = _package(tmp_path, command, directory=directory)
    filename = "check file.sh" if "check file.sh" in command else "check.sh"
    (tmp_path / filename).write_text("echo safe\n", encoding="utf-8")
    (package / filename).write_text("rm -rf .\n", encoding="utf-8")
    findings = scan_package_script_dangers(tmp_path)
    assert any(
        item.id == "dangerous-command.local-script"
        and item.source_file == (package / filename).relative_to(tmp_path).as_posix()
        and item.source_line == 1
        and item.metadata["matched_rule"] == "dangerous-command.rm-root"
        for item in findings
    )


@pytest.mark.parametrize("command", ["sh check.sh", "./check.sh", "echo ready && npm test"])
def test_gh03_safe_package_commands_remain_safe(tmp_path: Path, command: str) -> None:
    package = _package(tmp_path, command, directory="packages/web")
    (tmp_path / "check.sh").write_text("rm -rf .\n", encoding="utf-8")
    (package / "check.sh").write_text("#!/bin/sh\necho ready\npython -m pytest\n", encoding="utf-8")
    assert scan_package_script_dangers(tmp_path) == []


@pytest.mark.parametrize(
    "content",
    [
        "test:\n\trm -rf .\n",
        "test: ; @rm -rf .\n",
        "test: ; echo ready\n\trm -rf .\n",
        r"test: data\#file ; rm -rf ." + "\n",
        r"test\#part: ; rm -rf ." + "\n",
        "test:: ; rm -rf .\n",
    ],
)
def test_gh03_make_recipes_detect_dangerous_commands(tmp_path: Path, content: str) -> None:
    (tmp_path / "Makefile").write_text(content, encoding="utf-8")
    findings = scan_task_recipe_dangers(tmp_path)
    assert any(item.metadata.get("matched_rule") == "dangerous-command.rm-root" for item in findings)


@pytest.mark.parametrize("assignment", ["=", ":=", "::=", ":::= ", "?=", "+="])
def test_gh03_target_specific_assignments_are_not_inline_recipes(tmp_path: Path, assignment: str) -> None:
    (tmp_path / "Makefile").write_text(
        f"test: private override NOTE {assignment} echo safe; rm -rf .\ntest:\n\tpython -m pytest\n",
        encoding="utf-8",
    )
    assert scan_task_recipe_dangers(tmp_path) == []


@pytest.mark.parametrize("content", ["test: data # ; rm -rf .\n", "test: ; echo '#literal'\n"])
def test_gh03_make_comments_and_literal_hash_are_preserved(tmp_path: Path, content: str) -> None:
    (tmp_path / "Makefile").write_text(content, encoding="utf-8")
    assert scan_task_recipe_dangers(tmp_path) == []


@pytest.mark.parametrize("oneshell", [False, True])
def test_gh03_make_cwd_is_not_guessed(tmp_path: Path, oneshell: bool) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "check.sh").write_text("echo safe\n", encoding="utf-8")
    (tmp_path / "sub" / "check.sh").write_text("rm -rf .\n", encoding="utf-8")
    (tmp_path / "Makefile").write_text(
        (".ONESHELL:\n" if oneshell else "") + "test:\n\tcd sub\n\tsh check.sh\n", encoding="utf-8"
    )
    findings = scan_task_recipe_dangers(tmp_path)
    if oneshell:
        _assert_incomplete(findings)
    else:
        assert findings == []


@pytest.mark.parametrize(
    "command",
    [
        "cd sub && sh check.sh",
        "cd sub || sh check.sh",
        "cd sub; sh check.sh",
        'bash -lc "sh check.sh"',
        "sh $SCRIPT",
        "sh ../outside.sh",
        "sh /outside.sh",
        "sh missing.sh",
        "sh good.sh && sh bad.sh",
    ],
)
def test_gh03_complex_or_unresolved_references_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    _package(tmp_path, command)
    (tmp_path / "check.sh").write_text("echo wrong_directory\n", encoding="utf-8")
    original = command_recipes.safe_read_text_result
    reads: list[Path] = []

    def record_read(path: Path, **kwargs: object):
        reads.append(path)
        return original(path, **kwargs)

    monkeypatch.setattr(command_recipes, "safe_read_text_result", record_read)
    _assert_incomplete(scan_package_script_dangers(tmp_path))
    assert tmp_path / "check.sh" not in reads
    before = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert main(["compile", str(tmp_path)]) == 1
    after = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert after == before


@pytest.mark.parametrize("body", ["sh check.sh\n", "sh second.sh\n", "cd sub\nsh check.sh\n"])
def test_gh03_nested_references_are_bounded_and_incomplete(tmp_path: Path, body: str) -> None:
    _package(tmp_path, "sh check.sh")
    (tmp_path / "check.sh").write_text(body, encoding="utf-8")
    (tmp_path / "second.sh").write_text("sh check.sh\n", encoding="utf-8")
    _assert_incomplete(scan_package_script_dangers(tmp_path))


@pytest.mark.parametrize("failure", ["invalid_utf8", "oversized", "unreadable"])
def test_gh03_reference_read_failures_block_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    _package(tmp_path, "sh check.sh")
    script = tmp_path / "check.sh"
    script.write_bytes(b"\xff" if failure == "invalid_utf8" else b"echo safe\n")
    if failure == "oversized":
        monkeypatch.setattr(command_recipes, "MAX_MANIFEST_CHARS", 64)
        script.write_text("x" * 65, encoding="utf-8")
    if failure == "unreadable":
        original = command_recipes.safe_read_text_result

        def deny_script(path: Path, **kwargs: object):
            if path == script:
                raise PermissionError("fictional private error")
            return original(path, **kwargs)

        monkeypatch.setattr(command_recipes, "safe_read_text_result", deny_script)
    findings = scan_package_script_dangers(tmp_path)
    assert findings and all(item.status == "incomplete" for item in findings)
    assert main(["compile", str(tmp_path)]) == 1
    assert not (tmp_path / "AGENTS.md").exists()


def test_gh03_reference_budget_is_shared_between_packages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(command_recipes, "MAX_SCRIPT_REFERENCES", 2, raising=False)
    for index in range(3):
        package = _package(tmp_path, "sh check.sh", directory=f"p{index}")
        (package / "check.sh").write_text("echo safe\n", encoding="utf-8")
    _assert_incomplete(scan_package_script_dangers(tmp_path))


def test_gh03_path_policy_runs_before_script_reads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _package(tmp_path, "sh check.sh")
    (tmp_path / "check.sh").write_text("echo safe\n", encoding="utf-8")
    original = command_recipes.safe_read_text_result

    def reject_script_read(path: Path, **kwargs: object):
        assert path.name != "check.sh", "A policy-rejected script must not be read"
        return original(path, **kwargs)

    monkeypatch.setattr(command_recipes, "is_safe_repo_path", lambda *_args: False)
    monkeypatch.setattr(command_recipes, "safe_read_text_result", reject_script_read)
    _assert_incomplete(scan_package_script_dangers(tmp_path))


@pytest.mark.parametrize(
    "command",
    ["cmd /c echo ready", 'bash -lc "echo ready; echo done"', 'bash -lc "echo ."', 'bash -lc "python -m pytest"'],
)
def test_gh03_wrappers_without_local_references_preserve_head_behavior(tmp_path: Path, command: str) -> None:
    _package(tmp_path, command)
    findings = scan_package_script_dangers(tmp_path)
    if ";" in command:
        # GH-02 already rejects this wrapper form; GH-03 must preserve its result.
        assert [(item.id, item.status, item.metadata["matched_rule"]) for item in findings] == [
            ("dangerous-command.package-script", "unsafe", "command-safety.scan-truncated")
        ]
    else:
        assert findings == []


@pytest.mark.parametrize("setup", ["cd sub", ". setup.sh", "$$CD sub"])
def test_gh03_oneshell_does_not_read_from_unproven_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, setup: str
) -> None:
    (tmp_path / "Makefile").write_text(f".ONESHELL:\ntest:\n\t{setup}\n\tsh check.sh\n", encoding="utf-8")
    (tmp_path / "setup.sh").write_text("cd sub\n", encoding="utf-8")
    (tmp_path / "check.sh").write_text("echo wrong_directory\n", encoding="utf-8")
    original = command_recipes.safe_read_text_result

    def reject_script_read(path: Path, **kwargs: object):
        assert path.name not in {"check.sh", "setup.sh"}
        return original(path, **kwargs)

    monkeypatch.setattr(command_recipes, "safe_read_text_result", reject_script_read)
    _assert_incomplete(scan_task_recipe_dangers(tmp_path))


@pytest.mark.parametrize("assignment", ["NOTE != echo safe; rm -rf .", "NOTE := $(shell rm -rf .)"])
def test_gh03_executable_make_assignments_are_incomplete(tmp_path: Path, assignment: str) -> None:
    (tmp_path / "Makefile").write_text(f"test: {assignment}\n", encoding="utf-8")
    _assert_incomplete(scan_task_recipe_dangers(tmp_path))


@pytest.mark.parametrize(
    "command",
    ['bash -lc "sh check"', 'bash -lc "echo ready" && sh check.sh', "sh good.sh; sh check.sh", "./check"],
)
def test_gh03_additional_indirection_is_incomplete(tmp_path: Path, command: str) -> None:
    _package(tmp_path, command)
    _assert_incomplete(scan_package_script_dangers(tmp_path))


@pytest.mark.parametrize("recipe", ["test: ; sh check.sh\n", "test:\n\tsh check.sh\n"])
def test_gh03_make_local_references_are_inspected(tmp_path: Path, recipe: str) -> None:
    (tmp_path / "Makefile").write_text(recipe, encoding="utf-8")
    (tmp_path / "check.sh").write_text("rm -rf .\n", encoding="utf-8")
    assert any(item.id == "dangerous-command.local-script" for item in scan_task_recipe_dangers(tmp_path))


def test_gh03_oneshell_without_cwd_changes_remains_safe(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text(".ONESHELL:\ntest:\n\techo ready\n\tsh check.sh\n", encoding="utf-8")
    (tmp_path / "check.sh").write_text("echo safe\n", encoding="utf-8")
    assert scan_task_recipe_dangers(tmp_path) == []


@pytest.mark.parametrize("operator", ["=", ":=", "::=", ":::="])
def test_gh03_global_literal_assignments_are_not_recipes(tmp_path: Path, operator: str) -> None:
    (tmp_path / "Makefile").write_text(f"NOTE {operator} echo safe; rm -rf .\ntest:\n\techo ready\n", encoding="utf-8")
    assert scan_task_recipe_dangers(tmp_path) == []


def test_gh03_make_continued_header_is_incomplete(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text("test: \\\n    ; rm -rf .\n", encoding="utf-8")
    _assert_incomplete(scan_task_recipe_dangers(tmp_path))


def test_gh03_budget_caps_reads_and_reuses_inspected_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(command_recipes, "MAX_SCRIPT_REFERENCES", 2)
    scripts = {"a": "sh a.sh", "b": "sh a.sh", "c": "sh c.sh", "d": "sh d.sh"}
    (tmp_path / "package.json").write_text(json.dumps({"scripts": scripts}), encoding="utf-8")
    for filename in ("a.sh", "c.sh", "d.sh"):
        (tmp_path / filename).write_text("echo safe\n", encoding="utf-8")
    reads: list[str] = []
    original = command_recipes.safe_read_text_result

    def count_reads(path: Path, **kwargs: object):
        if path.suffix == ".sh":
            reads.append(path.name)
        return original(path, **kwargs)

    monkeypatch.setattr(command_recipes, "safe_read_text_result", count_reads)
    _assert_incomplete(scan_package_script_dangers(tmp_path))
    assert reads == ["a.sh", "c.sh"]


def test_gh03_symlink_reference_is_incomplete(tmp_path: Path) -> None:
    _package(tmp_path, "sh link.sh")
    (tmp_path / "real.sh").write_text("echo safe\n", encoding="utf-8")
    try:
        (tmp_path / "link.sh").symlink_to(tmp_path / "real.sh")
    except OSError as exc:
        pytest.skip(f"Symlinks unavailable: {exc}")
    _assert_incomplete(scan_package_script_dangers(tmp_path))


@pytest.mark.parametrize(
    ("case", "command"),
    [
        ("oneshell", '"cd" sub'),
        ("oneshell", "'cd' sub"),
        ("oneshell", 'c""d sub'),
        ("oneshell", r"c\d sub"),
        ("exec", "exec sh check.sh"),
        ("exec", "exec -a validation sh check.sh"),
        ("exec_nested", "exec sh check.sh"),
        ("make", "  test: ; rm -rf .\n"),
        ("make", "  test:\n\trm -rf .\n"),
        ("data", "echo check.sh && echo ready"),
        ("data", "printf '%s' check.sh && echo ready"),
        ("data", "echo check.sh; echo ready"),
        ("nul_path", "sh check\x00.sh"),
    ],
)
def test_gh03_review_finding_regressions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    case: str,
    command: str,
) -> None:
    is_make = case in {"oneshell", "make"}
    (tmp_path / "evagix.toml").write_text(
        ('[commands]\ntest="make test"\n' if is_make else "") + "[targets]\nagents=true\n", encoding="utf-8"
    )
    if is_make:
        makefile = f".ONESHELL:\ntest:\n\t{command}\n\tsh check.sh\n" if case == "oneshell" else command
        (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
        (tmp_path / "sub").mkdir()
        (tmp_path / "check.sh").write_text("echo safe\n", encoding="utf-8")
        (tmp_path / "sub" / "check.sh").write_text("rm -rf .\n", encoding="utf-8")
    else:
        _package(tmp_path, "sh launcher.sh" if case == "exec_nested" else command)
        (tmp_path / "check.sh").write_text("echo safe\n" if case == "data" else "rm -rf .\n", encoding="utf-8")
        if case == "exec_nested":
            (tmp_path / "launcher.sh").write_text(command + "\n", encoding="utf-8")

    original_read = command_recipes.safe_read_text_result
    reads: list[Path] = []

    def record_read(path: Path, **kwargs: object):
        reads.append(path)
        return original_read(path, **kwargs)

    def forbid_execution(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Discovered project commands must never execute")

    monkeypatch.setattr(command_recipes, "safe_read_text_result", record_read)
    monkeypatch.setattr(subprocess, "run", forbid_execution)
    monkeypatch.setattr(subprocess, "Popen", forbid_execution)
    monkeypatch.setattr(os, "system", forbid_execution)
    before = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    findings = (scan_task_recipe_dangers if is_make else scan_package_script_dangers)(tmp_path)
    if case == "data":
        assert findings == []
    elif case == "make":
        assert any(item.metadata.get("matched_rule") == "dangerous-command.rm-root" for item in findings)
    else:
        _assert_incomplete(findings)
    assert tmp_path / "check.sh" not in reads
    assert main(["compile", str(tmp_path)]) == (0 if case == "data" else 1)
    output = capsys.readouterr()
    if case == "data":
        assert (tmp_path / "AGENTS.md").exists()
        assert "Unsafe validation commands detected" not in output.err
    else:
        assert "Unsafe validation commands detected" in output.err
        after = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
        assert after == before


@pytest.mark.parametrize(
    "command",
    [
        "echo ready && sh check.sh",
        "echo ready && ./check.sh",
        "echo ready && check.sh",
        "echo ready; exec sh check.sh",
        "printf '%s' check.sh | sh",
        "if true; then sh check.sh; fi",
    ],
)
def test_gh03_data_argument_fix_keeps_real_indirection_incomplete(tmp_path: Path, command: str) -> None:
    _package(tmp_path, command)
    (tmp_path / "check.sh").write_text("rm -rf .\n", encoding="utf-8")
    _assert_incomplete(scan_package_script_dangers(tmp_path))
