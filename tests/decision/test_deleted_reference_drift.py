from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from evagix import reference_drift as drift
from evagix.scanning import git_snapshot


def git(root: Path, *args: str, data: bytes | None = None) -> str:
    return subprocess.check_output(["git", "-c", "commit.gpgsign=false", *args], cwd=root, input=data).decode().strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.name", "Fixture User")
    git(tmp_path, "config", "user.email", "fixture@example.com")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/test.sh").write_text("echo test\n")
    (tmp_path / "README.md").write_text("# Demo\nSee [test script](scripts/test.sh).\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("Run the [script](./scripts/test.sh).\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    git(tmp_path, "checkout", "-qb", "feature")
    return tmp_path


def delete_target(repo: Path) -> str:
    git(repo, "rm", "-q", "scripts/test.sh")
    git(repo, "commit", "-qm", "delete script")
    return git(repo, "rev-parse", "HEAD")


def test_reports_unchanged_documents_with_snapshot_evidence(repo: Path) -> None:
    head = delete_target(repo)
    report = drift.build_reference_drift_report(repo)
    assert report.complete
    assert report.head == head
    assert report.merge_base == report.base == git(repo, "rev-parse", "main")
    assert [(f.document, f.target, f.line, f.column) for f in report.findings] == [
        ("README.md", "scripts/test.sh", 2, 19),
        ("AGENTS.md", "scripts/test.sh", 1, 18),
    ]
    payload = json.loads(drift.render_reference_drift_json(report))
    assert payload["completeness"] == "complete"
    assert payload["scope"]["working_tree"] == "excluded"
    assert "advisory" in drift.render_reference_drift_text(report)
    annotations = drift.render_reference_drift_github_annotations(report)
    assert "::notice file=README.md,line=2,col=19" in annotations
    assert "::error" not in annotations


def test_worktree_and_index_cannot_fix_or_invent_committed_findings(repo: Path) -> None:
    delete_target(repo)
    (repo / "README.md").write_text("Fixed locally\n")
    git(repo, "add", "README.md")
    (repo / "AGENTS.md").unlink()
    (repo / "scripts").mkdir(exist_ok=True)
    (repo / "scripts/test.sh").write_text("untracked replacement\n")
    assert len(drift.build_reference_drift_report(repo).findings) == 2
    assert not drift.build_reference_drift_report(repo, head="main").findings


def test_preexisting_missing_link_is_not_new_drift(repo: Path) -> None:
    (repo / "README.md").write_text("[missing](already-missing.py)\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "unrelated documentation")
    assert drift.build_reference_drift_report(repo).findings == []


def test_committed_document_fix_removes_the_finding(repo: Path) -> None:
    delete_target(repo)
    (repo / "README.md").write_text("Removed test script.\n")
    git(repo, "rm", "-q", "AGENTS.md")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "update instructions")
    report = drift.build_reference_drift_report(repo)
    assert report.complete and not report.findings
    assert report.inspected_documents == ["README.md"]


def test_base_branch_advances_without_changing_pr_deletion_scope(repo: Path) -> None:
    ancestor = git(repo, "rev-parse", "main")
    head = delete_target(repo)
    git(repo, "checkout", "-q", "main")
    (repo / "new-file.py").write_text("# unrelated\n")
    (repo / "README.md").write_text("Changed only on base\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "advance main")
    report = drift.build_reference_drift_report(repo, head=head)
    assert report.merge_base == ancestor != report.base
    assert len(report.findings) == 2


def test_file_replaced_by_directory_still_resolves(repo: Path) -> None:
    delete_target(repo)
    (repo / "scripts/test.sh").mkdir(parents=True)
    (repo / "scripts/test.sh/content.txt").write_text("directory landing page\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "replace with directory")
    assert not drift.build_reference_drift_report(repo).findings


def test_renamed_file_retains_broken_old_reference(repo: Path) -> None:
    git(repo, "mv", "scripts/test.sh", "scripts/check.sh")
    git(repo, "commit", "-qm", "rename script")
    assert len(drift.build_reference_drift_report(repo).findings) == 2


def test_symlink_document_is_not_followed(repo: Path) -> None:
    delete_target(repo)
    oid = git(repo, "hash-object", "-w", "--stdin", data=b"/outside/private\n")
    git(repo, "update-index", "--add", "--cacheinfo", f"120000,{oid},README.md")
    git(repo, "commit", "-qm", "symlink document")
    report = drift.build_reference_drift_report(repo)
    assert not report.complete
    assert report.inspected_documents == ["AGENTS.md"]
    assert len(report.findings) == 1
    assert "outside" not in drift.render_reference_drift_json(report)


@pytest.mark.parametrize("content", [b"bad \xff", b"binary\0document"])
def test_bad_document_is_incomplete_and_preserves_other_findings(repo: Path, content: bytes) -> None:
    delete_target(repo)
    (repo / "README.md").write_bytes(content)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "invalid document")
    report = drift.build_reference_drift_report(repo)
    assert not report.complete and len(report.findings) == 1
    assert report.findings[0].document == "AGENTS.md"
    assert "::warning::" in drift.render_reference_drift_github_annotations(report)


def test_oversized_document_is_not_silently_clean(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(drift, "_DOCUMENT_LIMIT", 4)
    report = drift.build_reference_drift_report(repo)
    assert not report.complete and not report.inspected_documents


def test_finding_budget_is_explicit(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    delete_target(repo)
    monkeypatch.setattr(drift, "_FINDING_LIMIT", 1)
    report = drift.build_reference_drift_report(repo)
    assert not report.complete and len(report.findings) == 1


def test_tree_budget_fails_without_a_clean_report(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git_snapshot, "_TREE_LIMIT", 8)
    with pytest.raises(RuntimeError, match="size limit"):
        drift.build_reference_drift_report(repo)


@pytest.mark.parametrize("ref", ["--output=stolen", "main..HEAD", "missing-branch"])
def test_bad_refs_fail_without_writing_files(repo: Path, ref: str) -> None:
    with pytest.raises((ValueError, RuntimeError)):
        drift.build_reference_drift_report(repo, base=ref)
    assert not (repo / "stolen").exists()


def test_missing_history_has_no_two_dot_fallback(repo: Path) -> None:
    git(repo, "checkout", "-q", "--orphan", "unrelated")
    git(repo, "commit", "-qm", "unrelated root")
    with pytest.raises(RuntimeError):
        drift.build_reference_drift_report(repo)


def test_replacement_objects_do_not_change_evidence(repo: Path) -> None:
    head = delete_target(repo)
    git(repo, "replace", head, git(repo, "rev-parse", "main"))
    report = drift.build_reference_drift_report(repo)
    assert report.head == head and len(report.findings) == 2


def test_ambient_git_directory_does_not_redirect_scan(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    delete_target(repo)
    monkeypatch.setenv("GIT_DIR", str(repo / "nonexistent"))
    assert len(drift.build_reference_drift_report(repo).findings) == 2


def test_inspection_does_not_execute_git_text_converters(repo: Path) -> None:
    (repo / ".gitattributes").write_text("*.md diff=untrusted\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "attributes")
    delete_target(repo)
    git(repo, "config", "diff.external", "evagix-must-not-execute-this")
    git(repo, "config", "diff.untrusted.textconv", "evagix-must-not-execute-this")
    assert len(drift.build_reference_drift_report(repo).findings) == 2


def test_snapshot_subprocess_disables_lazy_fetch_and_ambient_config(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_popen = subprocess.Popen
    calls = []

    def inspect(*args, **kwargs):
        calls.append((args[0], kwargs["env"]))
        return real_popen(*args, **kwargs)

    # A mapping double avoids changing native Windows environment entries:
    # restoring an empty value with putenv can remove it from child processes.
    monkeypatch.setattr(
        git_snapshot.os,
        "environ",
        {
            **git_snapshot.os.environ,
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "remote.origin.url",
            "GIT_CONFIG_VALUE_0": "https://invalid.example/private",
        },
    )
    monkeypatch.setattr(git_snapshot.subprocess, "Popen", inspect)
    drift.build_reference_drift_report(repo)
    for command, environment in calls:
        assert "protocol.allow=never" in command
        assert environment["GIT_NO_LAZY_FETCH"] == "1"
        assert environment["GIT_NO_REPLACE_OBJECTS"] == "1"
        assert "GIT_CONFIG_VALUE_0" not in environment


def test_renderers_redact_targets() -> None:
    report = drift.ReferenceDriftReport(
        "a" * 40,
        "b" * 40,
        "a" * 40,
        ["README.md"],
        [],
        [drift.DeletedReference("README.md", 1, 1, "api_key=synthetic-private-value.txt")],
    )
    for renderer in (
        drift.render_reference_drift_text,
        drift.render_reference_drift_json,
        drift.render_reference_drift_github_annotations,
    ):
        assert "synthetic-private-value" not in renderer(report)


def test_bounded_reader_terminates_a_stalled_process(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_popen = subprocess.Popen

    def stalled(*args, **kwargs):
        return real_popen([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)

    monkeypatch.setattr(git_snapshot, "_TIMEOUT", 0.1)
    monkeypatch.setattr(git_snapshot.subprocess, "Popen", stalled)
    with pytest.raises(RuntimeError, match="timed out"):
        git_snapshot.GitSnapshot(repo).read("rev-parse", "HEAD")
