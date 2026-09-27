from __future__ import annotations

import json
from pathlib import Path

import pytest

from evagix.cli import main
from evagix.commands.common import _facts
from evagix.generated_integrity import INTEGRITY_MANIFEST_PATH, parse_integrity_manifest
from evagix.utils import extract_fingerprint, facts_fingerprint


def _repo(root: Path, target: str) -> None:
    (root / "pyproject.toml").write_text(
        '[project]\nname="demo"\nversion="0.1.0"\ndependencies=["pytest", "ruff"]\n', encoding="utf-8"
    )
    output_format = "json" if target.endswith(".json") else "markdown"
    (root / "evagix.toml").write_text(
        f'[[targets.custom]]\nname="local"\npath="{target}"\nformat="{output_format}"\n', encoding="utf-8"
    )


def _snapshot(root: Path) -> dict[str, bytes | None]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None for path in root.rglob("*")
    }


@pytest.mark.parametrize(
    "target", ["custom/context.md", "custom/nested/context.md", "custom notes/nested/context.json"]
)
@pytest.mark.parametrize("existing_parent", [False, True], ids=["new-parent", "existing-parent"])
def test_first_compile_is_fresh_and_repeated_generation_is_identical(
    tmp_path: Path, target: str, existing_parent: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    _repo(tmp_path, target)
    if existing_parent:
        (tmp_path / target).parent.mkdir(parents=True)

    assert main(["compile", str(tmp_path)]) == 0
    assert (tmp_path / target).is_file()
    assert main(["check", str(tmp_path)]) == 0
    first = _snapshot(tmp_path)
    facts, _ = _facts(tmp_path)
    expected = facts_fingerprint(facts.to_dict())
    assert extract_fingerprint((tmp_path / target).read_text(encoding="utf-8")) == expected
    manifest = parse_integrity_manifest((tmp_path / INTEGRITY_MANIFEST_PATH).read_text(encoding="utf-8"))
    assert manifest is not None and manifest.source_fingerprint == expected
    assert target in manifest.target_digests

    assert main(["compile", str(tmp_path)]) == 0
    assert main(["sync", str(tmp_path)]) == 0
    assert main(["check", str(tmp_path)]) == 0
    assert _snapshot(tmp_path) == first
    capsys.readouterr()
    assert main(["sync", str(tmp_path), "--plan"]) == 0
    assert "No changes needed." in capsys.readouterr().out


@pytest.mark.parametrize("target", ["custom/context.md", "custom/nested/context.json"])
def test_first_sync_to_new_custom_directory_passes(tmp_path: Path, target: str) -> None:
    _repo(tmp_path, target)
    assert main(["sync", str(tmp_path)]) == 0
    assert (tmp_path / target).is_file()
    assert main(["check", str(tmp_path)]) == 0


@pytest.mark.parametrize("arguments", [["compile", "--dry-run"], ["sync", "--plan"], ["diff"]])
@pytest.mark.parametrize("docs_only", [False, True])
def test_custom_target_preview_creates_nothing(tmp_path: Path, arguments: list[str], docs_only: bool) -> None:
    if docs_only:
        _docs_repo(tmp_path, "docs/nested/context.md")
    else:
        _repo(tmp_path, "custom/nested/context.md")
    before = _snapshot(tmp_path)
    result = main([arguments[0], str(tmp_path), *arguments[1:]])
    assert result == (1 if arguments[0] == "diff" else 0)
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / "custom").exists()
    assert not (tmp_path / ".evagix").exists()


@pytest.mark.parametrize("command", ["compile", "sync"])
def test_ownership_conflict_prevents_new_output_directories(
    tmp_path: Path, command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    _repo(tmp_path, "custom/nested/context.md")
    with (tmp_path / "evagix.toml").open("a", encoding="utf-8") as config:
        config.write('\n[[targets.custom]]\nname="manual"\npath="manual.md"\n')
    (tmp_path / "manual.md").write_text("User-owned context\n", encoding="utf-8")
    before = _snapshot(tmp_path)

    assert main([command, str(tmp_path)]) == 1
    assert "Skipped existing non-evagix files" in capsys.readouterr().err
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("target_parent", ["custom", "tests", "migrations"])
def test_real_repository_folder_changes_still_invalidate_generated_context(
    tmp_path: Path, target_parent: str, capsys: pytest.CaptureFixture[str]
) -> None:
    _repo(tmp_path, f"{target_parent}/context.md")
    assert main(["compile", str(tmp_path)]) == 0
    assert main(["check", str(tmp_path)]) == 0
    payload = json.loads((tmp_path / ".evagix/context.json").read_text(encoding="utf-8"))
    assert target_parent in payload["facts"]["folders"]
    initial_fingerprint = payload["fingerprint"]
    current_facts = json.loads(json.dumps(_facts(tmp_path)[0].to_dict()))
    current_facts.pop("generated_targets")
    assert payload["facts"] == current_facts

    capsys.readouterr()
    (tmp_path / "new_source_folder").mkdir()
    assert main(["check", str(tmp_path)]) == 1
    assert "stale" in capsys.readouterr().err.lower()
    assert facts_fingerprint(_facts(tmp_path)[0].to_dict()) != initial_fingerprint

    (tmp_path / "new_source_folder").rmdir()
    assert main(["check", str(tmp_path)]) == 0


def test_custom_target_integrity_is_still_enforced(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = "custom/nested/context.md"
    _repo(tmp_path, target)
    assert main(["compile", str(tmp_path)]) == 0
    assert main(["check", str(tmp_path)]) == 0
    with (tmp_path / target).open("a", encoding="utf-8") as handle:
        handle.write("\nManual drift\n")

    assert main(["check", str(tmp_path)]) == 1
    assert "modified manually" in capsys.readouterr().err


def _docs_repo(root: Path, target: str, *, existing_parent: bool = False) -> None:
    (root / "README.md").write_text("# Demo\n\nProject documentation.\n", encoding="utf-8")
    (root / "evagix.toml").write_text(f'[[targets.custom]]\nname="docs"\npath="{target}"\n', encoding="utf-8")
    if existing_parent:
        (root / target).parent.mkdir(parents=True)


@pytest.mark.parametrize("command", ["compile", "sync"])
@pytest.mark.parametrize("target", ["docs/context.md", "docs/nested/context.md"])
@pytest.mark.parametrize("existing_parent", [False, True], ids=["new-parent", "existing-parent"])
def test_docs_only_first_generation_matches_rescanned_facts(
    tmp_path: Path, command: str, target: str, existing_parent: bool
) -> None:
    _docs_repo(tmp_path, target, existing_parent=existing_parent)

    assert main([command, str(tmp_path)]) == 0
    assert main(["check", str(tmp_path)]) == 0
    facts, _ = _facts(tmp_path)
    fingerprint = facts_fingerprint(facts.to_dict())
    payload = json.loads((tmp_path / ".evagix/context.json").read_text(encoding="utf-8"))
    assert payload["fingerprint"] == fingerprint
    assert extract_fingerprint((tmp_path / target).read_text(encoding="utf-8")) == fingerprint
    manifest = parse_integrity_manifest((tmp_path / INTEGRITY_MANIFEST_PATH).read_text(encoding="utf-8"))
    assert manifest is not None and manifest.source_fingerprint == fingerprint
    current_facts = json.loads(json.dumps(facts.to_dict()))
    current_facts.pop("generated_targets")
    assert payload["facts"] == current_facts
    first = _snapshot(tmp_path)
    assert main([command, str(tmp_path)]) == 0
    assert _snapshot(tmp_path) == first


def test_docs_only_second_generation_is_byte_stable(tmp_path: Path) -> None:
    _docs_repo(tmp_path, "docs/context.md")
    assert main(["compile", str(tmp_path)]) == 0
    first = _snapshot(tmp_path)
    assert main(["compile", str(tmp_path)]) == 0
    assert _snapshot(tmp_path) == first


@pytest.mark.parametrize("target", ["docs/examples/context.md", "docs/fixtures/context.md"])
def test_planned_outputs_preserve_classification_path_exclusions(tmp_path: Path, target: str) -> None:
    _docs_repo(tmp_path, target)
    assert main(["sync", str(tmp_path)]) == 0
    payload = json.loads((tmp_path / ".evagix/context.json").read_text(encoding="utf-8"))
    assert "docs/" not in payload["facts"]["classification"]["primary"]["signals"]
    assert payload["fingerprint"] == facts_fingerprint(_facts(tmp_path)[0].to_dict())
    first = _snapshot(tmp_path)
    assert main(["compile", str(tmp_path)]) == 0
    assert _snapshot(tmp_path) == first


def test_projected_classification_preserves_config_enrichment_order(tmp_path: Path) -> None:
    _docs_repo(tmp_path, "docs/context.md")
    with (tmp_path / "evagix.toml").open("a", encoding="utf-8") as config:
        config.write('\n[commands]\ntest="echo ready"\n')
    assert main(["sync", str(tmp_path)]) == 0
    payload = json.loads((tmp_path / ".evagix/context.json").read_text(encoding="utf-8"))
    facts = _facts(tmp_path)[0]
    assert facts.commands["test"] == "echo ready"
    assert payload["fingerprint"] == facts_fingerprint(facts.to_dict())
    first = _snapshot(tmp_path)
    assert main(["compile", str(tmp_path)]) == 0
    assert _snapshot(tmp_path) == first


def test_real_source_files_still_change_classification_and_fingerprint(tmp_path: Path) -> None:
    _docs_repo(tmp_path, "docs/context.md")
    assert main(["sync", str(tmp_path)]) == 0
    before = _facts(tmp_path)[0]
    (tmp_path / "mkdocs.yml").write_text("site_name: Demo\n", encoding="utf-8")
    after = _facts(tmp_path)[0]
    assert after.classification != before.classification
    assert facts_fingerprint(after.to_dict()) != facts_fingerprint(before.to_dict())
    assert main(["check", str(tmp_path)]) == 1
