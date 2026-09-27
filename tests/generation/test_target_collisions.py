from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from evagix.cli import main
from evagix.config import CustomTarget, load_config
from evagix.core.io import WriteConflictError, build_write_plan
from evagix.generated_integrity import INTEGRITY_MANIFEST_PATH, with_integrity_manifest
from evagix.model import RepoFacts
from evagix.renderers import render_all
from evagix.safety import EvagixSafetyError
from evagix.targets import ALL_TARGET_KEYS

RESERVED_PATHS = [*render_all(RepoFacts(root_name="demo"), list(ALL_TARGET_KEYS)), INTEGRITY_MANIFEST_PATH]
COLLISIONS = [
    ([CustomTarget("local", ".evagix/context.json")], "reserved generated output path"),
    ([CustomTarget("local", ".evagix/integrity.json")], "reserved generated output path"),
    (
        [CustomTarget("first", "custom/context.md"), CustomTarget("second", "custom/context.md")],
        "duplicate generated output path",
    ),
    ([CustomTarget("same", "custom/one.md"), CustomTarget("same", "custom/two.md")], "duplicate custom target name"),
    ([CustomTarget(" same ", "custom/one.md"), CustomTarget("same", "custom/two.md")], "duplicate custom target name"),
    (
        [CustomTarget("first", "custom/context.md"), CustomTarget("second", "custom/../custom/context.md")],
        "duplicate generated output path",
    ),
]


def _write_config(root: Path, targets: list[CustomTarget]) -> None:
    (root / "README.md").write_text("# Demo\n", encoding="utf-8")
    (root / "evagix.toml").write_text(
        "[targets]\nuniversal_json=false\nuniversal_md=false\n\n"
        + "\n".join(
            f"[[targets.custom]]\nname={json.dumps(target.name)}\npath={json.dumps(target.path)}\n"
            f"format={json.dumps(target.output_format)}\n"
            for target in targets
        ),
        encoding="utf-8",
    )


def _snapshot(root: Path) -> dict[str, bytes | None]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None for path in root.rglob("*")
    }


@pytest.mark.parametrize(("targets", "diagnostic"), COLLISIONS)
@pytest.mark.parametrize("args", [["compile"], ["compile", "--force"], ["compile", "--dry-run"], ["sync"], ["check"]])
def test_config_collisions_fail_before_any_write(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], targets: list[CustomTarget], diagnostic: str, args: list[str]
) -> None:
    _write_config(tmp_path, targets)
    before = _snapshot(tmp_path)
    assert diagnostic in load_config(tmp_path).parse_error
    with pytest.raises(SystemExit) as exc:
        main([args[0], str(tmp_path), *args[1:]])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Invalid Evagix config" in captured.err
    assert diagnostic in captured.err
    assert "Traceback" not in captured.err
    assert not captured.out
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("path", RESERVED_PATHS)
def test_all_builtin_output_paths_are_reserved_even_when_disabled(tmp_path: Path, path: str) -> None:
    _write_config(tmp_path, [CustomTarget("local", path)])
    assert "reserved generated output path" in load_config(tmp_path).parse_error
    with pytest.raises(EvagixSafetyError, match="reserved generated output path"):
        render_all(RepoFacts(root_name="demo"), [], [CustomTarget("local", path)])


@pytest.mark.parametrize(("targets", "diagnostic"), COLLISIONS)
def test_renderer_rejects_collisions_when_config_validation_is_bypassed(
    targets: list[CustomTarget], diagnostic: str
) -> None:
    with pytest.raises(EvagixSafetyError, match=diagnostic):
        render_all(RepoFacts(root_name="demo"), None, targets)


@pytest.mark.parametrize(
    "path", ["./.evagix/context.json", ".evagix/../.evagix/context.json", ".evagix//integrity.json"]
)
def test_reserved_path_aliases_are_rejected(tmp_path: Path, path: str) -> None:
    _write_config(tmp_path, [CustomTarget("local", path)])
    assert "reserved generated output path" in load_config(tmp_path).parse_error
    with pytest.raises(EvagixSafetyError, match="reserved generated output path"):
        render_all(RepoFacts(root_name="demo"), [], [CustomTarget("local", path)])


def test_absolute_paths_cannot_alias_generated_outputs(tmp_path: Path) -> None:
    _write_config(tmp_path, [CustomTarget("local", str(tmp_path / ".evagix/context.json"))])
    assert "reserved generated output path" in load_config(tmp_path).parse_error
    # The final write boundary also knows the root if earlier validation was bypassed.
    with pytest.raises(WriteConflictError, match="duplicate generated output path"):
        build_write_plan(
            tmp_path, {"custom/context.md": "first", str(tmp_path / "custom/context.md"): "second"}, force=True
        )
    assert not (tmp_path / "custom").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows path aliases")
@pytest.mark.parametrize("path", [".EVAGIX/CONTEXT.JSON", ".evagix/context.json.", ".evagix./context.json"])
def test_windows_reserved_path_aliases_are_rejected(tmp_path: Path, path: str) -> None:
    _write_config(tmp_path, [CustomTarget("local", path)])
    assert "reserved generated output path" in load_config(tmp_path).parse_error
    with pytest.raises(EvagixSafetyError, match="reserved generated output path"):
        render_all(RepoFacts(root_name="demo"), [], [CustomTarget("local", path)])


@pytest.mark.parametrize("path", [INTEGRITY_MANIFEST_PATH, "./.evagix/integrity.json"])
def test_integrity_sidecar_cannot_overwrite_an_output(path: str) -> None:
    outputs = {path: "custom content"}
    with pytest.raises(EvagixSafetyError, match="reserved generated output path"):
        with_integrity_manifest(outputs, "fingerprint")
    assert outputs == {path: "custom content"}


def test_write_plan_rejects_aliased_keys_before_writing(tmp_path: Path) -> None:
    with pytest.raises(WriteConflictError, match="duplicate generated output path"):
        build_write_plan(tmp_path, {"custom/context.md": "first", "custom/../custom/context.md": "second"}, force=True)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("verb", ["compile", "sync"])
def test_valid_distinct_custom_targets_stay_stable(tmp_path: Path, verb: str) -> None:
    targets = [CustomTarget("local_md", "custom/context.md"), CustomTarget("local_json", "custom/context.json", "json")]
    _write_config(tmp_path, targets)
    assert not load_config(tmp_path).parse_error
    assert main([verb, str(tmp_path)]) == 0
    assert main(["check", str(tmp_path)]) == 0
    first = _snapshot(tmp_path)
    assert main(["compile", str(tmp_path)]) == 0
    assert _snapshot(tmp_path) == first
    assert "# local_md Context" in (tmp_path / targets[0].path).read_text(encoding="utf-8")
    assert json.loads((tmp_path / targets[1].path).read_text(encoding="utf-8"))["custom_target"]["name"] == "local_json"


def test_repeated_builtin_selection_remains_idempotent() -> None:
    facts = RepoFacts(root_name="demo")
    assert render_all(facts, ["agents", "agents"]) == render_all(facts, ["agents"])


WINDOWS_UNSAFE_OUTPUT_PATHS = [
    "custom/invalid?.md",
    "custom/invalid*.md",
    "custom/invalid<.md",
    "custom/invalid>.md",
    'custom/invalid".md',
    "custom/invalid|.md",
    "custom/invalid\x00.md",
    "custom/invalid\x01.md",
    "custom/invalid\x1f.md",
    "custom/NUL.md",
    "custom/COM1.md",
    "custom/LPT9.md",
    "custom/CON/nested.md",
    ".evagix/contex~1.jso",
    ".evagix/integr~1.jso",
    "custom/long-t~1.md",
    "custom~1/context.md",
    "custom~1/../custom/context.md",
    ".evagix/context.json::$DATA",
    ".evagix/integrity.json::$DATA",
    "custom/context.md:stream",
    "custom:stream/context.md",
]


@pytest.mark.skipif(os.name != "nt", reason="Windows output path safety")
@pytest.mark.parametrize("path", WINDOWS_UNSAFE_OUTPUT_PATHS)
@pytest.mark.parametrize("verb", ["compile", "sync"])
def test_windows_unsafe_outputs_fail_before_any_write(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], path: str, verb: str
) -> None:
    _write_config(
        tmp_path,
        [CustomTarget("first", "custom/long-target-name.md"), CustomTarget("unsafe", path)],
    )
    config_path = tmp_path / "evagix.toml"
    config_path.write_text(config_path.read_text(encoding="utf-8").replace("=false", "=true"), encoding="utf-8")
    before = _snapshot(tmp_path)
    try:
        result = main([verb, str(tmp_path)])
    except SystemExit as exc:
        result = exc.code
    captured = capsys.readouterr()
    assert _snapshot(tmp_path) == before
    assert result == 1
    assert "Unsafe Windows output path component" in captured.err
    assert "Traceback" not in captured.err
    assert "Written" not in captured.out
    assert "targets.custom[1].path" in load_config(tmp_path).parse_error


@pytest.mark.skipif(os.name != "nt", reason="Windows output path safety")
@pytest.mark.parametrize("path", WINDOWS_UNSAFE_OUTPUT_PATHS)
@pytest.mark.parametrize("boundary", ["render", "write_plan"])
def test_windows_unsafe_outputs_rejected_when_config_is_bypassed(tmp_path: Path, path: str, boundary: str) -> None:
    with pytest.raises(EvagixSafetyError, match="Unsafe Windows output path component"):
        if boundary == "render":
            render_all(RepoFacts(root_name="demo"), None, [CustomTarget("unsafe", path)])
        else:
            build_write_plan(tmp_path, {"AGENTS.md": "valid first", path: "unsafe"}, force=True)
    assert not list(tmp_path.iterdir())


@pytest.mark.skipif(os.name != "nt", reason="Windows output path safety")
@pytest.mark.parametrize("path", [".evagix/contex~1.jso", ".evagix/context.json::$DATA"])
def test_windows_unsafe_syntax_is_rejected_before_resolving_existing_files(tmp_path: Path, path: str) -> None:
    existing = tmp_path / ".evagix/context.json"
    existing.parent.mkdir()
    existing.write_text('{"existing": true}\n', encoding="utf-8")
    _write_config(tmp_path, [CustomTarget("unsafe", path)])
    before = _snapshot(tmp_path)
    assert "Unsafe Windows output path component" in load_config(tmp_path).parse_error
    with pytest.raises(EvagixSafetyError, match="Unsafe Windows output path component"):
        build_write_plan(tmp_path, {path: "replacement"}, force=True)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("absolute", [False, True])
def test_ordinary_output_paths_remain_valid_and_deterministic(tmp_path: Path, absolute: bool) -> None:
    relative = "custom folder/notes~draft.md"
    path = str(tmp_path / relative) if absolute else relative
    _write_config(tmp_path, [CustomTarget("ordinary", path)])
    assert not load_config(tmp_path).parse_error
    assert main(["compile", str(tmp_path)]) == 0
    assert (tmp_path / relative).is_file()
    assert main(["check", str(tmp_path)]) == 0
    first = _snapshot(tmp_path)
    assert main(["sync", str(tmp_path)]) == 0
    assert _snapshot(tmp_path) == first


STRUCTURAL_OUTPUT_CONFLICTS = [
    ["custom/context.md", "custom/context.md/nested.md"],
    ["custom/context.md", "custom/../custom/context.md/nested.md"],
    [".evagix/context.json/nested.md"],
    [".evagix/integrity.json/nested.md"],
    [".evagix"],
]


@pytest.mark.parametrize("paths", STRUCTURAL_OUTPUT_CONFLICTS)
@pytest.mark.parametrize("verb", ["compile", "sync"])
def test_structural_output_conflicts_fail_before_any_write(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], paths: list[str], verb: str
) -> None:
    _write_config(tmp_path, [CustomTarget(f"custom{index}", path) for index, path in enumerate(paths)])
    config_path = tmp_path / "evagix.toml"
    config_path.write_text(config_path.read_text(encoding="utf-8").replace("=false", "=true"), encoding="utf-8")
    before = _snapshot(tmp_path)
    assert main([verb, str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert _snapshot(tmp_path) == before
    assert "file/directory conflict" in captured.err
    assert "Written" not in captured.out


@pytest.mark.parametrize("paths", STRUCTURAL_OUTPUT_CONFLICTS)
@pytest.mark.parametrize("force", [False, True])
def test_write_plan_rejects_file_directory_conflicts(tmp_path: Path, paths: list[str], force: bool) -> None:
    outputs = {".evagix/context.json": "builtin", ".evagix/integrity.json": "integrity"}
    outputs.update(dict.fromkeys(paths, "custom"))
    with pytest.raises(WriteConflictError, match="file/directory conflict"):
        build_write_plan(tmp_path, outputs, force=force)
    assert not list(tmp_path.iterdir())


def test_write_plan_rejects_absolute_relative_file_directory_conflict(tmp_path: Path) -> None:
    outputs = {"custom/context.md": "parent", str(tmp_path / "custom/context.md/nested.md"): "child"}
    with pytest.raises(WriteConflictError, match="file/directory conflict"):
        build_write_plan(tmp_path, outputs, force=True)
    assert not list(tmp_path.iterdir())


@pytest.mark.skipif(os.name != "nt", reason="Windows path aliases")
@pytest.mark.parametrize("parent", ["CUSTOM/CONTEXT.MD", "custom/context.md."])
def test_write_plan_rejects_windows_aliased_file_directory_conflicts(tmp_path: Path, parent: str) -> None:
    with pytest.raises(WriteConflictError, match="file/directory conflict"):
        build_write_plan(tmp_path, {parent: "parent", "custom/context.md/nested.md": "child"}, force=True)
    assert not list(tmp_path.iterdir())


def test_write_plan_allows_shared_directories_and_distinct_path_components(tmp_path: Path) -> None:
    outputs = {"custom/context.md": "first", "custom/other.md": "second", "custom/context.md-extra/nested.md": "third"}
    plan = build_write_plan(tmp_path, outputs)
    assert plan.ok
    assert set(plan.relative_paths) == set(outputs)
    assert not list(tmp_path.iterdir())
