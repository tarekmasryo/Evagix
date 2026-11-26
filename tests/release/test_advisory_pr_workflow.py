from __future__ import annotations

import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _job() -> str:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    return workflow.split("\n  advisory-pr-review:\n", 1)[1]


def _step(name: str) -> str:
    tail = _job().split(f"      - name: {name}\n", 1)[1]
    return re.split(r"\n      - ", tail, maxsplit=1)[0]


def _publisher() -> str:
    return textwrap.dedent(_step("Publish advisory review summary").split("        run: |\n", 1)[1])


def test_advisory_job_waits_for_existing_gates_without_weakening_them() -> None:
    job = _job()
    assert "needs: [quality, test, self-governance, build, artifact-smoke]" in job
    assert "if: ${{ always() && !cancelled() && github.event_name == 'pull_request' }}" in job
    assert "runs-on: ubuntu-latest" in job and "timeout-minutes: 10" in job
    permissions = job.split("    permissions:\n", 1)[1].split("    steps:\n", 1)[0]
    assert permissions == "      contents: read\n      pull-requests: read\n      checks: read\n      statuses: read\n"
    assert "continue-on-error" not in job
    assert "secrets." not in job and "pull_request_target" not in job
    assert "upload-artifact" not in job and "github-script" not in job


def test_advisory_tool_and_constraints_are_independent_of_the_inspected_pr() -> None:
    tool = _step("Check out the reviewed verification tool")
    assert "repository: tarekmasryo/Evagix" in tool
    assert re.search(r"^          ref: [0-9a-f]{40}$", tool, re.MULTILINE)
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
    script = _publisher()
    assert "${{" not in script
    assert "--expectations" not in script
    assert "::" not in script


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
        (0, "# Advisory\nNo checks observed; required-check coverage unknown\n", True, 0, "No checks observed"),
        (1, "# Advisory\nincomplete: do not infer missing checks\n", True, 1, "incomplete"),
        (2, "partial output must not be published", True, 2, "Evagix review unavailable"),
        (0, "", True, 2, "Evagix review unavailable"),
        (0, "", False, 2, "Evagix review unavailable"),
    ],
    ids=[
        "success",
        "failed-check-and-reference",
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
        assert output == "Existing summary\n" + report
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
        ]
        assert directory.read_text(encoding="utf-8").strip().endswith("/runner temp")
