from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from evagix import pr_summary
from evagix import test_changes as changes
from evagix.verification.github_pr_checks import PullRequestChecks

PR_URL = "https://github.com/owner/repo/pull/7"
SOURCE = "import pytest\n\ndef test_existing():\n    assert 2 + 2 == 4\n"
SKIPPED = SOURCE.replace("def test_existing", "@pytest.mark.skip(reason='later')\ndef test_existing")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
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
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


@dataclass(frozen=True)
class _Repo:
    root: Path
    base: str
    head: str

    def args(self, *, expectations: bool = False) -> list[str]:
        args = [PR_URL, "--repo", str(self.root), "--base", self.base, "--head", self.head]
        if expectations:
            args.extend(("--expectations", ".github/checks.json"))
        return args


def _repository(root: Path, before: dict[str, str | bytes], after: dict[str, str | bytes]) -> _Repo:
    _git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("# Fixture project\n", encoding="utf-8")
    (root / ".github").mkdir()
    (root / ".github/checks.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "repository_id": 17,
                "checks": [{"revision": "head", "kind": "check_run", "name": "tests", "producer_id": 9}],
            }
        ),
        encoding="utf-8",
    )
    for path, content in before.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "base")
    base = _git(root, "rev-parse", "HEAD")
    for path in before.keys() - after.keys():
        (root / path).unlink()
    for path, content in after.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    _git(root, "add", ".")
    _git(root, "commit", "--allow-empty", "-qm", "head")
    return _Repo(root, base, _git(root, "rev-parse", "HEAD"))


@pytest.fixture(autouse=True)
def _no_unexpected_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVAGIX_GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(pr_summary, "collect_pr_checks", lambda *a, **k: pytest.fail("Unexpected network collection"))
    monkeypatch.setattr(
        pr_summary, "inspect_github_junit", lambda *a, **k: pytest.fail("Unexpected artifact collection")
    )


def _collect(monkeypatch: pytest.MonkeyPatch, repo: _Repo, *, failed: bool = False) -> list[str]:
    calls: list[str] = []

    def collect(url: str, *, token: str | None = None) -> PullRequestChecks:
        assert token is None
        calls.append(url)
        return PullRequestChecks(
            {
                "schema_version": "1.0",
                "kind": "github_pr_checks",
                "repository": "owner/repo",
                "repository_id": 17,
                "pull_request": 7,
                "state": "open",
                "base_sha": repo.base,
                "head_sha": repo.head,
                "test_merge_status": "unavailable",
                "completeness": "complete",
                "policy_decision": "not_evaluated",
                "required_checks": "unknown",
                "revisions": [
                    {
                        "kind": "head",
                        "sha": repo.head,
                        "completeness": "complete",
                        "checks": [
                            {
                                "kind": "check_run",
                                "id": 31,
                                "name": "tests",
                                "producer": "Fixture App",
                                "producer_id": 9,
                                "status": "completed",
                                "conclusion": "failure" if failed else "success",
                                "result": "failed" if failed else "passed",
                                "url": None,
                            }
                        ],
                    }
                ],
            }
        )

    monkeypatch.setattr(pr_summary, "collect_pr_checks", collect)
    return calls


def _section(output: str) -> str:
    return output.split("## Test change review\n", 1)[1].split("\n## ", 1)[0]


@pytest.mark.parametrize("use_expectations", [False, True])
@pytest.mark.parametrize(
    "before,after,code,renamed",
    [
        ({"test_example.py": SOURCE}, {"test_example.py": SOURCE.replace("2 + 2", "2 * 2")}, None, False),
        ({"test_example.py": SOURCE}, {}, "tests.deleted-file", False),
        ({"test_example.py": SOURCE}, {"test_renamed.py": SOURCE}, None, True),
        ({"test_example.py": SOURCE}, {"test_renamed.py": SKIPPED}, "tests.unconditional-skip-added", True),
        ({"test_example.py": SOURCE}, {"test_example.py": SKIPPED}, "tests.unconditional-skip-added", False),
        (
            {"test_example.py": SOURCE},
            {
                "test_example.py": SOURCE.replace(
                    "def test_existing", "@pytest.mark.skipif(True, reason='conditional')\ndef test_existing"
                )
            },
            None,
            False,
        ),
        ({"test_example.py": SKIPPED}, {"test_example.py": SKIPPED.replace("later", "still later")}, None, False),
        ({"test_example.py": SKIPPED}, {"test_example.py": SOURCE}, None, False),
    ],
    ids=[
        "healthy",
        "deleted",
        "renamed",
        "renamed-with-skip",
        "unconditional",
        "conditional",
        "existing-skip",
        "skip-removed",
    ],
)
def test_committed_test_changes_are_advisory_in_both_summary_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    use_expectations: bool,
    before: dict[str, str],
    after: dict[str, str],
    code: str | None,
    renamed: bool,
) -> None:
    repo = _repository(tmp_path, before, after)
    calls = _collect(monkeypatch, repo)
    assert pr_summary.main(repo.args(expectations=use_expectations)) == 0
    captured = capsys.readouterr()
    assert captured.err == "" and calls == [PR_URL]
    section = _section(captured.out)
    assert "**Inspection:** complete" in section
    assert f"**Findings:** {int(code is not None)}." in section
    assert repo.base in section and repo.head in section
    assert "Changes may be intentional" in section
    assert "execution, test quality and merge readiness are not verified" in section
    if code is not None:
        assert code in section
    else:
        assert "No findings within the inspected scope" in section
    assert ("Rename candidate:" in section) is renamed
    if renamed:
        assert "test_renamed.py" in section and "tests.deleted-file" not in section
    assert "## Evagix PR checks" in captured.out
    assert "## Deleted-file reference review" in captured.out
    assert "## Deleted-script instruction review" in captured.out


@pytest.mark.parametrize("kind", ["syntax", "encoding", "dynamic-skip", "budget"])
@pytest.mark.parametrize("failed_junit", [False, True])
def test_incomplete_test_inspection_keeps_findings_and_complete_junit_visible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    kind: str,
    failed_junit: bool,
) -> None:
    content: str | bytes = {
        "syntax": "def test_existing(:\n",
        "encoding": b"\xff",
        "dynamic-skip": SKIPPED.replace("'later'", "reason_from_config"),
        "budget": SKIPPED,
    }[kind]
    repo = _repository(
        tmp_path,
        {"test_example.py": SOURCE, "test_removed.py": "def test_removed():\n    pass\n"},
        {"test_example.py": content},
    )
    if kind == "budget":
        monkeypatch.setattr(changes, "_SOURCE_LIMIT", 4)
    calls = _collect(monkeypatch, repo)
    junit = tmp_path / "results.xml"
    marker = "<failure/>" if failed_junit else ""
    junit.write_text(
        f'<testsuite name="pytest" tests="1" failures="{int(failed_junit)}" errors="0" skipped="0">'
        f'<testcase name="test_case">{marker}</testcase></testsuite>',
        encoding="utf-8",
    )
    assert pr_summary.main([*repo.args(), "--junit-report", str(junit)]) == 1
    captured = capsys.readouterr()
    assert captured.err == "" and calls == [PR_URL]
    section = _section(captured.out)
    assert "**Inspection:** incomplete" in section
    assert "tests.deleted-file" in section and "test_removed.py" in section
    assert "skip declarations not inspected" in section
    assert "## Evagix PR checks" in captured.out and "passed: 1" in captured.out
    assert "## Deleted-file reference review" in captured.out
    assert "## Deleted-script instruction review" in captured.out
    assert "## Local pytest JUnit report" in captured.out
    assert "unverified" in captured.out


@pytest.mark.parametrize("marker,failures,skipped", [("", 0, 0), ("<failure/>", 1, 0), ("<skipped/>", 0, 1)])
def test_test_findings_and_junit_outcomes_do_not_override_other_review_sections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    marker: str,
    failures: int,
    skipped: int,
) -> None:
    instructions = "See [verification](scripts/verify.py).\n\nRun `python scripts/verify.py`.\n"
    repo = _repository(
        tmp_path,
        {"README.md": instructions, "scripts/verify.py": "pass\n", "test_example.py": SOURCE},
        {"README.md": instructions},
    )
    _collect(monkeypatch, repo, failed=True)
    junit = tmp_path / "results.xml"
    junit.write_text(
        f'<testsuite name="pytest" tests="1" failures="{failures}" errors="0" skipped="{skipped}">'
        f'<testcase name="test_case">{marker}</testcase></testsuite>',
        encoding="utf-8",
    )
    assert pr_summary.main([*repo.args(), "--junit-report", str(junit)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "failed: 1" in captured.out
    assert "scripts/verify.py" in captured.out
    assert "## Deleted-file reference review" in captured.out
    assert "## Deleted-script instruction review" in captured.out
    assert "tests.deleted-file" in _section(captured.out)
    assert "## Local pytest JUnit report" in captured.out


def test_worktree_index_and_untracked_changes_do_not_replace_committed_test_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = SOURCE + "\nraise RuntimeError('Fixture module must never execute')\n"
    repo = _repository(
        tmp_path,
        {"test_example.py": source},
        {"test_example.py": source.replace("def test_existing", "@pytest.mark.skip\ndef test_existing")},
    )
    _collect(monkeypatch, repo)
    (tmp_path / "test_example.py").write_text(SOURCE, encoding="utf-8")
    _git(tmp_path, "add", "test_example.py")
    (tmp_path / "test_untracked.py").write_text(SKIPPED, encoding="utf-8")
    status = _git(tmp_path, "status", "--porcelain")
    assert pr_summary.main(repo.args()) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "tests.unconditional-skip-added" in _section(captured.out)
    assert "test_untracked.py" not in captured.out
    assert _git(tmp_path, "status", "--porcelain") == status


def test_test_inspection_failure_emits_no_summary_or_repository_exception_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repository(tmp_path, {"test_example.py": SOURCE}, {"test_example.py": SKIPPED})

    def unavailable(*args: object, **kwargs: object) -> None:
        raise RuntimeError("private object error")

    monkeypatch.setattr(pr_summary, "build_test_changes_report", unavailable)
    assert pr_summary.main(repo.args()) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err.startswith("ERROR:")
    assert "private object error" not in captured.err
