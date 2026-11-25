from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from evagix.verification import pr_expectations
from evagix.verification.contracts import ContractError
from evagix.verification.github_pr_checks import PullRequestChecks
from evagix.verification.pr_expectations import CheckExpectations, ExpectedCheck, compare_pr_checks, parse_expectations


def check(identifier=1, producer=30, result="passed", **changes):
    status, conclusion = {
        "passed": ("completed", "success"),
        "failed": ("completed", "failure"),
        "pending": ("in_progress", None),
        "other": ("completed", "skipped"),
        "unknown": ("completed", "future_result"),
    }[result]
    return {
        "id": identifier,
        "kind": "check_run",
        "name": "Tests",
        "producer": "Example CI" if producer is not None else None,
        "producer_id": producer,
        "result": result,
        "status": status,
        "conclusion": conclusion,
        "url": f"https://github.com/example/project/runs/{identifier}",
        **changes,
    }


def snapshot(*checks, complete=True, merge_checks=None):
    revisions = [
        {
            "kind": "head",
            "sha": "b" * 40,
            "completeness": "complete" if complete else "incomplete",
            "checks": list(checks),
        }
    ]
    if merge_checks is not None:
        revisions.append({"kind": "test_merge", "sha": "c" * 40, "completeness": "complete", "checks": merge_checks})
    return PullRequestChecks(
        {
            "schema_version": "1.0",
            "kind": "github_pr_checks",
            "repository": "example/project",
            "repository_id": 10,
            "pull_request": 7,
            "state": "open",
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "test_merge_status": "available" if merge_checks is not None else "unavailable",
            "completeness": "complete" if complete else "incomplete",
            "policy_decision": "not_evaluated",
            "required_checks": "unknown",
            "revisions": revisions,
        }
    )


def expectations(**changes):
    return CheckExpectations(
        10, (ExpectedCheck(**{"revision": "head", "kind": "check_run", "name": "Tests", "producer_id": 30, **changes}),)
    )


def input_payload():
    return {
        "schema_version": "1.0",
        "repository_id": 10,
        "checks": [{"revision": "head", "kind": "check_run", "name": "Tests", "producer_id": 30}],
    }


def result(report, spec=None):
    return compare_pr_checks(report, spec or expectations()).to_dict()["results"][0]


@pytest.mark.parametrize(
    "rows,outcome,reason",
    [
        ([check()], "passed", "reported_success"),
        ([check(result="failed")], "failed", "reported_failure"),
        ([check(result="pending")], "pending", "reported_pending"),
        ([check(result="other")], "unverified", "non_success_conclusion"),
        ([check(result="unknown")], "unverified", "unknown_outcome"),
        ([], "missing", "not_observed"),
        ([check(producer=99)], "missing", "producer_mismatch"),
        ([check(producer=None)], "unverified", "producer_unknown"),
        ([check(), check(2, producer=None)], "unverified", "producer_unknown"),
        ([check(), check(2)], "unverified", "ambiguous_matches"),
        ([check(), check(2, result="failed")], "unverified", "ambiguous_matches"),
        ([check(), check(2, producer=99, result="failed")], "passed", "reported_success"),
    ],
)
def test_expected_check_decision_table_retains_source_evidence(rows, outcome, reason):
    actual = result(snapshot(*rows))
    assert (actual["outcome"], actual["reason"]) == (outcome, reason)
    assert actual["revision_sha"] == "b" * 40
    assert actual["inventory"] == "complete"
    assert actual["observed"] == rows


@pytest.mark.parametrize("rows", [[], [check()], [check(result="failed")], [check(producer=99)]])
def test_incomplete_revision_never_establishes_success_failure_or_absence(rows):
    actual = result(snapshot(*rows, complete=False))
    assert actual["outcome"] == "unverified"
    assert actual["reason"] == "incomplete_inventory"
    assert actual["observed"] == rows


def test_missing_merge_revision_never_falls_back_to_successful_head():
    actual = result(snapshot(check()), expectations(revision="test_merge"))
    assert actual["outcome"] == "unverified"
    assert actual["reason"] == "revision_unavailable"
    assert actual["revision_sha"] is None
    assert actual["inventory"] == "unavailable"
    assert actual["observed"] == []


def test_explicit_revision_and_local_completeness_control_comparison():
    report = snapshot(check(), complete=False, merge_checks=[check(2, result="failed")])
    actual = compare_pr_checks(report, expectations(revision="test_merge")).to_dict()
    assert actual["completeness"] == "incomplete"
    assert actual["results"][0]["outcome"] == "failed"
    assert actual["results"][0]["revision_sha"] == "c" * 40
    assert actual["policy_decision"] == "not_evaluated"
    assert actual["expectations_authority"] == "caller_supplied"


@pytest.mark.parametrize("name", ["tests", " Tests", "Tests ", "Tests.*", "Tests (3.11)"])
def test_names_are_exact_not_casefolded_trimmed_or_expanded(name):
    assert result(snapshot(check()), expectations(name=name))["reason"] == "not_observed"


def test_unknown_producer_of_unrelated_check_is_not_ambiguous():
    actual = result(snapshot(check(), check(2, producer=None, name="Docs")))
    assert actual["outcome"] == "passed"
    assert len(actual["observed"]) == 1


def test_check_and_status_producers_are_separate_identity_namespaces():
    status = check(kind="commit_status", status="success", conclusion=None)
    assert result(snapshot(status))["outcome"] == "missing"
    assert result(snapshot(status), expectations(kind="commit_status"))["outcome"] == "passed"


def test_matrix_expectations_do_not_disappear_when_other_jobs_pass():
    spec = CheckExpectations(
        10, tuple(ExpectedCheck("head", "check_run", f"Tests ({os})", 30) for os in ("Linux", "Windows"))
    )
    report = compare_pr_checks(snapshot(check(name="Tests (Linux)")), spec).to_dict()
    assert [(r["expected"]["name"], r["outcome"]) for r in report["results"]] == [
        ("Tests (Linux)", "passed"),
        ("Tests (Windows)", "missing"),
    ]


def test_snapshot_is_not_mutated_and_matching_precedes_redaction():
    source = snapshot(check(name="token=synthetic-one"))
    before = deepcopy(source._payload)
    actual = compare_pr_checks(source, expectations(name="token=synthetic-two")).to_dict()
    assert actual["results"][0]["outcome"] == "missing"
    assert source._payload == before
    assert "synthetic-two" not in json.dumps(actual)
    assert "synthetic-two" not in repr(expectations(name="token=synthetic-two"))
    matched = compare_pr_checks(source, expectations(name="token=synthetic-one"))
    assert matched.to_dict()["results"][0]["outcome"] == "passed"
    assert "synthetic-one" not in json.dumps(matched.to_dict())
    assert "synthetic-one" not in repr(matched)


def test_repository_mismatch_does_not_produce_a_comparison():
    with pytest.raises(ContractError, match="repository"):
        compare_pr_checks(snapshot(check()), CheckExpectations(11, expectations().checks))


def test_digest_binds_exact_expectations_but_not_entry_order():
    first, second = expectations().checks[0], expectations(name="Docs").checks[0]
    spec = CheckExpectations(10, (first, second))
    assert spec.digest() == CheckExpectations(10, (second, first)).digest()
    assert spec.digest() != CheckExpectations(11, spec.checks).digest()
    for key, value in (("revision", "test_merge"), ("kind", "commit_status"), ("name", " Tests"), ("producer_id", 31)):
        assert spec.digest() != CheckExpectations(10, (replace(first, **{key: value}), second)).digest()


@pytest.mark.parametrize("value", [None, True, False, 0, -1, 2**63, 1.0, "1", [], {}])
@pytest.mark.parametrize("field", ["repository_id", "producer_id"])
def test_invalid_identifiers_are_rejected(value, field):
    payload = input_payload()
    target = payload if field == "repository_id" else payload["checks"][0]
    target[field] = value
    with pytest.raises(ContractError):
        parse_expectations(payload)


@pytest.mark.parametrize("name", ["", "a" * 1025, "Tests\n", "Tests\x00", "Tests\u2028", "Tests\ud800", None, 1, []])
def test_invalid_names_are_rejected_without_echoing_input(name):
    payload = input_payload()
    payload["checks"][0]["name"] = name
    with pytest.raises(ContractError, match="^Invalid expectation name$"):
        parse_expectations(payload)


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 1},
        {"schema_version": "2.0"},
        {"checks": []},
        {"checks": {}},
        {"checks": [None]},
        {"extra": "token=private"},
    ],
)
def test_input_version_structure_and_unknown_fields_are_rejected(changes):
    with pytest.raises(ContractError):
        parse_expectations({**input_payload(), **changes})


@pytest.mark.parametrize(
    "changes", [{"kind": []}, {"kind": "job"}, {"revision": {}}, {"revision": "latest"}, {"extra": 1}]
)
def test_invalid_check_selectors_are_rejected(changes):
    payload = input_payload()
    payload["checks"][0].update(changes)
    with pytest.raises(ContractError):
        parse_expectations(payload)


def test_missing_fields_and_duplicate_or_oversized_sets_are_rejected():
    for key in input_payload():
        payload = input_payload()
        del payload[key]
        with pytest.raises(ContractError):
            parse_expectations(payload)
    for key in input_payload()["checks"][0]:
        payload = input_payload()
        del payload["checks"][0][key]
        with pytest.raises(ContractError):
            parse_expectations(payload)
    for count in (2, 101):
        payload = input_payload()
        payload["checks"] *= count
        with pytest.raises(ContractError):
            parse_expectations(payload)


def test_supported_boundaries_and_direct_construction():
    payload = input_payload()
    payload["repository_id"] = 2**63 - 1
    payload["checks"] = [dict(payload["checks"][0], name=f"فحص {i}", producer_id=2**63 - 1) for i in range(100)]
    assert len(parse_expectations(payload).checks) == 100
    assert parse_expectations(input_payload()) == expectations()
    for value in ([], (), (None,), (expectations().checks[0],) * 2):
        with pytest.raises(ContractError):
            CheckExpectations(10, value)
    for report, spec in (({}, expectations()), (snapshot(), {})):
        with pytest.raises(ContractError):
            compare_pr_checks(report, spec)


def test_report_budget_accepts_exact_size_and_rejects_one_byte_over(monkeypatch):
    source, spec = snapshot(check()), expectations()
    payload = compare_pr_checks(source, spec).to_dict()
    size = len(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    monkeypatch.setattr(pr_expectations, "_REPORT_LIMIT", size)
    assert compare_pr_checks(source, spec).to_dict() == payload
    monkeypatch.setattr(pr_expectations, "_REPORT_LIMIT", size - 1)
    with pytest.raises(ContractError, match="size limit"):
        compare_pr_checks(source, spec)


def test_repeated_candidate_groups_cannot_amplify_into_unbounded_report():
    source = snapshot(*(check(i, url="https://example.test/" + "a" * 1900) for i in range(1, 301)))
    spec = CheckExpectations(10, tuple(ExpectedCheck("head", "check_run", "Tests", i) for i in range(1, 101)))
    with pytest.raises(ContractError, match="8000000-byte size limit"):
        compare_pr_checks(source, spec)


def test_size_limit_also_covers_redaction_expansion(monkeypatch):
    source, spec = snapshot(check(name="token=x")), expectations(name="token=x")
    report = compare_pr_checks(source, spec)

    def size(value):
        return len(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    raw_size = size(report._payload)
    assert size(report.to_dict()) > raw_size
    monkeypatch.setattr(pr_expectations, "_REPORT_LIMIT", raw_size)
    report = compare_pr_checks(source, spec)
    with pytest.raises(ContractError, match="size limit"):
        report.to_dict()
