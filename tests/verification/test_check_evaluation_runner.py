from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest

from evagix.verification import ContractError
from scripts import evaluate_check_verification as runner


@pytest.fixture
def development_case():
    subject = {
        "repository": "sample/repo",
        "revision": "c" * 40,
        "subject_kind": "commit",
        "workflow": "test",
        "job": "unit",
    }
    return {
        "id": "development-success",
        "segment": "development",
        "assessment": "verified",
        "request": {
            "schema_version": "1.0",
            "kind": "check_succeeded",
            "subject": subject,
            "run_id": "123",
            "attempt": 1,
        },
        "batch": {
            "schema_version": "1.0",
            "kind": "check_evidence",
            "source_kind": "ci",
            "source_id": "fixture",
            "complete": True,
            "records": [
                {
                    "record_id": "r1",
                    "subject": subject,
                    "run_id": "123",
                    "attempt": 1,
                    "state": "completed",
                    "conclusion": "success",
                }
            ],
        },
        "expected": {"condition": "supported", "reason": "check_succeeded"},
    }


def write_dataset(directory, cases):
    data = json.dumps({"dataset_version": "1.0", "cases": cases}).encode("utf-8")
    (directory / "development.json").write_bytes(data)
    manifest = directory / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "dataset_version": "1.0",
                "file": "development.json",
                "sha256": hashlib.sha256(data).hexdigest(),
                "case_count": len(cases),
                "provenance": "development test",
                "limitations": ["Synthetic only"],
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_runner_counts_disagreements_and_false_support_with_known_denominators(tmp_path, development_case):
    failure = deepcopy(development_case)
    failure["id"] = "development-disagreement"
    failure["expected"] = {"condition": "contradicted", "reason": "check_failed"}
    invalid = deepcopy(development_case)
    invalid["id"] = "development-invalid"
    invalid["request"]["attempt"] = True
    invalid["expected"] = {"condition": "invalid_input", "reason": None}
    manifest = write_dataset(tmp_path, [development_case, failure, invalid])
    report = runner.evaluate_corpus(manifest)
    assert report["cases"] == 3
    assert report["disagreements"] == report["false_support"] == 1
    assert report["passed"] is False
    assert report["segments"] == {"development": {"cases": 3, "disagreements": 1, "false_support": 1}}
    assert report["confusion_counts"] == {
        "supported -> supported": 1,
        "contradicted -> supported": 1,
        "invalid_input -> invalid_input": 1,
    }
    assert len(report["implementation_sha256"]) == 64
    assert runner.main(["--manifest", str(manifest), "--output", str(tmp_path / "result.json")]) == 1


@pytest.mark.parametrize(
    "mode,reason",
    [
        ("missing", "source_unverified"),
        ("unverified", "source_unverified"),
        ("mismatched_digest", "source_binding_mismatch"),
    ],
)
def test_fixture_modes_do_not_imply_authentication(development_case, mode, reason):
    development_case["assessment"] = mode
    assert runner.evaluate_case(development_case) == {"condition": "unverified", "reason": reason}


def test_preserves_first_result_and_distinguishes_operational_failure(tmp_path, development_case, capsys):
    manifest = write_dataset(tmp_path, [development_case])
    output = tmp_path / "first.json"
    args = ["--manifest", str(manifest), "--output", str(output)]
    assert runner.main(args) == 0
    first = output.read_bytes()
    assert runner.main(args) == 2
    assert output.read_bytes() == first
    assert "could not complete" in capsys.readouterr().err
    (tmp_path / "development.json").write_text("{}", encoding="utf-8")
    assert runner.main(["--manifest", str(manifest)]) == 2


@pytest.mark.parametrize("mutation", ["duplicate", "invalid-expected", "invalid-mode", "invalid-reason"])
def test_invalid_corpus_is_not_scored_as_a_model_error(tmp_path, development_case, mutation):
    cases = [development_case]
    if mutation == "duplicate":
        cases *= 2
    elif mutation == "invalid-expected":
        development_case["expected"]["condition"] = "allow"
    elif mutation == "invalid-mode":
        development_case["assessment"] = "authenticated"
    else:
        development_case["expected"]["condition"] = "invalid_input"
    with pytest.raises(runner.DatasetError):
        runner.evaluate_corpus(write_dataset(tmp_path, cases))


def test_invariant_failure_for_valid_inputs_is_not_a_successful_invalid_input_case(
    tmp_path, development_case, monkeypatch
):
    development_case["expected"] = {"condition": "invalid_input", "reason": None}
    manifest = write_dataset(tmp_path, [development_case])

    def broken_evaluation(*args, **kwargs):
        raise ContractError("Internal invariant failed")

    monkeypatch.setattr(runner, "evaluate_check", broken_evaluation)
    assert runner.main(["--manifest", str(manifest)]) == 2


def test_manifest_cannot_select_a_file_outside_its_directory(tmp_path, development_case):
    manifest = write_dataset(tmp_path, [development_case])
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["file"] = "../outside.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    assert runner.main(["--manifest", str(manifest)]) == 2
