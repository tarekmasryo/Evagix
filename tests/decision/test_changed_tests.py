from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from evagix import test_changes as changes

SOURCE = "import pytest\n\ndef test_existing():\n    assert 2 + 2 == 4\n"
SKIPPED = SOURCE.replace("def test_existing", '@pytest.mark.skip(reason="review later")\ndef test_existing')


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


def commit(root: Path, message: str = "fixture change") -> None:
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_existing.py").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "tests/helper.py").write_text("# helper\n", encoding="utf-8")
    commit(tmp_path, "base")
    git(tmp_path, "checkout", "-qb", "feature")
    return tmp_path


def test_deleted_file_has_old_revision_location_and_ignores_helper(repo: Path) -> None:
    git(repo, "rm", "tests/test_existing.py", "tests/helper.py")
    commit(repo)
    report = changes.build_test_changes_report(repo)
    assert report.complete and len(report.findings) == 1
    finding = report.findings[0]
    assert finding.code == "tests.deleted-file" and finding.path == "tests/test_existing.py"
    assert finding.revision == "merge_base" and finding.line == finding.column == 1
    assert finding.test is None and finding.previous_path is None
    assert report.merge_base == report.base == git(repo, "rev-parse", "main")
    assert report.head == git(repo, "rev-parse", "HEAD")


@pytest.mark.parametrize("filename", ["test_example.py", "example_test.py"])
def test_both_default_python_filename_patterns_are_inspected(repo: Path, filename: str) -> None:
    path = repo / filename
    path.write_text(SOURCE, encoding="utf-8")
    commit(repo)
    git(repo, "branch", "-f", "main", "HEAD")
    path.unlink()
    commit(repo)
    assert [finding.path for finding in changes.build_test_changes_report(repo).findings] == [filename]


@pytest.mark.parametrize("edit", ["", "# small edit\n"])
def test_rename_is_visible_separately_without_a_deletion_finding(repo: Path, edit: str) -> None:
    git(repo, "mv", "tests/test_existing.py", "tests/test_new.py")
    path = repo / "tests/test_new.py"
    path.write_text(SOURCE + edit, encoding="utf-8")
    commit(repo)
    report = changes.build_test_changes_report(repo)
    assert report.complete and not report.findings
    assert len(report.renames) == 1
    assert (report.renames[0].previous_path, report.renames[0].path) == ("tests/test_existing.py", "tests/test_new.py")
    assert 50 <= report.renames[0].similarity <= 100


def test_rename_with_new_skip_retains_previous_declaration(repo: Path) -> None:
    # Enough unchanged content for Git's explicit similarity threshold.
    original = SOURCE + "\n".join(f"# shared explanatory line {index}" for index in range(30)) + "\n"
    (repo / "tests/test_existing.py").write_text(original, encoding="utf-8")
    commit(repo)
    git(repo, "branch", "-f", "main", "HEAD")
    git(repo, "mv", "tests/test_existing.py", "tests/test_new.py")
    (repo / "tests/test_new.py").write_text(
        original.replace("def test_existing", "@pytest.mark.skip\ndef test_existing"), encoding="utf-8"
    )
    commit(repo)
    report = changes.build_test_changes_report(repo)
    assert report.complete and len(report.renames) == len(report.findings) == 1
    item = report.findings[0]
    assert item.code == "tests.unconditional-skip-added" and item.path == "tests/test_new.py"
    assert item.test == "test_existing" and item.previous_path == "tests/test_existing.py"
    assert item.previous_line == 3 and item.line == 3 and item.column == 2 and item.revision == "head"


def test_move_outside_supported_patterns_is_not_declared_deleted_or_clean(repo: Path) -> None:
    git(repo, "mv", "tests/test_existing.py", "tests/example.py")
    commit(repo)
    report = changes.build_test_changes_report(repo)
    assert not report.complete and not report.findings and len(report.renames) == 1
    assert "outside the supported" in report.limitations[0]


@pytest.mark.parametrize(
    "replacement",
    [
        SOURCE + "# ordinary change\n",
        SOURCE.replace("def test_existing", "@pytest.mark.skipif(True, reason='condition')\ndef test_existing"),
        SOURCE.replace("def test_existing", "@pytest.mark.skipif(False, reason='condition')\ndef test_existing"),
        SOURCE.replace("assert 2 + 2 == 4", "if False:\n        pytest.skip('conditional')"),
        SOURCE + "\n@pytest.mark.skip\ndef test_new():\n    pass\n",
        SKIPPED.replace("test_existing", "test_renamed"),
        SOURCE + '\ntext = "@pytest.mark.skip"\n# @pytest.mark.skip\n',
    ],
)
def test_ordinary_conditional_new_and_renamed_tests_do_not_prove_new_skips(repo: Path, replacement: str) -> None:
    (repo / "tests/test_existing.py").write_text(replacement, encoding="utf-8")
    commit(repo)
    report = changes.build_test_changes_report(repo)
    assert report.complete and not report.findings


@pytest.mark.parametrize(
    "marker",
    ["pytest.mark.skip", "pytest.mark.skip()", "pytest.mark.skip('later')", "pytest.mark.skip(reason='later')"],
)
def test_explicit_decorator_addition_is_advisory(repo: Path, marker: str) -> None:
    (repo / "tests/test_existing.py").write_text(
        SOURCE.replace("def test_existing", f"@{marker}\ndef test_existing"), encoding="utf-8"
    )
    commit(repo)
    report = changes.build_test_changes_report(repo)
    assert report.complete and len(report.findings) == 1
    assert report.findings[0].marker_scope == "test" and report.findings[0].severity == "advisory"


@pytest.mark.parametrize("replacement", [SKIPPED.replace("review later", "another reason"), SOURCE])
def test_existing_skip_reason_change_or_removal_is_not_new(repo: Path, replacement: str) -> None:
    path = repo / "tests/test_existing.py"
    path.write_text(SKIPPED, encoding="utf-8")
    commit(repo)
    git(repo, "branch", "-f", "main", "HEAD")
    path.write_text(replacement, encoding="utf-8")
    commit(repo)
    report = changes.build_test_changes_report(repo)
    assert report.complete and not report.findings


def test_inherited_markers_are_compared_without_duplicate_findings(repo: Path) -> None:
    path = repo / "tests/test_existing.py"
    path.write_text("import pytest\nclass TestExample:\n    def test_existing(self):\n        pass\n", encoding="utf-8")
    commit(repo)
    git(repo, "branch", "-f", "main", "HEAD")
    path.write_text(
        "import pytest\npytestmark = pytest.mark.skip\n@pytest.mark.skip\nclass TestExample:\n    @pytest.mark.skip\n    def test_existing(self):\n        pass\n",
        encoding="utf-8",
    )
    commit(repo)
    report = changes.build_test_changes_report(repo)
    assert report.complete and len(report.findings) == 1
    assert report.findings[0].test == "TestExample.test_existing" and report.findings[0].marker_scope == "module"


def test_new_file_and_working_tree_changes_are_excluded(repo: Path) -> None:
    (repo / "tests/test_new.py").write_text(SKIPPED, encoding="utf-8")
    commit(repo)
    (repo / "tests/test_existing.py").write_text(SKIPPED, encoding="utf-8")
    git(repo, "add", "tests/test_existing.py")
    (repo / "tests/test_existing.py").unlink()
    report = changes.build_test_changes_report(repo)
    assert report.complete and not report.findings and not report.inspected_files


def test_base_branch_advancement_uses_merge_base(repo: Path) -> None:
    ancestor = git(repo, "rev-parse", "main")
    (repo / "tests/test_existing.py").write_text(SKIPPED, encoding="utf-8")
    commit(repo)
    head = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "main")
    git(repo, "rm", "tests/test_existing.py")
    commit(repo, "independent base change")
    report = changes.build_test_changes_report(repo, head=head)
    assert report.base != ancestor and report.merge_base == ancestor and len(report.findings) == 1


@pytest.mark.parametrize("data", [b"bad \xff", b"binary\0source", b"def test_broken(:\n"])
def test_bad_source_makes_inspection_incomplete_and_preserves_deletions(repo: Path, data: bytes) -> None:
    (repo / "extra_test.py").write_text(SOURCE, encoding="utf-8")
    commit(repo)
    git(repo, "branch", "-f", "main", "HEAD")
    (repo / "tests/test_existing.py").write_bytes(data)
    git(repo, "rm", "extra_test.py")
    commit(repo)
    report = changes.build_test_changes_report(repo)
    assert not report.complete and len(report.findings) == 1
    assert report.findings[0].code == "tests.deleted-file"


def test_link_replacement_is_not_read_or_called_a_deletion(repo: Path) -> None:
    oid = git(repo, "hash-object", "-w", "--stdin", data=b"/private/outside")
    git(repo, "update-index", "--add", "--cacheinfo", f"120000,{oid},tests/test_existing.py")
    git(repo, "commit", "-qm", "replace with link")
    report = changes.build_test_changes_report(repo)
    assert not report.complete and not report.findings
    assert all("/private/outside" not in item for item in report.limitations)


@pytest.mark.parametrize("limit,complete", [(1, False), (2, True)])
def test_finding_budget_only_marks_actual_excess_incomplete(
    repo: Path, monkeypatch: pytest.MonkeyPatch, limit: int, complete: bool
) -> None:
    path = repo / "tests/test_existing.py"
    original = SOURCE + "\ndef test_second():\n    pass\n"
    path.write_text(original, encoding="utf-8")
    commit(repo)
    git(repo, "branch", "-f", "main", "HEAD")
    path.write_text("pytestmark = pytest.mark.skip\n" + original, encoding="utf-8")
    commit(repo)
    monkeypatch.setattr(changes, "_FINDING_LIMIT", limit)
    report = changes.build_test_changes_report(repo)
    assert report.complete is complete and len(report.findings) == limit


def test_source_and_file_budgets_are_explicit(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (repo / "tests/test_existing.py").write_text(SKIPPED, encoding="utf-8")
    commit(repo)
    monkeypatch.setattr(changes, "_SOURCE_LIMIT", 4)
    report = changes.build_test_changes_report(repo)
    assert not report.complete and not report.findings and not report.inspected_files
    monkeypatch.setattr(changes, "_FILE_LIMIT", 0)
    report = changes.build_test_changes_report(repo)
    assert report.limitations == ["Changed test-file limit reached; remaining files were not inspected."]


def test_missing_revision_is_operational_error(repo: Path) -> None:
    with pytest.raises(RuntimeError, match="Git snapshot"):
        changes.build_test_changes_report(repo, head="absent-ref")


def test_extractor_does_not_import_or_execute_project_source(repo: Path) -> None:
    (repo / "tests/test_existing.py").write_text(
        "raise RuntimeError('must never execute')\n" + SKIPPED, encoding="utf-8"
    )
    commit(repo)
    report = changes.build_test_changes_report(repo)
    assert report.complete and len(report.findings) == 1


def test_dynamic_reason_replaced_by_literal_is_incomplete_not_new_skip(repo: Path) -> None:
    path = repo / "tests/test_existing.py"
    path.write_text(
        SOURCE.replace("def test_existing", "@pytest.mark.skip(reason=reason)\ndef test_existing"), encoding="utf-8"
    )
    commit(repo)
    git(repo, "branch", "-f", "main", "HEAD")
    path.write_text(SKIPPED, encoding="utf-8")
    commit(repo)
    report = changes.build_test_changes_report(repo)
    assert not report.complete and not report.findings
    assert "merge base" in report.limitations[0] and "outside the supported literal syntax" in report.limitations[0]


def test_rename_candidate_budget_is_explicit(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    git(repo, "mv", "tests/test_existing.py", "test_new.py")
    (repo / "other.txt").write_text("new file\n", encoding="utf-8")
    commit(repo)
    monkeypatch.setattr(changes, "_RENAME_LIMIT", 1)
    report = changes.build_test_changes_report(repo)
    assert not report.complete and not report.findings and len(report.renames) == 1
    assert "Rename candidate limit" in report.limitations[0]


@pytest.mark.parametrize("limit,complete,count", [(1, False, 1), (2, True, 2)])
def test_changed_file_budget_distinguishes_exact_limit(
    repo: Path, monkeypatch: pytest.MonkeyPatch, limit: int, complete: bool, count: int
) -> None:
    (repo / "extra_test.py").write_text(SOURCE, encoding="utf-8")
    commit(repo)
    git(repo, "branch", "-f", "main", "HEAD")
    git(repo, "rm", "tests/test_existing.py", "extra_test.py")
    commit(repo)
    monkeypatch.setattr(changes, "_FILE_LIMIT", limit)
    report = changes.build_test_changes_report(repo)
    assert report.complete is complete and len(report.findings) == count


def test_rename_does_not_invoke_configured_external_diff(repo: Path) -> None:
    git(repo, "mv", "tests/test_existing.py", "test_new.py")
    commit(repo)
    git(repo, "config", "diff.external", "this-command-must-not-run")
    git(repo, "config", "diff.renames", "false")
    report = changes.build_test_changes_report(repo)
    assert report.complete and not report.findings and len(report.renames) == 1


@pytest.mark.parametrize("metadata", [b"R100\0old\0", b"D\0old\0new\0", b"R101\0old\0new\0", b"R50\0\xff\0new\0"])
def test_invalid_rename_metadata_is_not_treated_as_a_clean_report(
    repo: Path, monkeypatch: pytest.MonkeyPatch, metadata: bytes
) -> None:
    git(repo, "mv", "tests/test_existing.py", "test_new.py")
    commit(repo)
    original = changes.GitSnapshot.read

    def read(self: changes.GitSnapshot, *args: str, limit: int = 4096) -> bytes:
        return metadata if args[0] == "diff" else original(self, *args, limit=limit)

    monkeypatch.setattr(changes.GitSnapshot, "read", read)
    with pytest.raises(RuntimeError, match="unsupported rename metadata"):
        changes.build_test_changes_report(repo)


def test_unrelated_symlink_rename_does_not_block_regular_file_evidence(repo: Path) -> None:
    oid = git(repo, "hash-object", "-w", "--stdin", data=b"/private/outside")
    git(repo, "update-index", "--add", "--cacheinfo", f"120000,{oid},old_link")
    git(repo, "commit", "-qm", "base link")
    git(repo, "branch", "-f", "main", "HEAD")
    git(repo, "update-index", "--force-remove", "old_link")
    git(repo, "update-index", "--add", "--cacheinfo", f"120000,{oid},new_link")
    git(repo, "update-index", "--force-remove", "tests/test_existing.py")
    (repo / "added.txt").write_text("unrelated\n", encoding="utf-8")
    git(repo, "add", "added.txt")
    git(repo, "commit", "-qm", "rename link and delete test path")
    report = changes.build_test_changes_report(repo)
    assert report.complete and len(report.findings) == 1 and not report.renames


def test_declared_skip_reason_never_appears_in_public_reports(repo: Path) -> None:
    from evagix.reports.test_changes import render_test_changes_json, render_test_changes_text

    (repo / "tests/test_existing.py").write_text(
        SKIPPED.replace("review later", "synthetic-private-reason"), encoding="utf-8"
    )
    commit(repo)
    report = changes.build_test_changes_report(repo)
    assert len(report.findings) == 1
    assert "synthetic-private-reason" not in render_test_changes_json(report) + render_test_changes_text(report)
