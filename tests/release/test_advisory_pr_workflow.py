from __future__ import annotations

import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from evagix.reports.test_changes import render_test_changes_markdown
from evagix.test_changes import build_test_changes_report

ROOT = Path(__file__).resolve().parents[2]


def _job(name: str = "advisory-pr-review") -> str:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    return re.split(r"\n  [a-z][a-z-]*:\n", workflow.split(f"\n  {name}:\n", 1)[1], maxsplit=1)[0]


def _step(name: str, job: str = "advisory-pr-review") -> str:
    tail = _job(job).split(f"      - name: {name}\n", 1)[1]
    return re.split(r"\n      - ", tail, maxsplit=1)[0]


def _publisher() -> str:
    return textwrap.dedent(_step("Publish advisory review summary").split("        run: |\n", 1)[1])


def test_advisory_job_waits_for_existing_gates_without_weakening_them() -> None:
    job = _job()
    assert "needs: [quality, test, self-governance, build, artifact-smoke]" in job
    assert "if: ${{ always() && !cancelled() && github.event_name == 'pull_request' }}" in job
    assert "runs-on: ubuntu-latest" in job and "timeout-minutes: 10" in job
    permissions = job.split("    permissions:\n", 1)[1].split("    steps:\n", 1)[0]
    assert sorted(line.strip() for line in permissions.splitlines()) == [
        "actions: read",
        "checks: read",
        "contents: read",
        "pull-requests: read",
        "statuses: read",
    ]
    assert "continue-on-error" not in job
    assert "secrets." not in job and "pull_request_target" not in job
    assert "upload-artifact" not in job and "github-script" not in job


def test_advisory_tool_and_constraints_are_independent_of_the_inspected_pr() -> None:
    tool = _step("Check out the reviewed verification tool")
    assert "repository: tarekmasryo/Evagix" in tool
    assert re.search(r"^          ref: [0-9a-f]{40}$", tool, re.MULTILINE)
    assert "ref: 69701c2ee29fa4e97f630bf430c714110cbe74f0" in tool
    assert "path: verification-tool" in tool
    install = _step("Install the reviewed verification tool")
    assert "working-directory: ${{ runner.temp }}" in install
    assert "TOOL_SOURCE: ${{ github.workspace }}/verification-tool" in install
    assert 'python -I -m venv "$RUNNER_TEMP/evagix-summary-env"' in install
    assert '-c "$TOOL_SOURCE/constraints-release.txt" pip setuptools wheel' in install
    assert '--no-build-isolation --no-deps "$TOOL_SOURCE"' in install
    assert "inspected" not in install
    inspected = _step("Fetch inspected commits as data")
    assert "ref: ${{ github.event.pull_request.head.sha }}" in inspected
    assert "fetch-depth: 0" in inspected and "path: inspected" in inspected
    for checkout in (tool, inspected):
        assert "persist-credentials: false" in checkout
        assert "submodules: false" in checkout and "lfs: false" in checkout
    job = _job()
    assert job.index("Install the reviewed verification tool") < job.index("Fetch inspected commits as data")


def test_advisory_publisher_handles_setup_failures_and_passes_inputs_as_data() -> None:
    step = _step("Publish advisory review summary")
    assert "if: ${{ always() }}" in step
    assert "working-directory: ${{ runner.temp }}" in step
    assert "BASE_SHA: ${{ github.event.pull_request.base.sha }}" in step
    assert "HEAD_SHA: ${{ github.event.pull_request.head.sha }}" in step
    assert "EVAGIX_GITHUB_TOKEN: ${{ github.token }}" in step
    assert "JUNIT_STATUS: ${{ needs.quality.outputs.junit-status }}" in step
    assert "JUNIT_ATTEMPT: ${{ needs.quality.outputs.junit-attempt }}" in step
    assert "JUNIT_DOWNLOAD: ${{ steps.junit-download.outcome }}" in step
    assert "JUNIT_ARTIFACT_ID: ${{ needs.quality.outputs.junit-artifact-id }}" in step
    script = _publisher()
    assert "${{" not in script
    assert "--expectations" not in script
    assert "::" not in script


def test_junit_transfer_keeps_quality_gates_and_limits_artifact_scope() -> None:
    quality = _job("quality")
    tests = _step("Tests with coverage", "quality")
    assert "--cov=evagix --cov-branch --cov-report=term-missing --cov-fail-under=80" in tests
    assert '--junitxml="$RUNNER_TEMP/evagix-quality-raw.xml"' in tests
    assert "continue-on-error" not in quality and "set +e" not in tests
    prepare = _step("Prepare minimized JUnit transfer", "quality")
    assert "if: ${{ always() && !cancelled() && github.event_name == 'pull_request' }}" in prepare
    assert "junit-status: ${{ steps.junit-transfer.outputs.status }}" in quality
    assert "junit-attempt: ${{ steps.junit-transfer.outputs.attempt }}" in quality
    assert "junit-artifact-id: ${{ steps.junit-upload.outputs.artifact-id }}" in quality
    upload = _step("Upload minimized JUnit report", "quality")
    assert "id: junit-upload" in upload
    assert "always() && !cancelled()" in upload and "github.event_name == 'pull_request'" in upload
    assert "steps.junit-transfer.outputs.status == 'complete'" in upload
    assert "name: evagix-quality-junit-${{ github.run_attempt }}" in upload
    assert "path: ${{ runner.temp }}/evagix-quality-junit.xml\n" in upload
    assert "raw.xml" not in upload and "retention-days: 1\n" in upload
    assert "if-no-files-found: error" in upload
    download = _step("Download minimized JUnit report")
    assert "needs.quality.outputs.junit-attempt == github.run_attempt" in download
    assert "needs.quality.outputs.junit-status == 'complete'" in download
    assert "needs.quality.outputs.junit-artifact-id != ''" in download
    assert "artifact-ids: ${{ needs.quality.outputs.junit-artifact-id }}" in download
    assert "path: ${{ runner.temp }}/evagix-junit-input" in download
    assert "skip-decompress: true" in download
    assert "digest-mismatch: error" in download
    assert all(
        option not in download for option in ("          name:", "github-token:", "run-id:", "repository:", "pattern:")
    )


def _bash() -> str:
    executable = shutil.which("bash")
    if executable:
        return executable
    if os.name == "nt" and (git := shutil.which("git")):
        candidate = Path(git).resolve().parents[1] / "bin/bash.exe"
        if candidate.is_file():
            return str(candidate)
    pytest.skip("Workflow shell integration requires Bash")


@pytest.mark.parametrize(
    "status,report,available,expected_status,expected_summary",
    [
        (0, "# Advisory\npassed: 1\n", True, 0, "passed: 1"),
        (0, "# Advisory\nfailed: 1\nAGENTS.md:2:3: deleted target\n", True, 0, "failed: 1"),
        (0, "# Advisory\nXML outcome: skipped_only\n", True, 0, "skipped_only"),
        (0, "# Advisory\nNo checks observed; required-check coverage unknown\n", True, 0, "No checks observed"),
        (1, "# Advisory\nincomplete: do not infer missing checks\n", True, 1, "incomplete"),
        (2, "partial output must not be published", True, 2, "Evagix review unavailable"),
        (0, "", True, 2, "Evagix review unavailable"),
        (0, "", False, 2, "Evagix review unavailable"),
    ],
    ids=[
        "success",
        "failed-check-and-reference",
        "skipped-tests",
        "empty-inventory",
        "incomplete",
        "error",
        "empty-output",
        "setup-failed",
    ],
)
def test_workflow_publishes_only_usable_reports_and_preserves_status(
    tmp_path: Path,
    status: int,
    report: str,
    available: bool,
    expected_status: int,
    expected_summary: str,
) -> None:
    # Substitute only the CLI process; execute the checked-in workflow's shell.
    runner = tmp_path / "runner temp"
    workspace = tmp_path / "workspace with spaces"
    runner.mkdir()
    workspace.mkdir()
    archive = runner / "evagix-junit-input" / "original archive.zip"
    archive.parent.mkdir()
    archive.write_bytes(b"archive bytes are inspected by the substituted CLI")
    executable = runner / "evagix-summary-env/bin/python"
    arguments = runner / "arguments.txt"
    directory = runner / "directory.txt"
    if available:
        executable.parent.mkdir(parents=True)
        executable.write_text(
            '#!/usr/bin/env bash\nset -eu\nprintf "%s\\n" "$@" > "$STUB_ARGUMENTS"\n'
            'pwd > "$STUB_DIRECTORY"\nprintf "%s" "$STUB_REPORT"\nexit "$STUB_STATUS"\n',
            encoding="utf-8",
            newline="\n",
        )
        executable.chmod(0o755)
    summary = runner / "step summary.md"
    summary.write_text("Existing summary\n", encoding="utf-8")
    script = runner / "publish.sh"
    script.write_text(_publisher(), encoding="utf-8", newline="\n")
    env = {
        **os.environ,
        "RUNNER_TEMP": runner.as_posix(),
        "GITHUB_WORKSPACE": workspace.as_posix(),
        "GITHUB_STEP_SUMMARY": summary.as_posix(),
        "PR_URL": "https://github.com/example/project/pull/7",
        "BASE_SHA": "a" * 40,
        "HEAD_SHA": "b" * 40,
        "EVAGIX_GITHUB_TOKEN": "fixture-token-not-for-output",
        "JUNIT_STATUS": "complete",
        "JUNIT_DOWNLOAD": "success",
        "JUNIT_ATTEMPT": "2",
        "JUNIT_ARTIFACT_ID": "300",
        "GITHUB_RUN_ID": "100",
        "GITHUB_RUN_ATTEMPT": "2",
        "STUB_ARGUMENTS": arguments.as_posix(),
        "STUB_DIRECTORY": directory.as_posix(),
        "STUB_REPORT": report,
        "STUB_STATUS": str(status),
    }
    result = subprocess.run(
        [_bash(), "--noprofile", "--norc", "-e", "-o", "pipefail", script.as_posix()],
        cwd=runner,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )
    assert result.returncode == expected_status
    output = summary.read_text(encoding="utf-8")
    assert output.startswith("Existing summary\n") and expected_summary in output
    assert result.stdout == ""
    assert "fixture-token-not-for-output" not in output + result.stdout + result.stderr
    assert "partial output must not be published" not in output
    if expected_status == 2:
        assert "no clean result is implied" in output
    else:
        assert output.startswith("Existing summary\n" + report)
        assert "JUnit transfer scope: Quality gates only" in output
        assert "producing attempt and tested revision remain unproven" in output
    if available:
        assert arguments.read_text(encoding="utf-8").splitlines() == [
            "-I",
            "-m",
            "evagix.pr_summary",
            env["PR_URL"],
            "--repo",
            f"{workspace.as_posix()}/inspected",
            "--base",
            env["BASE_SHA"],
            "--head",
            env["HEAD_SHA"],
            "--junit-archive",
            archive.as_posix(),
            "--junit-run-id",
            "100",
            "--junit-attempt",
            "2",
            "--junit-artifact-id",
            "300",
        ]
        assert directory.read_text(encoding="utf-8").strip().endswith("/runner temp")


@pytest.mark.parametrize(
    "state,download,attempt,cli_status,expected",
    [
        ("incomplete", "skipped", "2", 0, 1),
        ("error", "skipped", "2", 0, 1),
        ("", "skipped", "", 0, 1),
        ("complete", "failure", "2", 0, 1),
        ("complete", "success", "1", 0, 1),
        ("complete", "success", "2", 1, 1),
        ("complete", "success", "2", 2, 2),
        ("error", "failure", "2", 2, 2),
    ],
    ids=[
        "incomplete",
        "malformed-source",
        "producer-not-run",
        "missing-artifact",
        "old-attempt",
        "incomplete-consumer",
        "malformed-artifact",
        "both-unavailable",
    ],
)
def test_junit_unavailability_is_explicit_and_never_reuses_an_old_attempt(
    tmp_path: Path,
    state: str,
    download: str,
    attempt: str,
    cli_status: int,
    expected: int,
) -> None:
    executable = tmp_path / "evagix-summary-env/bin/python"
    executable.parent.mkdir(parents=True)
    executable.write_text(
        '#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$STUB_ARGUMENTS"\n'
        'printf "%s" "$STUB_REPORT"\nexit "$STUB_STATUS"\n',
        encoding="utf-8",
        newline="\n",
    )
    executable.chmod(0o755)
    archive = tmp_path / "evagix-junit-input" / ".original.zip"
    archive.parent.mkdir()
    archive.write_bytes(b"archive fixture")
    arguments = tmp_path / "arguments.txt"
    summary = tmp_path / "summary.md"
    script = tmp_path / "publish.sh"
    script.write_text(_publisher(), encoding="utf-8", newline="\n")
    report = "# Existing advisory findings\nAGENTS.md:2: deleted script\n"
    env = {
        **os.environ,
        "RUNNER_TEMP": tmp_path.as_posix(),
        "GITHUB_WORKSPACE": tmp_path.as_posix(),
        "GITHUB_STEP_SUMMARY": summary.as_posix(),
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_RUN_ID": "100",
        "PR_URL": "https://github.com/example/project/pull/7",
        "BASE_SHA": "a" * 40,
        "HEAD_SHA": "b" * 40,
        "JUNIT_STATUS": state,
        "JUNIT_DOWNLOAD": download,
        "JUNIT_ATTEMPT": attempt,
        "JUNIT_ARTIFACT_ID": "300",
        "STUB_ARGUMENTS": arguments.as_posix(),
        "STUB_REPORT": report,
        "STUB_STATUS": str(cli_status),
    }
    result = subprocess.run(
        [_bash(), "--noprofile", "--norc", "-e", "-o", "pipefail", script.as_posix()],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )
    assert result.returncode == expected and not result.stdout
    output = summary.read_text(encoding="utf-8")
    attached = state == "complete" and download == "success" and attempt == "2"
    assert ("--junit-archive" in arguments.read_text(encoding="utf-8")) == attached
    if cli_status == 2:
        assert "Evagix review unavailable" in output and report not in output
    elif attached:
        assert report in output and "JUnit transfer scope" in output
    else:
        assert report in output and "Quality gates JUnit unavailable" in output
        assert "Test success and complete execution cannot be inferred" in output
        assert ("source report was incomplete" in output) == (state == "incomplete")


def _run_archive_selection(
    tmp_path: Path, *, layout: str = "regular", overrides: dict[str, str] | None = None
) -> tuple[subprocess.CompletedProcess[str], str, list[str], Path]:
    # Exercise the actual workflow shell, substituting only the report-producing CLI.
    executable = tmp_path / "evagix-summary-env/bin/python"
    executable.parent.mkdir(parents=True)
    executable.write_text(
        '#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$STUB_ARGUMENTS"\n'
        'printf "%s" "$STUB_REPORT"\nexit "$STUB_STATUS"\n',
        encoding="utf-8",
        newline="\n",
    )
    executable.chmod(0o755)
    inputs = tmp_path / "evagix-junit-input"
    archive = inputs / "provider-selected filename.bin"
    if layout != "missing-directory":
        inputs.mkdir()
    if layout in {"regular", "two-files", "extra-hidden-file", "file-and-directory"}:
        archive.write_bytes(b"archive fixture")
    if layout == "hidden-only":
        archive = inputs / ".hidden-original.zip"
        archive.write_bytes(b"archive fixture")
    elif layout == "two-files":
        (inputs / "another.zip").write_bytes(b"extra artifact")
    elif layout == "extra-hidden-file":
        (inputs / ".extra.zip").write_bytes(b"extra hidden artifact")
    elif layout in {"directory-only", "file-and-directory"}:
        (inputs / "nested").mkdir()
    elif layout == "symlink":
        target = tmp_path / "outside-input.zip"
        target.write_bytes(b"outside artifact")
        try:
            archive.symlink_to(target)
        except OSError:
            pytest.skip("Creating symlinks requires platform support or permission")
    arguments = tmp_path / "arguments.txt"
    summary = tmp_path / "summary.md"
    script = tmp_path / "publish.sh"
    script.write_text(_publisher(), encoding="utf-8", newline="\n")
    env = {
        **os.environ,
        "RUNNER_TEMP": tmp_path.as_posix(),
        "GITHUB_WORKSPACE": tmp_path.as_posix(),
        "GITHUB_STEP_SUMMARY": summary.as_posix(),
        "GITHUB_RUN_ID": "100",
        "GITHUB_RUN_ATTEMPT": "2",
        "PR_URL": "https://github.com/example/project/pull/7",
        "BASE_SHA": "a" * 40,
        "HEAD_SHA": "b" * 40,
        "JUNIT_STATUS": "complete",
        "JUNIT_DOWNLOAD": "success",
        "JUNIT_ATTEMPT": "2",
        "JUNIT_ARTIFACT_ID": "300",
        "EVAGIX_GITHUB_TOKEN": "fixture-token-not-for-output",
        "STUB_ARGUMENTS": arguments.as_posix(),
        "STUB_REPORT": "# Existing advisory findings\nAGENTS.md:2: deleted script\n",
        "STUB_STATUS": "0",
        **(overrides or {}),
    }
    result = subprocess.run(
        [_bash(), "--noprofile", "--norc", "-e", "-o", "pipefail", script.as_posix()],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )
    output = summary.read_text(encoding="utf-8")
    assert "fixture-token-not-for-output" not in output + result.stdout + result.stderr
    assert not result.stdout
    assert "AGENTS.md:2: deleted script" in output
    return result, output, arguments.read_text(encoding="utf-8").splitlines(), archive


@pytest.mark.parametrize(
    "change,code",
    [
        ("healthy", None),
        ("deleted", "tests.deleted-file"),
        ("renamed", None),
        ("conditional", None),
        ("unconditional", "tests.unconditional-skip-added"),
        ("incomplete", None),
    ],
)
def test_publisher_preserves_generated_test_change_evidence_and_collection_status(
    tmp_path: Path, change: str, code: str | None
) -> None:
    workspace = tmp_path / "workspace with spaces"
    repository = workspace / "inspected"
    repository.mkdir(parents=True)

    def git(*args: str) -> str:
        return subprocess.run(
            [
                "git",
                "-c",
                "user.name=Fixture User",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "core.autocrlf=false",
                *args,
            ],
            cwd=repository,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout.strip()

    source = "import pytest\n\ndef test_existing():\n    assert True\n\nraise RuntimeError('SOURCE_MUST_NOT_EXECUTE')\n"
    test_file = repository / "test_example.py"
    test_file.write_text(source, encoding="utf-8")
    (repository / "README.md").write_text("# Fixture repository\n", encoding="utf-8")
    git("init", "-q", "-b", "main")
    git("add", ".")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    if change == "deleted":
        test_file.unlink()
    elif change == "renamed":
        test_file.rename(repository / "test_renamed.py")
    else:
        updated = {
            "healthy": source.replace("assert True", "assert 1"),
            "conditional": source.replace(
                "def test_existing", "@pytest.mark.skipif(True, reason='SOURCE_ONLY_SKIP_REASON')\ndef test_existing"
            ),
            "unconditional": source.replace(
                "def test_existing", "@pytest.mark.skip(reason='SOURCE_ONLY_SKIP_REASON')\ndef test_existing"
            ),
            "incomplete": "def test_existing(:\n",
        }[change]
        test_file.write_text(updated, encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "change tests")
    head = git("rev-parse", "HEAD")
    evidence = build_test_changes_report(repository, base=base, head=head)
    assert [finding.code for finding in evidence.findings] == ([] if code is None else [code])
    assert bool(evidence.renames) is (change == "renamed")
    assert evidence.complete is (change != "incomplete")
    status = 0 if evidence.complete else 1
    report = "# Existing advisory findings\nAGENTS.md:2: deleted script\n\n" + render_test_changes_markdown(evidence)
    runner = tmp_path / "runner temp"
    runner.mkdir()
    result, output, arguments, _ = _run_archive_selection(
        runner,
        overrides={
            "STUB_REPORT": report,
            "STUB_STATUS": str(status),
            "BASE_SHA": base,
            "HEAD_SHA": head,
            "GITHUB_WORKSPACE": workspace.as_posix(),
        },
    )
    assert result.returncode == status
    assert output.startswith(report)
    assert "## Test change review" in output
    assert "Advisory only: collection, execution, test quality and merge readiness are not verified" in output
    assert "JUnit transfer scope: Quality gates only" in output
    assert "producing attempt and tested revision remain unproven" in output
    assert arguments[arguments.index("--base") + 1] == base
    assert arguments[arguments.index("--head") + 1] == head
    assert arguments[arguments.index("--repo") + 1] == repository.as_posix()
    assert "--junit-archive" in arguments
    assert "SOURCE_MUST_NOT_EXECUTE" not in output + result.stderr
    assert "SOURCE_ONLY_SKIP_REASON" not in output + result.stderr


@pytest.mark.parametrize(
    "layout,accepted",
    [
        ("regular", True),
        ("hidden-only", True),
        ("missing-directory", False),
        ("empty-directory", False),
        ("two-files", False),
        ("extra-hidden-file", False),
        ("directory-only", False),
        ("file-and-directory", False),
        ("symlink", False),
    ],
)
def test_archive_selection_requires_exactly_one_regular_file_including_hidden_entries(
    tmp_path: Path, layout: str, accepted: bool
) -> None:
    result, output, arguments, archive = _run_archive_selection(tmp_path, layout=layout)
    assert result.returncode == (0 if accepted else 1)
    assert ("--junit-archive" in arguments) == accepted
    if accepted:
        assert arguments[arguments.index("--junit-archive") + 1] == archive.as_posix()
        assert "original archive is compared with GitHub artifact and run metadata" in output
    else:
        assert "Quality gates JUnit unavailable" in output
        assert "Test success and complete execution cannot be inferred" in output


@pytest.mark.parametrize(
    "overrides",
    [
        {"JUNIT_ARTIFACT_ID": ""},
        {"JUNIT_ARTIFACT_ID": "0"},
        {"JUNIT_ARTIFACT_ID": "300,301"},
        {"JUNIT_ARTIFACT_ID": "$(touch invalid-id-executed)"},
        {"GITHUB_RUN_ID": ""},
        {"GITHUB_RUN_ID": "0"},
        {"GITHUB_RUN_ID": "100 101"},
        {"GITHUB_RUN_ID": "1; touch invalid-id-executed"},
        {"JUNIT_ATTEMPT": "0", "GITHUB_RUN_ATTEMPT": "0"},
        {"JUNIT_ATTEMPT": "invalid", "GITHUB_RUN_ATTEMPT": "invalid"},
        {"JUNIT_ATTEMPT": "", "GITHUB_RUN_ATTEMPT": ""},
    ],
    ids=[
        "missing-artifact-id",
        "zero-artifact-id",
        "multiple-artifact-ids",
        "shell-artifact-id",
        "missing-run-id",
        "zero-run-id",
        "multiple-run-ids",
        "shell-run-id",
        "zero-attempt",
        "nonnumeric-attempt",
        "missing-attempt",
    ],
)
def test_invalid_association_ids_do_not_attach_an_archive_or_execute_data(
    tmp_path: Path, overrides: dict[str, str]
) -> None:
    result, output, arguments, _ = _run_archive_selection(tmp_path, overrides=overrides)
    assert result.returncode == 1
    assert "--junit-archive" not in arguments
    assert "Quality gates JUnit unavailable" in output
    assert not (tmp_path / "invalid-id-executed").exists()


@pytest.mark.parametrize("status,state", [(0, "complete"), (1, "incomplete"), (2, "error"), (127, "error")])
def test_producer_reports_collection_state_without_replacing_pytest_status(
    tmp_path: Path,
    status: int,
    state: str,
) -> None:
    executable = tmp_path / "python"
    executable.write_text('#!/usr/bin/env bash\nexit "$STUB_STATUS"\n', encoding="utf-8", newline="\n")
    executable.chmod(0o755)
    output = tmp_path / "job-output.txt"
    script = tmp_path / "prepare.sh"
    command = _step("Prepare minimized JUnit transfer", "quality").split("        run: |\n", 1)[1]
    script.write_text(textwrap.dedent(command), encoding="utf-8", newline="\n")
    env = {
        **os.environ,
        "RUNNER_TEMP": tmp_path.as_posix(),
        "GITHUB_OUTPUT": output.as_posix(),
        "GITHUB_RUN_ATTEMPT": "2",
        "STUB_STATUS": str(status),
    }
    # Put the stub on PATH inside Bash so Windows drive separators cannot alter it.
    invocation = 'export PATH="$PWD:$PATH"; exec bash -e -o pipefail "$RUNNER_TEMP/prepare.sh"'
    result = subprocess.run(
        [_bash(), "--noprofile", "--norc", "-c", invocation],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0
    assert output.read_text(encoding="utf-8") == f"status={state}\nattempt=2\n"
