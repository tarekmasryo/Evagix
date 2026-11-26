from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from evagix import script_drift


def git(root: Path, *args: str, data: bytes | None = None) -> str:
    return (
        subprocess.check_output(
            [
                "git",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "core.autocrlf=false",
                "-c",
                "user.name=Fixture User",
                "-c",
                "user.email=fixture@example.invalid",
                *args,
            ],
            cwd=root,
            input=data,
            stderr=subprocess.PIPE,
        )
        .decode()
        .strip()
    )


@pytest.fixture
def script_repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/old.py").write_text("raise SystemExit(97)\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("Run `python scripts/old.py`.\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("```sh\npython scripts/old.py\n```\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    git(tmp_path, "checkout", "-qb", "feature")
    return tmp_path


def remove_script(root: Path) -> None:
    git(root, "rm", "-q", "scripts/old.py")
    git(root, "commit", "-qm", "remove script")


@pytest.mark.parametrize("rename", [False, True])
def test_deleted_or_renamed_target_is_reported_without_guessing_replacement(script_repo: Path, rename: bool) -> None:
    if rename:
        git(script_repo, "mv", "scripts/old.py", "scripts/new.py")
        git(script_repo, "commit", "-qm", "rename script")
    else:
        remove_script(script_repo)
    report = script_drift.build_script_drift_report(script_repo)
    assert report.complete
    assert report.base == report.merge_base == git(script_repo, "rev-parse", "main")
    assert report.head == git(script_repo, "rev-parse", "HEAD")
    assert [(f.document, f.target, f.line, f.column, f.code) for f in report.findings] == [
        ("README.md", "scripts/old.py", 2, 8, "context.deleted-script-reference"),
        ("AGENTS.md", "scripts/old.py", 1, 13, "context.deleted-script-reference"),
    ]
    payload = json.loads(script_drift.render_script_drift_json(report))
    assert payload["scope"]["working_directory"] == "repository_root_assumed"
    assert "scripts/new.py" not in script_drift.render_script_drift_text(report)


def test_head_document_fix_removes_stale_instruction(script_repo: Path) -> None:
    git(script_repo, "mv", "scripts/old.py", "scripts/new.py")
    for name in ("README.md", "AGENTS.md"):
        document = script_repo / name
        document.write_text(document.read_text(encoding="utf-8").replace("old.py", "new.py"), encoding="utf-8")
    git(script_repo, "add", ".")
    git(script_repo, "commit", "-qm", "rename with updated instructions")
    report = script_drift.build_script_drift_report(script_repo)
    assert report.complete and not report.findings


def test_worktree_and_index_do_not_change_committed_evidence(script_repo: Path) -> None:
    remove_script(script_repo)
    (script_repo / "AGENTS.md").write_text("Updated locally\n", encoding="utf-8")
    git(script_repo, "add", "AGENTS.md")
    (script_repo / "README.md").unlink()
    (script_repo / "scripts").mkdir(exist_ok=True)
    (script_repo / "scripts/old.py").write_text("untracked replacement\n", encoding="utf-8")
    assert len(script_drift.build_script_drift_report(script_repo).findings) == 2
    assert not script_drift.build_script_drift_report(script_repo, head="main").findings


def test_existing_and_preexisting_missing_targets_are_not_deletion_findings(script_repo: Path) -> None:
    (script_repo / "AGENTS.md").write_text("Run `python scripts/missing.py`.\n", encoding="utf-8")
    git(script_repo, "add", ".")
    git(script_repo, "commit", "-qm", "unrelated instructions")
    report = script_drift.build_script_drift_report(script_repo)
    assert report.complete and not report.findings


def test_base_advancement_does_not_change_deletion_scope(script_repo: Path) -> None:
    ancestor = git(script_repo, "rev-parse", "main")
    remove_script(script_repo)
    head = git(script_repo, "rev-parse", "HEAD")
    git(script_repo, "checkout", "-q", "main")
    (script_repo / "README.md").write_text("Base-only change\n", encoding="utf-8")
    git(script_repo, "add", ".")
    git(script_repo, "commit", "-qm", "advance base")
    report = script_drift.build_script_drift_report(script_repo, head=head)
    assert report.base != report.merge_base == ancestor
    assert report.head == head and len(report.findings) == 2


@pytest.mark.parametrize("mode", ["120000", "160000", "100644"])
def test_non_directory_ancestor_is_incomplete_without_following_it(script_repo: Path, mode: str) -> None:
    git(script_repo, "rm", "-qr", "scripts")
    oid = (
        git(script_repo, "rev-parse", "HEAD")
        if mode == "160000"
        else git(script_repo, "hash-object", "-w", "--stdin", data=b"/outside/private")
    )
    git(script_repo, "update-index", "--add", "--cacheinfo", f"{mode},{oid},scripts")
    git(script_repo, "commit", "-qm", "replace script directory")
    report = script_drift.build_script_drift_report(script_repo)
    assert not report.complete and not report.findings
    assert len(report.limitations) == 2
    assert "non-directory" in report.limitations[0]
    assert "outside/private" not in script_drift.render_script_drift_json(report)


def test_nonregular_original_target_is_not_a_removed_script(script_repo: Path) -> None:
    oid = git(script_repo, "hash-object", "-w", "--stdin", data=b"/outside/private")
    git(script_repo, "update-index", "--add", "--cacheinfo", f"120000,{oid},scripts/old.py")
    git(script_repo, "commit", "-qm", "original symlink")
    git(script_repo, "branch", "-f", "main", "HEAD")
    git(script_repo, "update-index", "--force-remove", "scripts/old.py")
    git(script_repo, "commit", "-qm", "remove symlink")
    report = script_drift.build_script_drift_report(script_repo)
    assert report.complete and not report.findings


def test_target_replaced_by_directory_is_not_absent(script_repo: Path) -> None:
    remove_script(script_repo)
    (script_repo / "scripts/old.py").mkdir(parents=True)
    (script_repo / "scripts/old.py/__main__.py").write_text("raise SystemExit(97)\n", encoding="utf-8")
    git(script_repo, "add", ".")
    git(script_repo, "commit", "-qm", "use package directory")
    report = script_drift.build_script_drift_report(script_repo)
    assert report.complete and not report.findings


@pytest.mark.parametrize("content", [b"invalid \xff", b"binary\0document"])
def test_unreadable_document_is_incomplete_and_preserves_other_findings(script_repo: Path, content: bytes) -> None:
    remove_script(script_repo)
    (script_repo / "README.md").write_bytes(content)
    git(script_repo, "add", ".")
    git(script_repo, "commit", "-qm", "unreadable document")
    report = script_drift.build_script_drift_report(script_repo)
    assert not report.complete
    assert len(report.findings) == 1 and report.findings[0].document == "AGENTS.md"


def test_nonregular_document_is_not_followed(script_repo: Path) -> None:
    remove_script(script_repo)
    oid = git(script_repo, "hash-object", "-w", "--stdin", data=b"/outside/private")
    git(script_repo, "update-index", "--add", "--cacheinfo", f"120000,{oid},README.md")
    git(script_repo, "commit", "-qm", "symlink document")
    report = script_drift.build_script_drift_report(script_repo)
    assert not report.complete and report.inspected_documents == ["AGENTS.md"]
    assert len(report.findings) == 1
    assert "outside/private" not in script_drift.render_script_drift_text(report)


def test_missing_documents_are_inapplicable(script_repo: Path) -> None:
    git(script_repo, "rm", "README.md", "AGENTS.md")
    git(script_repo, "commit", "-qm", "remove instructions")
    report = script_drift.build_script_drift_report(script_repo)
    assert report.complete and not report.inspected_documents and not report.findings


def test_oversized_documents_are_incomplete(script_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(script_drift, "_DOCUMENT_LIMIT", 4)
    report = script_drift.build_script_drift_report(script_repo)
    assert not report.complete and not report.inspected_documents


@pytest.mark.parametrize(("limit", "complete", "count"), [(1, False, 1), (2, True, 2)])
def test_finding_budget_distinguishes_exact_limit_from_excess(
    script_repo: Path, monkeypatch: pytest.MonkeyPatch, limit: int, complete: bool, count: int
) -> None:
    remove_script(script_repo)
    monkeypatch.setattr(script_drift, "_FINDING_LIMIT", limit)
    report = script_drift.build_script_drift_report(script_repo)
    assert report.complete is complete and len(report.findings) == count


def test_repeated_ambiguous_targets_have_bounded_limitations(script_repo: Path) -> None:
    (script_repo / "AGENTS.md").write_text("Run `python scripts/old.py`.\n" * 100, encoding="utf-8")
    git(script_repo, "rm", "-qr", "scripts")
    oid = git(script_repo, "hash-object", "-w", "--stdin", data=b"/outside/private")
    git(script_repo, "update-index", "--add", "--cacheinfo", f"120000,{oid},scripts")
    git(script_repo, "add", "AGENTS.md")
    git(script_repo, "commit", "-qm", "replace directory")
    report = script_drift.build_script_drift_report(script_repo)
    assert not report.findings and len(report.limitations) == 2
