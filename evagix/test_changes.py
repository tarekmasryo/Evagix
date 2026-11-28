"""Advisory changes to candidate Python test files and literal skip declarations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from evagix.scanning.git_snapshot import GitSnapshot, TreeEntry
from evagix.scanning.pytest_skips import TestDeclaration, extract_test_declarations

_SOURCE_LIMIT = 500_000
_FILE_LIMIT = 200
_FINDING_LIMIT = 1000
_RENAME_LIMIT = 200


@dataclass(frozen=True)
class TestChangeFinding:
    code: str
    path: str
    revision: str
    line: int
    column: int
    test: str | None = None
    previous_path: str | None = None
    previous_line: int | None = None
    marker_scope: str | None = None
    severity: str = "advisory"


@dataclass(frozen=True)
class TestFileRename:
    previous_path: str
    path: str
    similarity: int


@dataclass(frozen=True)
class TestChangesReport:
    base: str
    head: str
    merge_base: str
    inspected_files: list[str]
    renames: list[TestFileRename]
    limitations: list[str]
    findings: list[TestChangeFinding]

    @property
    def complete(self) -> bool:
        return not self.limitations


def _test_path(path: str) -> bool:
    name = PurePosixPath(path).name
    return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))


def _renames(git: GitSnapshot, before: str, after: str) -> dict[str, tuple[str, int]]:
    output = git.read(
        "diff",
        "--name-status",
        "-z",
        "--no-relative",
        "--no-ext-diff",
        "--no-textconv",
        "--ignore-submodules=all",
        "--find-renames=50%",
        f"-l{_RENAME_LIMIT}",
        "--diff-filter=R",
        before,
        after,
        "--",
        limit=8_000_000,
    )
    records = output.split(b"\0")
    result = {}
    try:
        if records.pop() != b"" or len(records) % 3:
            raise ValueError
        for index in range(0, len(records), 3):
            status, old, new = records[index : index + 3]
            if not status.startswith(b"R") or not status[1:].isdigit() or not 50 <= int(status[1:]) <= 100:
                raise ValueError
            result[old.decode("utf-8")] = (new.decode("utf-8"), int(status[1:]))
    except (ValueError, UnicodeError) as exc:
        raise RuntimeError("Git returned unsupported rename metadata.") from exc
    return result


def _read_tests(
    git: GitSnapshot, entry: TreeEntry, path: str, revision: str, report: TestChangesReport
) -> dict[str, TestDeclaration] | None:
    if not entry.regular:
        report.limitations.append(f"{path} ({revision}): not a regular tracked file; skip declarations not inspected.")
        return None
    try:
        return extract_test_declarations(git.text(entry, limit=_SOURCE_LIMIT))
    except (RuntimeError, ValueError) as exc:
        # Parser/source errors can contain repository text. Emit a fixed reason.
        reason = (
            str(exc)
            if type(exc) is ValueError
            and str(exc)
            in {
                "multiple pytestmark assignments are not supported",
                "pytestmark has an unsupported rebinding or mutation",
                "skip marker arguments are outside the supported literal syntax",
                "Python syntax tree exceeds the inspection limit",
                "literal skip marker has an unsupported or ambiguous pytest binding",
                "duplicate Python declarations prevent an unambiguous comparison",
                "Python source cannot be safely parsed by this interpreter",
            }
            else "unavailable, oversized, non-UTF-8 or invalid Python source"
        )
        report.limitations.append(f"{path} ({revision}): {reason}; skip declarations not inspected.")
        return None


def build_test_changes_report(root: Path, *, base: str = "main", head: str = "HEAD") -> TestChangesReport:
    git = GitSnapshot(root)
    base_oid, head_oid = git.resolve(base), git.resolve(head)
    ancestor = git.merge_base(base_oid, head_oid)
    before, after = git.tree(ancestor), git.tree(head_oid)
    report = TestChangesReport(base_oid, head_oid, ancestor, [], [], [], [])
    removed = {path for path, entry in before.items() if entry.regular and path not in after}
    added = {path for path, entry in after.items() if entry.regular and path not in before}
    rename_candidates = _renames(git, ancestor, head_oid) if removed and added else {}
    if any(old not in before or new not in after for old, (new, _) in rename_candidates.items()):
        raise RuntimeError("Git rename metadata does not match the selected trees.")
    renamed = {
        old: (new, similarity)
        for old, (new, similarity) in rename_candidates.items()
        if old in removed and new in added
    }
    if max(len(removed), len(added)) > _RENAME_LIMIT and removed and added:
        report.limitations.append("Rename candidate limit exceeded; edited moves may appear as removed paths.")
    candidates = sorted(path for path, entry in before.items() if _test_path(path) and (entry != after.get(path)))

    def append(finding: TestChangeFinding) -> bool:
        if len(report.findings) >= _FINDING_LIMIT:
            report.limitations.append("Finding limit reached; remaining changes were not evaluated.")
            return False
        report.findings.append(finding)
        return True

    for index, path in enumerate(candidates):
        if index >= _FILE_LIMIT:
            report.limitations.append("Changed test-file limit reached; remaining files were not inspected.")
            break
        old = before[path]
        if not old.regular:
            report.limitations.append(f"{path} (merge base): not a regular tracked file; not inspected.")
            continue
        new_path = path
        if path in renamed:
            new_path, similarity = renamed[path]
            report.renames.append(TestFileRename(path, new_path, similarity))
            if not _test_path(new_path):
                report.limitations.append(
                    f"{path}: rename destination is outside the supported test filename patterns; collection not assessed."
                )
                continue
        elif path not in after:
            # This proves path removal, not loss of test behavior elsewhere.
            report.inspected_files.append(path)
            if not append(TestChangeFinding("tests.deleted-file", path, "merge_base", 1, 1)):
                break
            continue
        new = after[new_path]
        if old == new:
            report.inspected_files.append(new_path)
            continue
        previous = _read_tests(git, old, path, "merge base", report)
        current = _read_tests(git, new, new_path, "head", report)
        if previous is None or current is None:
            continue
        report.inspected_files.append(new_path)
        for name, test in current.items():
            earlier = previous.get(name)
            if earlier is None or earlier.skip is not None or test.skip is None:
                continue
            if not append(
                TestChangeFinding(
                    "tests.unconditional-skip-added",
                    new_path,
                    "head",
                    test.skip.line,
                    test.skip.column,
                    name,
                    path,
                    earlier.line,
                    test.skip.scope,
                )
            ):
                return report
    return report
