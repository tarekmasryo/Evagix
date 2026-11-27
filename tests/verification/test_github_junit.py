from __future__ import annotations

import hashlib
import io
import json
import stat
import struct
import warnings
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from evagix.verification import github_junit
from evagix.verification.github_collection import GitHubCollectionError

REPOSITORY = "example/project"
REVISION = "a" * 40
MEMBER = "evagix-quality-junit.xml"
ROOT = f"/repos/{REPOSITORY}"


def _request(**changes: Any) -> github_junit.JUnitArtifactRequest:
    values = dict(repository=REPOSITORY, run_id=30, attempt=2, artifact_id=40, revision=REVISION)
    values.update(changes)
    return github_junit.JUnitArtifactRequest(**values)


def _xml(marker: str = "", *, tests: int = 1, **counts: int) -> bytes:
    counters = dict(tests=tests, errors=0, failures=0, skipped=0)
    counters.update(counts)
    attrs = " ".join(f'{key}="{value}"' for key, value in counters.items())
    case = f'<testcase name="test_case">{marker}</testcase>' if tests else ""
    return f'<testsuite name="pytest" {attrs}>{case}</testsuite>'.encode()


def _zip(contents: bytes | None = None, *, member: str | zipfile.ZipInfo = MEMBER, compression: int = 8) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=compression) as archive:
        archive.writestr(member, contents if contents is not None else _xml())
    return stream.getvalue()


def _run(*, attempt: int = 2, **changes: Any) -> dict[str, Any]:
    result = {
        "id": 30,
        "repository": {"id": 10},
        "head_repository": {"id": 10},
        "workflow_id": 20,
        "head_sha": REVISION,
        "run_attempt": attempt,
        "event": "pull_request",
        "status": "completed",
        "conclusion": "success",
    }
    result.update(changes)
    return result


def _artifact(contents: bytes, **changes: Any) -> dict[str, Any]:
    result = {
        "id": 40,
        "name": "evagix-quality-junit-2",
        "size_in_bytes": len(contents),
        "expired": False,
        "digest": "sha256:" + hashlib.sha256(contents).hexdigest(),
        "workflow_run": {"id": 30, "repository_id": 10, "head_repository_id": 10, "head_sha": REVISION},
    }
    result.update(changes)
    return result


def _responses(
    contents: bytes,
    *,
    run: dict[str, Any] | None = None,
    attempt: dict[str, Any] | None = None,
    artifact: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    run = run if run is not None else _run()
    attempt = attempt if attempt is not None else deepcopy(run)
    artifact = artifact if artifact is not None else _artifact(contents)
    return [
        {"id": 10, "full_name": REPOSITORY},
        deepcopy(run),
        deepcopy(attempt),
        deepcopy(artifact),
        deepcopy(artifact),
        deepcopy(attempt),
        deepcopy(run),
    ]


def _install(monkeypatch: pytest.MonkeyPatch, responses: list[Any], *, on_get: Any = None) -> list[str]:
    calls: list[str] = []
    pending = list(responses)

    class Client:
        def __init__(self, token: str | None) -> None:
            self.token = token

        def get(self, path: str) -> tuple[dict[str, Any], str]:
            calls.append(path)
            if on_get is not None:
                on_get(path)
            assert pending, "Unexpected additional provider request"
            response = pending.pop(0)
            if isinstance(response, Exception):
                raise response
            return deepcopy(response), ""

    monkeypatch.setattr(github_junit, "_Client", Client)
    return calls


@pytest.fixture(autouse=True)
def _no_live_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github_junit, "_Client", lambda *a, **k: pytest.fail("Unexpected network client"))


def _inspect(tmp_path: Path, contents: bytes, **kwargs: Any) -> github_junit.GitHubJUnitReport:
    path = tmp_path / "results.zip"
    path.write_bytes(contents)
    return github_junit.inspect_github_junit(path, request=kwargs.pop("request", _request()), **kwargs)


@pytest.mark.parametrize(
    "xml,outcome,case_counts",
    [
        (_xml(), "passed", {"passed": 1}),
        (_xml("<failure/>", failures=1), "failed", {"failed": 1}),
        (_xml("<error/><error/>", errors=2), "failed", {"error": 1}),
        (_xml("<skipped/>", skipped=1), "skipped_only", {"skipped": 1}),
        (_xml(tests=0), "empty", {}),
    ],
)
@pytest.mark.parametrize("event", ["push", "pull_request"])
def test_provider_association_preserves_xml_outcomes_without_authenticating_tests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, xml: bytes, outcome: str, case_counts: dict, event: str
) -> None:
    contents = _zip(xml)
    calls = _install(monkeypatch, _responses(contents, run=_run(event=event)))
    report = _inspect(tmp_path, contents)
    payload = report.to_dict()
    assert report.exit_code == 0
    assert payload["collection_status"] == "complete"
    assert payload["archive_binding"] == "matched"
    assert payload["artifact_run_match"] == payload["revision_match"] == "match"
    assert payload["selected_attempt_status"] == "current"
    assert payload["artifact_attempt_binding"] == payload["tested_revision_binding"] == "unknown"
    assert payload["execution_verification"] == "unverified"
    assert payload["policy_decision"] == "not_evaluated"
    assert payload["junit"]["reported_outcome"] == outcome
    assert payload["junit"]["counts"] == {
        "cases": sum(case_counts.values()),
        **dict.fromkeys(("passed", "failed", "error", "skipped"), 0),
        **case_counts,
    }
    assert payload["junit"]["source_verification"] == "unverified"
    assert payload["junit"]["revision_binding"] == payload["junit"]["run_completion"] == "unknown"
    assert calls == [
        ROOT,
        ROOT + "/actions/runs/30",
        ROOT + "/actions/runs/30/attempts/2",
        ROOT + "/actions/artifacts/40",
        ROOT + "/actions/artifacts/40",
        ROOT + "/actions/runs/30/attempts/2",
        ROOT + "/actions/runs/30",
    ]


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "skipped", "neutral", "timed_out"])
def test_xml_passes_do_not_replace_provider_failure_or_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, conclusion: str
) -> None:
    contents = _zip()
    _install(monkeypatch, _responses(contents, run=_run(conclusion=conclusion)))
    report = _inspect(tmp_path, contents)
    assert report.to_dict()["run"]["conclusion"] == conclusion
    assert report.to_dict()["attempt"]["conclusion"] == conclusion
    assert report.to_dict()["junit"]["reported_outcome"] == "passed"
    assert report.exit_code == 0  # Collection, never a test or merge gate.


def test_old_selected_attempt_stays_stale_even_with_matching_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contents = _zip()
    _install(monkeypatch, _responses(contents, run=_run(attempt=3), attempt=_run(attempt=2)))
    report = _inspect(tmp_path, contents)
    assert report.exit_code == 1
    assert report.to_dict()["selected_attempt_status"] == "stale"
    assert report.to_dict()["artifact_attempt_binding"] == "unknown"
    assert report.to_dict()["junit"]["reported_outcome"] == "passed"


def test_artifact_names_and_embedded_claims_cannot_prove_an_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contents = _zip(
        _xml().replace(b"<testcase", b'<properties><property name="attempt" value="2"/></properties><testcase')
    )
    artifact = _artifact(contents, name="trusted-attempt-2", run_attempt=2, created_at="2099-01-01T00:00:00Z")
    _install(monkeypatch, _responses(contents, artifact=artifact))
    payload = _inspect(tmp_path, contents).to_dict()
    assert payload["selected_attempt_status"] == "current"
    assert payload["artifact_attempt_binding"] == "unknown"
    assert payload["execution_verification"] == "unverified"


@pytest.mark.parametrize(
    "field,value", [("id", 31), ("repository_id", 11), ("head_repository_id", 12), ("head_sha", "b" * 40)]
)
def test_archive_for_another_run_or_repository_never_attributes_test_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: Any
) -> None:
    contents = _zip()
    artifact = _artifact(contents)
    artifact["workflow_run"][field] = value
    _install(monkeypatch, _responses(contents, artifact=artifact))
    report = _inspect(tmp_path, contents)
    assert report.exit_code == 1
    assert report.to_dict()["archive_binding"] == "matched"
    assert report.to_dict()["artifact_run_match"] == "mismatch"
    assert report.to_dict()["junit"] is None


def test_provider_revision_mismatch_is_not_hidden_by_matching_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contents = _zip()
    _install(monkeypatch, _responses(contents))
    report = _inspect(tmp_path, contents, request=_request(revision="b" * 40))
    assert report.exit_code == 1
    assert report.to_dict()["revision_match"] == "mismatch"
    assert report.to_dict()["run"]["provider_head_sha"] == REVISION
    assert report.to_dict()["tested_revision_binding"] == "unknown"


@pytest.mark.parametrize(
    "changes",
    [{"id": 999}, {"repository": {"id": 999}}, {"run_attempt": 1}],
)
def test_provider_run_not_matching_requested_identity_cannot_be_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changes: dict
) -> None:
    contents = _zip()
    _install(monkeypatch, _responses(contents, run=_run(**changes), attempt=_run()))
    report = _inspect(tmp_path, contents)
    assert report.exit_code == 2
    assert report.to_dict()["issues"] == ["scope_mismatch"]
    assert report.to_dict()["junit"] is None


@pytest.mark.parametrize(
    "field,value", [("head_repository", {"id": 999}), ("workflow_id", 999), ("event", "push"), ("head_sha", "b" * 40)]
)
def test_attempt_metadata_cannot_describe_a_different_run_subject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: Any
) -> None:
    contents = _zip()
    _install(monkeypatch, _responses(contents, attempt=_run(**{field: value})))
    report = _inspect(tmp_path, contents)
    assert report.exit_code == 2
    assert report.to_dict()["issues"] == ["scope_mismatch"]
    assert report.to_dict()["junit"] is None


@pytest.mark.parametrize("digest", [None, "absent"])
def test_missing_provider_digest_never_attributes_local_report_to_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, digest: str | None
) -> None:
    contents = _zip()
    artifact = _artifact(contents, digest=None)
    if digest == "absent":
        del artifact["digest"]
    _install(monkeypatch, _responses(contents, artifact=artifact))
    report = _inspect(tmp_path, contents)
    assert report.exit_code == 1
    assert report.to_dict()["collection_status"] == "incomplete"
    assert report.to_dict()["archive_binding"] == "unknown"
    assert report.to_dict()["issues"] == ["artifact_digest_unavailable"]
    assert report.to_dict()["junit"] is None


@pytest.mark.parametrize(
    "index,field", [(0, "id"), (1, "head_sha"), (2, "run_attempt"), (3, "workflow_run"), (3, "expired")]
)
def test_missing_metadata_is_incomplete_not_a_clean_association(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, index: int, field: str
) -> None:
    contents = _zip()
    responses = _responses(contents)
    del responses[index][field]
    _install(monkeypatch, responses)
    report = _inspect(tmp_path, contents)
    assert report.exit_code == 1
    assert report.to_dict()["collection_status"] == "incomplete"
    assert report.to_dict()["issues"] == ["metadata_incomplete"]
    assert report.to_dict()["junit"] is None


@pytest.mark.parametrize("field,value", [("digest", "sha256:" + "0" * 64), ("size_in_bytes", 1)])
def test_changed_local_archive_does_not_inherit_provider_association(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: Any
) -> None:
    contents = _zip()
    _install(monkeypatch, _responses(contents, artifact=_artifact(contents, **{field: value})))
    report = _inspect(tmp_path, contents)
    assert report.exit_code == 1
    assert report.to_dict()["archive_binding"] == "mismatched"
    assert report.to_dict()["junit"] is None


@pytest.mark.parametrize(
    "index,field,value", [(4, "digest", "sha256:" + "0" * 64), (5, "conclusion", "failure"), (6, "run_attempt", 3)]
)
def test_metadata_changed_during_collection_cannot_produce_usable_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, index: int, field: str, value: Any
) -> None:
    contents = _zip()
    responses = _responses(contents)
    responses[index][field] = value
    _install(monkeypatch, responses)
    report = _inspect(tmp_path, contents)
    assert report.exit_code == 2
    assert report.to_dict()["issues"] == ["run_changed"]
    assert report.to_dict()["junit"] is None


def test_expired_artifact_remains_incomplete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contents = _zip()
    _install(monkeypatch, _responses(contents, artifact=_artifact(contents, expired=True)))
    report = _inspect(tmp_path, contents)
    assert report.exit_code == 1
    assert report.to_dict()["issues"] == ["artifact_expired"]


def test_same_buffer_is_hashed_and_parsed_if_file_changes_during_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contents = _zip()
    path = tmp_path / "results.zip"
    replacement = _zip(_xml("<failure/>", failures=1))
    _install(monkeypatch, _responses(contents), on_get=lambda _: path.write_bytes(replacement))
    report = _inspect(tmp_path, contents)
    assert path.read_bytes() == replacement
    assert report.exit_code == 0
    assert report.to_dict()["archive_binding"] == "matched"
    assert report.to_dict()["junit"]["reported_outcome"] == "passed"


@pytest.mark.parametrize("tests", [2, 100])
def test_internally_incomplete_xml_stays_incomplete_with_matching_provider_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tests: int
) -> None:
    contents = _zip(_xml(tests=tests))
    _install(monkeypatch, _responses(contents))
    report = _inspect(tmp_path, contents)
    assert report.exit_code == 1
    assert report.to_dict()["collection_status"] == "incomplete"
    assert report.to_dict()["archive_binding"] == "matched"
    assert report.to_dict()["junit"]["collection_status"] == "incomplete"
    assert report.to_dict()["junit"]["reported_outcome"] == "unknown"


def _unsupported_archive(kind: str) -> bytes:
    if kind == "traversal":
        return _zip(member="../escaped.xml")
    if kind == "nul-name":
        raw_name = MEMBER.encode() + b"Zsuffix"
        return _zip(member=raw_name.decode()).replace(raw_name, MEMBER.encode() + b"\x00suffix")
    if kind == "symlink":
        info = zipfile.ZipInfo(MEMBER)
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        return _zip(b"target.xml", member=info)
    if kind == "compression":
        return _zip(compression=zipfile.ZIP_BZIP2)
    if kind == "encrypted":
        data = bytearray(_zip())
        struct.pack_into("<H", data, 6, 1)
        struct.pack_into("<H", data, data.index(b"PK\x01\x02") + 8, 1)
        return bytes(data)
    if kind == "truncated":
        return _zip()[:-20]
    if kind == "invalid-deflate":
        data = bytearray(_zip())
        name_length, extra_length = struct.unpack_from("<HH", data, 26)
        data[30 + name_length + extra_length] = 0x07  # Reserved DEFLATE block type.
        return bytes(data)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive, warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        archive.writestr(MEMBER, _xml())
        archive.writestr(MEMBER if kind == "duplicate" else "other.xml", _xml())
    return stream.getvalue()


@pytest.mark.parametrize(
    "kind",
    [
        "traversal",
        "nul-name",
        "symlink",
        "compression",
        "encrypted",
        "truncated",
        "invalid-deflate",
        "duplicate",
        "extra-member",
    ],
)
def test_unsupported_archives_do_not_contact_provider_or_extract_files(tmp_path: Path, kind: str) -> None:
    report = _inspect(tmp_path, _unsupported_archive(kind))
    assert report.exit_code == 2
    assert report.to_dict()["junit"] is None
    assert report.to_dict()["metadata_source"] is None
    assert sorted(path.name for path in tmp_path.iterdir()) == ["results.zip"]


@pytest.mark.parametrize(
    "limit,code", [("MAX_ARCHIVE_BYTES", "archive_limit_exceeded"), ("MAX_REPORT_BYTES", "report_limit_exceeded")]
)
def test_resource_limits_fail_before_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit: str, code: str
) -> None:
    monkeypatch.setattr(github_junit, limit, 32)
    report = _inspect(tmp_path, _zip())
    assert report.exit_code == 2
    assert report.to_dict()["issues"] == [code]


@pytest.mark.parametrize("xml", [b"<testsuite", b'<!DOCTYPE x [<!ENTITY x "private">]><testsuite>&x;</testsuite>'])
def test_malformed_or_unsafe_xml_is_rejected_before_network(tmp_path: Path, xml: bytes) -> None:
    report = _inspect(tmp_path, _zip(xml))
    assert report.exit_code == 2
    assert report.to_dict()["issues"] == ["invalid_junit_report"]


@pytest.mark.parametrize("missing", [False, True])
def test_non_regular_or_missing_local_inputs_are_value_free(tmp_path: Path, missing: bool) -> None:
    path = tmp_path / "private-path-canary"
    if not missing:
        path.mkdir()
    report = github_junit.inspect_github_junit(path, request=_request())
    assert report.exit_code == 2
    assert "private-path-canary" not in json.dumps(report.to_dict())


@pytest.mark.parametrize("code", ["not_found", "forbidden", "rate_limited", "redirect_refused", "transport_error"])
def test_provider_errors_are_not_reported_as_test_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str
) -> None:
    _install(monkeypatch, [GitHubCollectionError(code)])
    report = _inspect(tmp_path, _zip(), token="synthetic-token-canary")
    assert report.exit_code == 2
    assert report.to_dict()["issues"] == [code]
    assert report.to_dict()["junit"] is None
    assert "synthetic-token-canary" not in json.dumps(report.to_dict())


def test_unused_metadata_and_xml_free_text_are_not_echoed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contents = _zip(_xml("<failure message='private-canary'>private-canary</failure>", failures=1))
    _install(
        monkeypatch, _responses(contents, artifact=_artifact(contents, name="private-canary", url="private-canary"))
    )
    payload = _inspect(tmp_path, contents).to_dict()
    assert payload["junit"]["reported_outcome"] == "failed"
    assert "private-canary" not in json.dumps(payload)


@pytest.mark.parametrize(
    "changes",
    [
        {"repository": "owner/../private-canary"},
        {"repository": "https://github.com/example/project"},
        {"run_id": True},
        {"run_id": 0},
        {"attempt": -1},
        {"attempt": "2"},
        {"artifact_id": 2**63},
        {"revision": "main"},
        {"revision": "A" * 40},
        {"member": "../result.xml"},
        {"member": "/result.xml"},
        {"member": "a\\result.xml"},
        {"member": "a/./result.xml"},
        {"member": "a//result.xml"},
        {"member": "result.xml\x00hidden"},
    ],
)
def test_unsupported_request_values_are_rejected_before_io(changes: dict) -> None:
    with pytest.raises(ValueError) as error:
        _request(**changes)
    assert "private-canary" not in str(error.value)


def test_explicit_nested_member_is_read_without_extraction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contents = _zip(member="reports/results.xml")
    _install(monkeypatch, _responses(contents))
    report = _inspect(tmp_path, contents, request=_request(member="reports/results.xml"))
    assert report.exit_code == 0
    assert report.to_dict()["junit"]["reported_outcome"] == "passed"
    assert not (tmp_path / "reports").exists()
