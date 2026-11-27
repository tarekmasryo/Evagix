from __future__ import annotations

import hashlib
import io
import re
import subprocess
import zipfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from evagix import pr_summary
from evagix.verification import github_junit
from evagix.verification.github_collection import GitHubCollectionError
from evagix.verification.github_pr_checks import PullRequestChecks

PR_URL = "https://github.com/owner/repo/pull/7"
API_ROOT = "/repos/owner/repo"
MEMBER = "evagix-quality-junit.xml"
HEADING = "## GitHub-associated JUnit report"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=Fixture User", "-c", "user.email=fixture@example.invalid", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


@dataclass(frozen=True)
class _Repo:
    path: Path
    base: str
    head: str

    def args(self) -> list[str]:
        return [PR_URL, "--repo", str(self.path), "--base", self.base, "--head", self.head]


@pytest.fixture
def repo(tmp_path: Path) -> _Repo:
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init", "-b", "main")
    (root / "scripts").mkdir()
    (root / "scripts/check.py").write_text("raise RuntimeError('must not execute')\n", encoding="utf-8")
    (root / "README.md").write_text("Run the [checks](scripts/check.py).\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("Run `python scripts/check.py` before submitting changes.\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "--no-gpg-sign", "-m", "initial")
    base = _git(root, "rev-parse", "HEAD")
    (root / "scripts/check.py").unlink()
    _git(root, "add", ".")
    _git(root, "commit", "--no-gpg-sign", "-m", "remove script")
    return _Repo(root, base, _git(root, "rev-parse", "HEAD"))


@pytest.fixture(autouse=True)
def _no_unexpected_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVAGIX_GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(github_junit, "_Client", lambda *a, **k: pytest.fail("Unexpected artifact network"))
    monkeypatch.setattr(pr_summary, "collect_pr_checks", lambda *a, **k: pytest.fail("Unexpected PR collection"))


def _xml(marker: str = "", *, tests: int = 1, **counts: int) -> bytes:
    counters = dict(tests=tests, failures=0, errors=0, skipped=0)
    counters.update(counts)
    attrs = " ".join(f'{key}="{value}"' for key, value in counters.items())
    case = f'<testcase name="private-test-name">{marker}</testcase>' if tests else ""
    return f'<testsuite name="private-suite-name" {attrs}>{case}</testsuite>'.encode()


def _archive(path: Path, xml: bytes | None = None, *, member: str = MEMBER) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, xml if xml is not None else _xml())
    contents = buffer.getvalue()
    path.write_bytes(contents)
    return contents


def _options(path: Path) -> list[str]:
    return [
        "--junit-archive",
        str(path),
        "--junit-run-id",
        "100",
        "--junit-attempt",
        "2",
        "--junit-artifact-id",
        "300",
    ]


def _run(repo: _Repo, *, attempt: int = 2, head_repository: int = 17, revision: str | None = None) -> dict[str, Any]:
    return {
        "id": 100,
        "repository": {"id": 17},
        "head_repository": {"id": head_repository},
        "workflow_id": 200,
        "head_sha": revision if revision is not None else repo.head,
        "run_attempt": attempt,
        "event": "pull_request",
        "status": "completed",
        "conclusion": "success",
    }


def _artifact(contents: bytes, run: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": 300,
        "size_in_bytes": len(contents),
        "digest": "sha256:" + hashlib.sha256(contents).hexdigest(),
        "expired": False,
        "workflow_run": {
            "id": run["id"],
            "repository_id": run["repository"]["id"],
            "head_repository_id": run["head_repository"]["id"],
            "head_sha": run["head_sha"],
        },
    }


def _responses(contents: bytes, run: dict[str, Any], *, attempt: dict[str, Any] | None = None) -> list[Any]:
    artifact = _artifact(contents, run)
    attempt = attempt if attempt is not None else run
    return [
        {"id": 17, "full_name": "owner/repo"},
        deepcopy(run),
        deepcopy(attempt),
        deepcopy(artifact),
        deepcopy(artifact),
        deepcopy(attempt),
        deepcopy(run),
    ]


def _checks(
    repo: _Repo,
    *,
    head_repository: int | None = 17,
    repository: int = 17,
    complete: bool = True,
    outcome: str = "failed",
) -> PullRequestChecks:
    completeness = "complete" if complete else "incomplete"
    checks = [
        {
            "kind": "check_run",
            "id": 401,
            "name": "required-tests",
            "producer": "Fixture App",
            "producer_id": 9,
            "status": "completed",
            "conclusion": "failure" if outcome == "failed" else "success",
            "result": outcome,
            "url": None,
        }
    ]
    return PullRequestChecks(
        {
            "schema_version": "1.0",
            "kind": "github_pr_checks",
            "repository": "owner/repo",
            "repository_id": repository,
            "pull_request": 7,
            "state": "open",
            "base_sha": repo.base,
            "head_sha": repo.head,
            "test_merge_status": "unavailable",
            "completeness": completeness,
            "policy_decision": "not_evaluated",
            "required_checks": "unknown",
            "revisions": [{"kind": "head", "sha": repo.head, "completeness": completeness, "checks": checks}],
        },
        _head_repository_id=head_repository,
    )


def _install(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[Any],
    checks: PullRequestChecks | None = None,
) -> list[str]:
    events: list[str] = []
    pending = list(responses)

    class Client:
        def __init__(self, token: str | None) -> None:
            self.token = token

        def get(self, path: str) -> tuple[dict[str, Any], str]:
            events.append(path)
            assert pending, "Unexpected extra artifact collection"
            response = pending.pop(0)
            if isinstance(response, Exception):
                raise response
            return deepcopy(response), ""

    monkeypatch.setattr(github_junit, "_Client", Client)
    if checks is not None:

        def collect(url: str, **kwargs: Any) -> PullRequestChecks:
            assert url == PR_URL
            assert not pending, "PR snapshot must be collected after artifact association"
            events.append("PR")
            return checks

        monkeypatch.setattr(pr_summary, "collect_pr_checks", collect)
    return events


def _plain(text: str) -> str:
    words = re.sub(r"\s+", " ", re.sub(r"[*`]", "", text)).lower()
    return re.sub(r" +([;.,])", r"\1", words)


def _section(text: str) -> str:
    return text.split(HEADING, 1)[1]


@pytest.mark.parametrize(
    "xml,outcome",
    [
        (_xml(), "passed"),
        (_xml("<failure/>", failures=1), "failed"),
        (_xml("<error/>", errors=1), "failed"),
        (_xml("<skipped/>", skipped=1), "skipped_only"),
        (_xml(tests=0), "empty"),
    ],
)
def test_associated_xml_and_failed_checks_remain_separate(
    repo: _Repo,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    xml: bytes,
    outcome: str,
) -> None:
    path = tmp_path / "results.zip"
    contents = _archive(path, xml)
    events = _install(monkeypatch, _responses(contents, _run(repo)), _checks(repo))
    before = _git(repo.path, "status", "--porcelain")
    assert pr_summary.main([*repo.args(), *_options(path)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    section = _plain(_section(captured.out))
    assert f"reported outcome: {outcome}" in section
    assert "repository identity: match" in section and "head repository identity: match" in section
    assert "artifact-producing attempt: unknown" in section
    assert "tested revision: unknown" in section and "execution verification: unverified" in section
    assert "not_evaluated" in section
    assert "within the selected run" in section and "does not select the latest workflow or pr run" in section
    assert repo.head in section
    assert "failed: 1" in captured.out and "required-tests" in captured.out
    assert "Deleted-file reference review" in captured.out and "Deleted-script instruction review" in captured.out
    assert "All sections use the requested base and head commits" not in captured.out
    assert "private-test-name" not in captured.out and "private-suite-name" not in captured.out
    assert events == [
        API_ROOT,
        API_ROOT + "/actions/runs/100",
        API_ROOT + "/actions/runs/100/attempts/2",
        API_ROOT + "/actions/artifacts/300",
        API_ROOT + "/actions/artifacts/300",
        API_ROOT + "/actions/runs/100/attempts/2",
        API_ROOT + "/actions/runs/100",
        "PR",
    ]
    assert _git(repo.path, "status", "--porcelain") == before


@pytest.mark.parametrize("head_repository", [17, 23])
def test_same_repo_and_fork_heads_match_by_provider_identity(
    repo: _Repo,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    head_repository: int,
) -> None:
    path = tmp_path / "results.zip"
    contents = _archive(path)
    _install(
        monkeypatch,
        _responses(contents, _run(repo, head_repository=head_repository)),
        _checks(repo, head_repository=head_repository),
    )
    assert pr_summary.main([*repo.args(), *_options(path)]) == 0
    assert "head repository identity: match" in _plain(_section(capsys.readouterr().out))


@pytest.mark.parametrize(
    "repository,head_repository,field,expected",
    [
        (999, 17, "repository identity", "mismatch"),
        (17, 23, "head repository identity", "mismatch"),
        (17, None, "head repository identity", "unknown"),
    ],
)
def test_same_sha_is_not_enough_when_pr_repository_identity_differs_or_is_unknown(
    repo: _Repo,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    repository: int,
    head_repository: int | None,
    field: str,
    expected: str,
) -> None:
    path = tmp_path / "results.zip"
    contents = _archive(path)
    _install(
        monkeypatch,
        _responses(contents, _run(repo)),
        _checks(repo, repository=repository, head_repository=head_repository),
    )
    assert pr_summary.main([*repo.args(), *_options(path)]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    section = _plain(_section(captured.out))
    assert f"{field}: {expected}" in section
    assert "observed case rows" not in section and "reported outcome: passed" not in section
    assert "Deleted-file reference review" in captured.out


@pytest.mark.parametrize(
    "case",
    [
        "old-revision",
        "stale-attempt",
        "digest-mismatch",
        "missing-digest",
        "missing-metadata",
        "artifact-run-mismatch",
        "incomplete-xml",
    ],
)
def test_nonmatching_stale_and_incomplete_artifacts_are_visible_advisory_evidence(
    repo: _Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    path = tmp_path / "results.zip"
    contents = _archive(path, _xml(tests=2) if case == "incomplete-xml" else None)
    run = _run(
        repo, revision=repo.base if case == "old-revision" else None, attempt=3 if case == "stale-attempt" else 2
    )
    responses = _responses(contents, run, attempt=_run(repo) if case == "stale-attempt" else None)
    for index in (3, 4):
        if case == "digest-mismatch":
            responses[index]["digest"] = "sha256:" + "0" * 64
        elif case == "missing-digest":
            responses[index]["digest"] = None
        elif case == "artifact-run-mismatch":
            responses[index]["workflow_run"]["id"] = 101
    if case == "missing-metadata":
        del responses[1]["head_sha"]
        responses = responses[:2]
    _install(monkeypatch, responses, _checks(repo))
    assert pr_summary.main([*repo.args(), *_options(path)]) == 1
    captured = capsys.readouterr()
    assert captured.err == "" and HEADING in captured.out
    section = _plain(_section(captured.out))
    expected = {
        "old-revision": "mismatch",
        "stale-attempt": "stale",
        "digest-mismatch": "mismatched",
        "missing-digest": "artifact_digest_unavailable",
        "missing-metadata": "metadata_incomplete",
        "artifact-run-mismatch": "mismatch",
        "incomplete-xml": "count_mismatch",
    }
    assert expected[case] in section
    assert "unknown" in section and "not_evaluated" in section
    assert "required-tests" in captured.out
    if case in {"digest-mismatch", "missing-digest", "missing-metadata", "artifact-run-mismatch"}:
        assert "observed case rows" not in section
    elif case == "old-revision":
        assert "revision match: mismatch" in section
        assert "xml observations for the selected artifact/run, not proof of pr test execution" in section
        assert repo.base in section and repo.head in section


@pytest.mark.parametrize("kind", ["missing", "directory", "corrupt-zip", "malformed-xml"])
def test_bad_artifact_emits_no_partial_summary_and_never_collects_pr(
    repo: _Repo, tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str
) -> None:
    path = tmp_path / "private-archive-name.zip"
    if kind == "directory":
        path.mkdir()
    elif kind == "corrupt-zip":
        path.write_bytes(b"private-invalid-archive-bytes")
    elif kind == "malformed-xml":
        _archive(path, b"<testsuite")
    assert pr_summary.main([*repo.args(), *_options(path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err.startswith("ERROR:")
    assert "private" not in captured.err and str(tmp_path) not in captured.err


@pytest.mark.parametrize("code", ["forbidden", "not_found", "transport_error", "run_changed"])
def test_provider_failure_emits_no_partial_combined_summary(
    repo: _Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], code: str
) -> None:
    path = tmp_path / "results.zip"
    _archive(path)
    _install(monkeypatch, [GitHubCollectionError(code)])
    assert pr_summary.main([*repo.args(), *_options(path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err.startswith("ERROR:")


def test_invalid_explicit_base_expectations_fail_before_artifact_network(
    repo: _Repo, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "results.zip"
    _archive(path)
    assert pr_summary.main([*repo.args(), "--expectations", ".github/missing.json", *_options(path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "regular tracked file" in captured.err


@pytest.mark.parametrize("field", ["base", "head"])
def test_pr_advanced_after_artifact_collection_cannot_publish_mixed_snapshots(
    repo: _Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], field: str
) -> None:
    path = tmp_path / "results.zip"
    contents = _archive(path)
    moved = _Repo(repo.path, "b" * 40 if field == "base" else repo.base, "c" * 40 if field == "head" else repo.head)
    _install(monkeypatch, _responses(contents, _run(repo)), _checks(moved))
    assert pr_summary.main([*repo.args(), *_options(path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "no longer matches" in captured.err


def test_good_artifact_cannot_override_incomplete_check_inventory(
    repo: _Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "results.zip"
    contents = _archive(path)
    _install(monkeypatch, _responses(contents, _run(repo)), _checks(repo, complete=False))
    assert pr_summary.main([*repo.args(), *_options(path)]) == 1
    output = capsys.readouterr().out
    assert "reported outcome: passed" in _plain(_section(output))
    assert "incomplete" in output


def test_current_run_and_selected_old_attempt_keep_distinct_conclusions(
    repo: _Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "results.zip"
    contents = _archive(path)
    latest = _run(repo, attempt=3)
    latest["conclusion"] = "failure"
    _install(monkeypatch, _responses(contents, latest, attempt=_run(repo)), _checks(repo, outcome="passed"))
    assert pr_summary.main([*repo.args(), *_options(path)]) == 1
    section = _plain(_section(capsys.readouterr().out))
    assert "currentness: stale" in section
    assert "run state: completed; conclusion: failure" in section
    assert "selected attempt state: completed; conclusion: success" in section
    assert "reported outcome: passed" in section
    assert "artifact-producing attempt: unknown" in section


def test_good_artifact_cannot_override_incomplete_repository_inspection(
    repo: _Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo.path / "AGENTS.md").write_bytes(b"\xff")
    _git(repo.path, "add", "AGENTS.md")
    _git(repo.path, "commit", "--no-gpg-sign", "-m", "invalid context encoding")
    updated = _Repo(repo.path, repo.base, _git(repo.path, "rev-parse", "HEAD"))
    path = tmp_path / "results.zip"
    contents = _archive(path)
    _install(monkeypatch, _responses(contents, _run(updated)), _checks(updated))
    assert pr_summary.main([*updated.args(), *_options(path)]) == 1
    output = capsys.readouterr().out
    assert "reported outcome: passed" in _plain(_section(output))
    assert "incomplete" in output.split(HEADING, 1)[0]


@pytest.mark.parametrize(
    "option", ["--junit-archive", "--junit-run-id", "--junit-attempt", "--junit-artifact-id", "--junit-member"]
)
@pytest.mark.parametrize("kind", ["orphan", "duplicate"])
def test_optional_binding_arguments_must_be_complete_and_unique_before_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], option: str, kind: str
) -> None:
    values = {
        "--junit-archive": "private.zip",
        "--junit-run-id": "100",
        "--junit-attempt": "2",
        "--junit-artifact-id": "300",
        "--junit-member": MEMBER,
    }
    args = [option, values[option]]
    if kind == "duplicate":
        args = [*_options(Path("private.zip")), *args]
        if option == "--junit-member":
            args.extend([option, values[option]])
    monkeypatch.setattr(pr_summary, "GitSnapshot", lambda *a, **k: pytest.fail("Unexpected repository read"))
    monkeypatch.setattr(
        pr_summary, "inspect_github_junit", lambda *a, **k: pytest.fail("Unexpected artifact read"), raising=False
    )
    common = [PR_URL, "--repo", str(tmp_path), "--base", "a" * 40, "--head", "b" * 40]
    assert pr_summary.main([*common, *args]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err.startswith("ERROR:")
    assert "private.zip" not in captured.err


def test_local_xml_and_github_archive_cannot_be_mixed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(pr_summary, "read_junit_report", lambda *a, **k: pytest.fail("Unexpected local report read"))
    monkeypatch.setattr(pr_summary, "GitSnapshot", lambda *a, **k: pytest.fail("Unexpected repository read"))
    common = [PR_URL, "--repo", str(tmp_path), "--base", "a" * 40, "--head", "b" * 40]
    assert pr_summary.main([*common, "--junit-report", "private.xml", *_options(Path("private.zip"))]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "private" not in captured.err


@pytest.mark.parametrize(
    "option,value",
    [
        ("--junit-run-id", "0"),
        ("--junit-attempt", "-1"),
        ("--junit-artifact-id", str(2**63)),
        ("--junit-run-id", "private-not-a-number"),
        ("--junit-member", "../private.xml"),
        ("--junit-member", "/private.xml"),
        ("--junit-member", "C:\\private.xml"),
    ],
)
def test_invalid_binding_values_are_rejected_before_io_without_echoing_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], option: str, value: str
) -> None:
    monkeypatch.setattr(pr_summary, "GitSnapshot", lambda *a, **k: pytest.fail("Unexpected repository read"))
    monkeypatch.setattr(pr_summary, "inspect_github_junit", lambda *a, **k: pytest.fail("Unexpected artifact read"))
    binding = _options(Path("private.zip"))
    if option in binding:
        binding[binding.index(option) + 1] = value
    else:
        binding.extend([option, value])
    common = [PR_URL, "--repo", str(tmp_path), "--base", "a" * 40, "--head", "b" * 40]
    assert pr_summary.main([*common, *binding]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err.startswith("ERROR:")
    assert value not in captured.err and "private" not in captured.err


@pytest.mark.parametrize("local", [False, True])
def test_existing_modes_never_inspect_archives_or_add_association_text(
    repo: _Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], local: bool
) -> None:
    monkeypatch.setattr(
        pr_summary, "inspect_github_junit", lambda *a, **k: pytest.fail("Unexpected artifact read"), raising=False
    )
    monkeypatch.setattr(pr_summary, "collect_pr_checks", lambda *a, **k: _checks(repo))
    args = repo.args()
    if local:
        path = tmp_path / "local.xml"
        path.write_bytes(_xml())
        args.extend(["--junit-report", str(path)])
    assert pr_summary.main(args) == 0
    before = capsys.readouterr()
    (repo.path / "junit.zip").write_bytes(b"unrequested invalid archive")
    monkeypatch.chdir(repo.path)
    assert pr_summary.main(args) == 0
    after = capsys.readouterr()
    assert after == before
    assert HEADING not in after.out
    if local:
        assert "## Local pytest JUnit report" in after.out
        assert "Source verification: `unverified`" in after.out
    else:
        assert "All sections use the requested base and head commits" in after.out


def test_archive_relative_path_uses_caller_directory_and_explicit_member(
    repo: _Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "results.zip"
    contents = _archive(path, member="reports/pytest.xml")
    (repo.path / path.name).write_bytes(b"repository-controlled invalid archive")
    monkeypatch.chdir(tmp_path)
    _install(monkeypatch, _responses(contents, _run(repo)), _checks(repo))
    assert pr_summary.main([*repo.args(), *_options(Path(path.name)), "--junit-member", "reports/pytest.xml"]) == 0
    assert HEADING in capsys.readouterr().out
    assert not (tmp_path / "reports").exists()


def test_association_output_omits_all_xml_free_text(
    repo: _Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "results.zip"
    xml = _xml("<failure message='private-message'>private-traceback</failure>", failures=1)
    xml = xml.replace(b"</testsuite>", b"<system-out>private-log</system-out></testsuite>")
    contents = _archive(path, xml)
    _install(monkeypatch, _responses(contents, _run(repo)), _checks(repo))
    assert pr_summary.main([*repo.args(), *_options(path)]) == 0
    output = capsys.readouterr().out
    assert "private-" not in output
    assert "reported outcome: failed" in _plain(_section(output))


def test_combined_byte_limit_preserves_no_partial_output(
    repo: _Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "results.zip"
    contents = _archive(path)
    _install(monkeypatch, _responses(contents, _run(repo)), _checks(repo))
    monkeypatch.setattr(pr_summary, "_SUMMARY_BYTES", 64)
    assert pr_summary.main([*repo.args(), *_options(path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "exceeds" in captured.err
