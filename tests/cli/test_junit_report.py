from __future__ import annotations

import json
import socket
import subprocess
from importlib.resources import files
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from evagix.cli import main


@pytest.fixture(autouse=True)
def no_execution_or_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected(*args: object, **kwargs: object) -> None:
        pytest.fail("Local JUnit reporting must not run commands or make network requests")

    monkeypatch.setattr(subprocess, "Popen", unexpected)
    monkeypatch.setattr(socket, "socket", unexpected)


@pytest.mark.parametrize("output_format", ["text", "json"])
@pytest.mark.parametrize(
    "body,attrs,status,outcome,exit_code",
    [
        ('<testcase name="ok"/>', 'tests="1" failures="0" errors="0" skipped="0"', "complete", "passed", 0),
        (
            '<testcase name="bad"><failure/></testcase>',
            'tests="1" failures="1" errors="0" skipped="0"',
            "complete",
            "failed",
            0,
        ),
        (
            '<testcase name="err"><error/></testcase>',
            'tests="1" failures="0" errors="1" skipped="0"',
            "complete",
            "failed",
            0,
        ),
        (
            '<testcase name="skip"><skipped/></testcase>',
            'tests="1" failures="0" errors="0" skipped="1"',
            "complete",
            "skipped_only",
            0,
        ),
        ("", 'tests="0" failures="0" errors="0" skipped="0"', "complete", "empty", 0),
        ('<testcase name="ok"/>', 'tests="2" failures="0" errors="0" skipped="0"', "incomplete", "unknown", 1),
        ('<testcase name="ok"/>', "", "incomplete", "unknown", 1),
        ('<testcase name="ok"/>', 'tests="1"', "incomplete", "unknown", 1),
        ("<testcase", "", "error", "unknown", 2),
    ],
)
def test_cli_collection_contract(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    output_format: str,
    body: str,
    attrs: str,
    status: str,
    outcome: str,
    exit_code: int,
) -> None:
    path = tmp_path / "local report.xml"
    path.write_text(f'<testsuite name="pytest" {attrs}>{body}</testsuite>', encoding="utf-8")
    assert main(["junit-report", str(path), "--format", output_format]) == exit_code
    output = capsys.readouterr()
    assert output.err == ""
    if output_format == "json":
        payload = json.loads(output.out)
        schema = json.loads(files("evagix.schemas").joinpath("junit-report.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
        assert payload["collection_status"] == status
        assert payload["reported_outcome"] == outcome
        assert payload["source_verification"] == "unverified"
        assert payload["revision_binding"] == payload["run_completion"] == "unknown"
        assert payload["policy_decision"] == "not_evaluated"
    else:
        assert f"Report collection: {status}; reported outcome: {outcome}" in output.out
        assert "Exit status describes collection, not test success" in output.out
        assert "Source verification: unverified" in output.out
        assert "run completion: unknown" in output.out


def test_cli_missing_report_is_structured_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["junit-report", str(tmp_path / "missing.xml"), "--format", "json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["issues"] == ["read_error"]
    assert payload["collection_status"] == "error"
    assert payload["counts"]["cases"] == 0


def test_cli_passed_rows_are_optional_but_json_is_complete(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "report.xml"
    path.write_text(
        '<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="test_hidden"/></testsuite>',
        encoding="utf-8",
    )
    assert main(["junit-report", str(path)]) == 0
    output = capsys.readouterr().out
    assert "test_hidden" not in output
    assert "Passed rows hidden: 1" in output
    assert main(["junit-report", str(path), "--all"]) == 0
    assert "test_hidden" in capsys.readouterr().out
    assert main(["junit-report", str(path), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["suites"][0]["cases"][0]["name"] == "test_hidden"


@pytest.mark.parametrize("output_format", ["text", "json"])
def test_cli_redacts_and_contains_untrusted_names(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], output_format: str
) -> None:
    path = tmp_path / "report.xml"
    path.write_text(
        '<testsuite tests="1" failures="1" errors="0" skipped="0">'
        '<properties><property name="commit" value="made-up-provenance"/></properties>'
        '<testcase name="اختبار&#x202e; token=example-secret" classname="test&#10;forged">'
        '<failure message="omit-this-message">omit-this-traceback</failure>'
        "<system-out>omit-this-stdout</system-out></testcase></testsuite>",
        encoding="utf-8",
    )
    assert main(["junit-report", str(path), "--format", output_format]) == 0
    output = capsys.readouterr().out
    assert "example-secret" not in output
    assert "omit-this" not in output
    assert "made-up-provenance" not in output
    assert "\u202e" not in output
    assert "test\nforged" not in output
    assert "[REDACTED]" in output
    if output_format == "json":
        assert "اختبار" in json.loads(output)["suites"][0]["cases"][0]["name"]
    else:
        assert "اختبار" in output


def test_cli_usage_errors_keep_argparse_contract(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit, match="2"):
        main(["junit-report"])
    assert "PATH" in capsys.readouterr().err
    with pytest.raises(SystemExit, match="2"):
        main(["junit-report", "report.xml", "--format", "xml"])
    assert "invalid choice" in capsys.readouterr().err


def test_cli_identifies_shortened_labels_without_losing_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "report.xml"
    long_name = "p" * 4096
    path.write_text(
        f'<testsuite name="{long_name}" tests="1" failures="0" errors="0" skipped="0">'
        f'<testcase name="{long_name}"/></testsuite>',
        encoding="utf-8",
    )
    assert main(["junit-report", str(path), "--all"]) == 0
    output = capsys.readouterr().out
    assert output.count("identity shortened") == 2
    assert "cases=1, passed=1" in output
    assert long_name not in output


def test_cli_json_survives_final_redaction_of_mysql_parameter_ids(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "report.xml"
    path.write_text(
        '<testsuite tests="1" failures="0" errors="0" skipped="0">'
        '<testcase name="test_command[mysql -u root -psynthetic-secret]"/></testsuite>',
        encoding="utf-8",
    )
    assert main(["junit-report", str(path), "--format", "json"]) == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert "synthetic-secret" not in output
    assert payload["counts"]["passed"] == 1
    assert payload["suites"][0]["cases"][0]["name"].endswith("-p[REDACTED]")
