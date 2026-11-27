from __future__ import annotations

import hashlib
import json
import socket
import zipfile
from copy import deepcopy
from importlib.resources import files
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from evagix.cli import main
from evagix.verification import github_junit

REVISION = "a" * 40
RUN_URL = "https://github.com/example/project/actions/runs/20"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.delenv("EVAGIX_GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("Unexpected network"))


@pytest.fixture
def archive(tmp_path):
    path = tmp_path / "original artifact.zip"
    with zipfile.ZipFile(path, "w") as output:
        output.writestr(
            "evagix-quality-junit.xml",
            '<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="test_success"/></testsuite>',
        )
    return path


def _args(path: Path, output_format="json"):
    return [
        "junit-github",
        str(path),
        "--run",
        RUN_URL,
        "--attempt",
        "2",
        "--artifact-id",
        "30",
        "--revision",
        REVISION,
        "--format",
        output_format,
    ]


def _source(monkeypatch, archive, *, current=2, digest=None, conclusion="success"):
    run = {
        "id": 20,
        "repository": {"id": 10},
        "head_repository": {"id": 10},
        "workflow_id": 40,
        "head_sha": REVISION,
        "run_attempt": current,
        "event": "pull_request",
        "status": "completed",
        "conclusion": conclusion,
    }
    attempt = {**run, "run_attempt": 2}
    artifact = {
        "id": 30,
        "size_in_bytes": archive.stat().st_size,
        "expired": False,
        "digest": digest or "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest(),
        "workflow_run": {"id": 20, "repository_id": 10, "head_repository_id": 10, "head_sha": REVISION},
    }
    responses = [
        {"id": 10, "full_name": "example/project"},
        run,
        attempt,
        artifact,
        artifact,
        attempt,
        run,
    ]
    calls = []

    class Client:
        def __init__(self, token):
            calls.append(token)

        def get(self, path):
            calls.append(path)
            return deepcopy(responses.pop(0)), ""

    monkeypatch.setattr(github_junit, "_Client", Client)
    return calls


def _validate(payload):
    schemas = files("evagix.schemas")
    schema = json.loads(schemas.joinpath("github-junit.schema.json").read_text(encoding="utf-8"))
    junit = json.loads(schemas.joinpath("junit-report.schema.json").read_text(encoding="utf-8"))
    registry = Registry().with_resource(junit["$id"], Resource.from_contents(junit))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, registry=registry).validate(payload)


@pytest.mark.parametrize("output_format", ["text", "json"])
@pytest.mark.parametrize("current,exit_code", [(2, 0), (3, 1)])
def test_optional_command_reports_currentness_without_claiming_artifact_attempt(
    archive,
    monkeypatch,
    capsys,
    output_format,
    current,
    exit_code,
):
    calls = _source(monkeypatch, archive, current=current)
    assert main(_args(archive, output_format)) == exit_code
    captured = capsys.readouterr()
    assert captured.err == "" and len(calls) == 8
    if output_format == "json":
        payload = json.loads(captured.out)
        _validate(payload)
        assert payload["archive_binding"] == "matched"
        assert payload["artifact_run_match"] == payload["revision_match"] == "match"
        assert payload["selected_attempt_status"] == ("current" if current == 2 else "stale")
        assert payload["artifact_attempt_binding"] == payload["tested_revision_binding"] == "unknown"
        assert payload["execution_verification"] == "unverified"
        assert payload["junit"]["source_verification"] == "unverified"
        assert payload["policy_decision"] == "not_evaluated"
    else:
        assert "Artifact-producing attempt: unknown" in captured.out
        assert "latest attempt: " + str(current) in captured.out
        assert "reported outcome: passed" in captured.out
        assert RUN_URL in captured.out


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "skipped", "neutral"])
def test_run_conclusion_is_not_overwritten_by_passing_xml(archive, monkeypatch, capsys, conclusion):
    _source(monkeypatch, archive, conclusion=conclusion)
    assert main(_args(archive)) == 0
    payload = json.loads(capsys.readouterr().out)
    _validate(payload)
    assert payload["run"]["conclusion"] == conclusion
    assert payload["junit"]["reported_outcome"] == "passed"


def test_digest_mismatch_does_not_publish_xml_as_run_results(archive, monkeypatch, capsys):
    _source(monkeypatch, archive, digest="sha256:" + "0" * 64)
    assert main(_args(archive)) == 1
    payload = json.loads(capsys.readouterr().out)
    _validate(payload)
    assert payload["archive_binding"] == "mismatched"
    assert payload["junit"] is None


@pytest.mark.parametrize(
    "flag,value",
    [
        ("--run", "https://outside.invalid/example/project/actions/runs/20"),
        ("--run", RUN_URL + "?token=private-example"),
        ("--run", RUN_URL.replace("/project/", "/../")),
        ("--attempt", "0"),
        ("--attempt", "9" * 200),
        ("--artifact-id", "-3"),
        ("--revision", "main"),
        ("--revision", "b" * 39),
        ("--member", "../results.xml"),
        ("--member", "/results.xml"),
        ("--member", "folder\\results.xml"),
    ],
)
def test_invalid_arguments_fail_before_input_or_network(archive, monkeypatch, capsys, flag, value):
    monkeypatch.setattr(github_junit, "_read_archive", lambda *a: pytest.fail("Unexpected read"))
    args = _args(archive)
    if flag in args:
        args[args.index(flag) + 1] = value
    else:
        args.extend((flag, value))
    assert main(args) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "Invalid JUnit association arguments" in captured.err
    assert "private-example" not in captured.err


def test_missing_archive_is_a_structured_error_without_network(tmp_path, capsys):
    assert main(_args(tmp_path / "missing.zip")) == 2
    payload = json.loads(capsys.readouterr().out)
    _validate(payload)
    assert payload["issues"] == ["archive_read_error"]
    assert payload["metadata_source"] is None and payload["junit"] is None


def test_provider_failure_is_classified_without_echoing_token(archive, monkeypatch, capsys):
    from evagix.verification.github_collection import GitHubCollectionError

    def unavailable(request, token):
        assert token == "synthetic-private-token"
        raise GitHubCollectionError("forbidden")

    monkeypatch.setenv("EVAGIX_GITHUB_TOKEN", "synthetic-private-token")
    monkeypatch.setattr(github_junit, "_collect", unavailable)
    assert main(_args(archive)) == 2
    output = capsys.readouterr().out
    payload = json.loads(output)
    _validate(payload)
    assert payload["issues"] == ["forbidden"]
    assert "synthetic-private-token" not in output


def test_existing_offline_command_never_collects_association(tmp_path, monkeypatch, capsys):
    path = tmp_path / "results.xml"
    path.write_text('<testsuite tests="0" failures="0" errors="0" skipped="0"/>', encoding="utf-8")
    monkeypatch.setattr(github_junit, "inspect_github_junit", lambda *a, **k: pytest.fail("Unexpected association"))
    assert main(["junit-report", str(path), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "local_pytest_junit"
    assert "archive_binding" not in payload and payload["source_verification"] == "unverified"
