from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from importlib.resources import files

import pytest
from jsonschema import Draft202012Validator

from evagix.verification import (
    CheckRequest,
    CheckSubject,
    ContractError,
    EvidenceBatch,
    RunEvidence,
    SourceAssessment,
    evaluate_check,
    parse_batch,
    parse_request,
)


@pytest.fixture
def schema():
    resource = files("evagix.schemas").joinpath("check-verification.schema.json")
    payload = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(payload)
    return payload


@pytest.fixture
def inputs():
    subject = CheckSubject("example/project", "a" * 40, "commit", "tests", "python:3.11")
    return CheckRequest(subject, "run-1", 1), RunEvidence("record-1", subject, "run-1", 1, "completed", "success")


def validator(schema, name=None):
    return Draft202012Validator(schema if name is None else {"$ref": f"#/$defs/{name}", "$defs": schema["$defs"]})


@pytest.mark.parametrize("conclusion", ["success", "failure", "skipped", "neutral", "cancelled", "timed_out", None])
@pytest.mark.parametrize("complete", [True, False])
@pytest.mark.parametrize("verified", [True, False])
def test_actual_result_payload_validates(schema, inputs, conclusion, complete, verified):
    check_request, record = inputs
    batch = EvidenceBatch("ci", "collector", (replace(record, conclusion=conclusion),), complete)
    assessment = SourceAssessment(batch.digest(), "verified", "fixture") if verified else None
    result = evaluate_check(check_request, batch, assessment=assessment)
    validator(schema).validate(result.to_dict())


def test_schema_rejects_false_success_and_unknown_fields(schema, inputs):
    check_request, record = inputs
    batch = EvidenceBatch("ci", "collector", (record,), True)
    result = evaluate_check(check_request, batch, assessment=SourceAssessment(batch.digest(), "verified", "fixture"))
    payload = result.to_dict()
    for field, value in (
        ("completeness", "incomplete"),
        ("source_verification", "unverified"),
        ("evidence_match", "unknown"),
        ("conclusion", "failure"),
        ("verifier", None),
        ("reason", "no_evidence"),
        ("evidence_ids", []),
        ("engine_status", "error"),
        ("policy_decision", "allow"),
        ("confidence", 1.0),
    ):
        assert not validator(schema).is_valid({**payload, field: value})
    for field in payload:
        missing = deepcopy(payload)
        del missing[field]
        assert not validator(schema).is_valid(missing)


def test_redacted_display_can_expand_identities_and_collapse_record_labels(schema, inputs):
    check_request, record = inputs
    identifier = "x" * 245 + " password=x"
    assert len(identifier) == 256
    subject = replace(check_request.subject, workflow=identifier)
    check_request = replace(check_request, subject=subject)
    records = tuple(replace(record, subject=subject, record_id=f"password={value}") for value in ("one", "two"))
    batch = EvidenceBatch("ci", identifier, records, True)
    result = evaluate_check(check_request, batch, assessment=SourceAssessment(batch.digest(), "verified", identifier))
    payload = result.to_dict()
    assert len(payload["source_id"]) > 256
    assert payload["evidence_ids"] == ["password=[REDACTED]", "password=[REDACTED]"]
    assert result.evidence_ids == ("password=one", "password=two")
    validator(schema).validate(payload)


def test_input_schema_and_runtime_reject_self_attestation(schema, inputs):
    check_request, record = inputs
    request_payload = check_request._payload()
    batch_payload = {
        "schema_version": "1.0",
        "kind": "check_evidence",
        "source_kind": "local",
        "source_id": "collector",
        "complete": True,
        "records": [record._payload()],
    }
    validator(schema, "request").validate(request_payload)
    validator(schema, "batch").validate(batch_payload)
    assert parse_request(request_payload) == check_request
    assert parse_batch(batch_payload).records == (record,)
    for field in ("verified", "assessment", "verifier", "batch_digest"):
        payload = {**batch_payload, field: "trusted"}
        assert not validator(schema, "batch").is_valid(payload)
        with pytest.raises(ContractError):
            parse_batch(payload)
    for payload in (None, [], {}, {**request_payload, "kind": "task_completed"}):
        with pytest.raises(ContractError):
            parse_request(payload)
    for payload in (None, [], {}, {**batch_payload, "records": [None]}, {**batch_payload, "records": {}}):
        with pytest.raises(ContractError):
            parse_batch(payload)


def test_batch_digest_matches_documented_canonical_bytes(inputs):
    _, record = inputs
    records = [record._payload(), replace(record, record_id="second")._payload()]

    def encode(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )

    canonical = {
        "schema_version": "1.0",
        "kind": "check_evidence",
        "source_kind": "local",
        "source_id": "collector",
        "complete": True,
        "records": sorted(records, key=encode),
    }
    batch = parse_batch(canonical)
    assert batch.digest() == hashlib.sha256(b"evagix.check-evidence.v1\0" + encode(canonical)).hexdigest()


@pytest.mark.parametrize("suffix", ["\n", "\r", "\r\n", "\u2028", " "])
def test_revision_and_digest_schema_reject_trailing_characters(schema, inputs, suffix):
    check_request, record = inputs
    payload = check_request._payload()
    payload["subject"]["revision"] += suffix
    assert not validator(schema, "request").is_valid(payload)
    with pytest.raises(ContractError):
        parse_request(payload)
    batch = EvidenceBatch("ci", "collector", (record,), True)
    result = evaluate_check(check_request, batch).to_dict()
    result["batch_digest"] += suffix
    assert not validator(schema).is_valid(result)
