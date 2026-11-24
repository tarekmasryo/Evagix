from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from evagix.verification import CheckRequest, CheckSubject, ContractError, evaluate_check
from evagix.verification.github_actions import GitHubActionsScope, normalize_actions_attempt

REVISION = "a" * 40


@pytest.fixture
def scope():
    return GitHubActionsScope(10, 20, 2, pagination_complete=True)


@pytest.fixture
def run():
    return {
        "id": 20,
        "repository": {"id": 10},
        "head_repository": {"id": 10},
        "run_attempt": 2,
        "workflow_id": 30,
        "head_sha": REVISION,
        "event": "push",
    }


def job(identifier=40, **changes):
    return {
        "id": identifier,
        "run_id": 20,
        "run_attempt": 2,
        "head_sha": REVISION,
        "status": "completed",
        "conclusion": "success",
        **changes,
    }


def page(*jobs, total=None):
    return {"total_count": len(jobs) if total is None else total, "jobs": list(jobs)}


def request(identifier=40):
    return CheckRequest(
        CheckSubject(
            "github:repository:10", REVISION, "commit", "github-actions:workflow:30", f"github-actions:job:{identifier}"
        ),
        "20",
        2,
    )


@pytest.mark.parametrize(
    "state,conclusion",
    [
        ("queued", None),
        ("in_progress", None),
        ("completed", None),
        ("completed", "success"),
        ("completed", "failure"),
        ("completed", "skipped"),
        ("completed", "neutral"),
        ("completed", "cancelled"),
        ("completed", "timed_out"),
    ],
)
def test_import_preserves_job_outcome_without_authenticating_it(run, scope, state, conclusion):
    batch = normalize_actions_attempt(run, (page(job(status=state, conclusion=conclusion)),), scope=scope)

    assert batch.source_kind == "ci"
    assert batch.source_id == "github-actions:repository:10:run:20:attempt:2"
    assert batch.complete is True
    assert len(batch.records) == 1
    assert batch.records[0].subject == request().subject
    result = evaluate_check(request(), batch)
    assert (result.run_state, result.conclusion) == (state, conclusion)
    assert result.evidence_ids == ("github-actions:job:40",)
    assert result.evidence_match == "match"
    assert result.condition == "unverified"
    assert result.reason == "source_unverified"
    assert result.to_dict()["policy_decision"] == "not_evaluated"


def test_display_names_never_merge_distinct_jobs(run, scope):
    run["name"] = "tests"
    batch = normalize_actions_attempt(
        run,
        (page(job(name="tests", workflow_name=None), job(41, name="tests", conclusion="failure")),),
        scope=scope,
    )

    result = evaluate_check(request(41), batch)
    assert result.conclusion == "failure"
    assert result.evidence_ids == ("github-actions:job:41",)
    assert result.evidence_match == "match"
    assert len({record.subject.job for record in batch.records}) == 2


def test_metadata_does_not_inherit_requested_identity(run, scope):
    batch = normalize_actions_attempt(run, (page(job()),), scope=scope)
    wanted = replace(request(), subject=replace(request().subject, revision="b" * 40))
    result = evaluate_check(wanted, batch)
    assert result.condition == "unverified"
    assert result.evidence_match == "mismatch"
    assert batch.records[0].subject.revision == REVISION


def test_missing_optional_job_attempt_uses_declared_attempt_scope(run, scope):
    item = job()
    del item["run_attempt"]
    batch = normalize_actions_attempt(run, (page(item),), scope=scope)
    assert batch.records[0].attempt == 2
    assert evaluate_check(request(), batch).source_verification == "unverified"


@pytest.mark.parametrize(
    "field", ["id", "repository", "head_repository", "run_attempt", "workflow_id", "head_sha", "event"]
)
def test_missing_run_metadata_is_not_inferred(run, scope, field):
    del run[field]
    with pytest.raises(ContractError):
        normalize_actions_attempt(run, (page(job()),), scope=scope)


@pytest.mark.parametrize(
    "field,value",
    [
        ("repository", {"id": 11}),
        ("head_repository", {"id": 11}),
        ("repository", None),
        ("head_repository", {}),
        ("id", 21),
        ("run_attempt", 1),
        ("run_attempt", 3),
        ("run_attempt", True),
        ("workflow_id", "30"),
        ("workflow_id", 0),
        ("head_sha", None),
        ("head_sha", "main"),
        ("head_sha", "A" * 40),
        ("head_sha", "a" * 39),
    ],
)
def test_invalid_or_mixed_run_metadata_is_rejected_even_without_jobs(run, scope, field, value):
    run[field] = value
    with pytest.raises(ContractError):
        normalize_actions_attempt(run, (), scope=scope)


@pytest.mark.parametrize(
    "event", ["pull_request", "pull_request_target", "merge_group", "workflow_dispatch", "schedule", None]
)
def test_unsupported_event_cannot_be_imported_as_push_commit(run, scope, event):
    run["event"] = event
    with pytest.raises(ContractError, match="Unsupported GitHub event"):
        normalize_actions_attempt(run, (page(job()),), scope=scope)


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", True),
        ("id", "40"),
        ("id", 0),
        ("run_id", 21),
        ("head_sha", "b" * 40),
        ("run_attempt", 1),
        ("run_attempt", 3),
        ("run_attempt", None),
        ("run_attempt", 2.0),
        ("status", "waiting"),
        ("status", "requested"),
        ("status", "pending"),
        ("status", "cancelled"),
        ("status", []),
        ("conclusion", "action_required"),
        ("conclusion", "new_provider_value"),
        ("conclusion", {}),
    ],
)
def test_unsupported_or_mixed_job_metadata_is_not_coerced(run, scope, field, value):
    with pytest.raises(ContractError):
        normalize_actions_attempt(run, (page(job(**{field: value})),), scope=scope)


@pytest.mark.parametrize("field", ["id", "run_id", "head_sha", "status", "conclusion"])
def test_missing_job_fields_are_rejected(run, scope, field):
    item = job()
    del item[field]
    with pytest.raises(ContractError):
        normalize_actions_attempt(run, (page(item),), scope=scope)


@pytest.mark.parametrize("state", ["queued", "in_progress"])
def test_unfinished_job_cannot_carry_success(run, scope, state):
    with pytest.raises(ContractError, match="Only completed records"):
        normalize_actions_attempt(run, (page(job(status=state)),), scope=scope)


@pytest.mark.parametrize(
    "field,value",
    [
        ("repository_id", True),
        ("repository_id", 0),
        ("repository_id", 2**63),
        ("run_id", "20"),
        ("run_id", -1),
        ("attempt", 0),
        ("attempt", 2.0),
        ("attempt", 9_007_199_254_740_992),
        ("pagination_complete", 1),
        ("pagination_complete", "true"),
    ],
)
def test_collection_scope_has_strict_types_and_bounds(scope, field, value):
    with pytest.raises(ContractError):
        replace(scope, **{field: value})


def test_scope_must_be_explicit_not_payload_claim(run):
    with pytest.raises(ContractError, match="collection scope"):
        normalize_actions_attempt(run, (page(job()),), scope={"repository_id": 10, "run_id": 20, "attempt": 2})


def test_completeness_requires_count_and_collector_declaration(run, scope):
    undeclared = GitHubActionsScope(10, 20, 2)
    assert normalize_actions_attempt(run, (page(job()),), scope=undeclared).complete is False
    partial = normalize_actions_attempt(run, (page(job(), total=2),), scope=scope)
    assert partial.complete is False
    assert len(partial.records) == 1
    assert evaluate_check(request(), partial).completeness == "incomplete"
    assert normalize_actions_attempt(run, (), scope=scope).complete is False
    empty = normalize_actions_attempt(run, (page(),), scope=scope)
    assert empty.complete is True
    assert empty.records == ()
    assert evaluate_check(request(), empty).condition == "unverified"


def test_multiple_pages_are_deterministic_and_do_not_mutate_input(run, scope):
    pages = (page(job(42), job(41), total=3), page(job(40), total=3))
    before = deepcopy((run, pages))
    first = normalize_actions_attempt(run, pages, scope=scope)
    second = normalize_actions_attempt(run, (pages[1], page(job(41), job(42), total=3)), scope=scope)
    assert first.complete is True
    assert first == second
    assert first.digest() == second.digest()
    assert (run, pages) == before


@pytest.mark.parametrize(
    "pages",
    [
        [page(job())],
        (None,),
        ({"total_count": 1},),
        ({"total_count": 1, "jobs": {}},),
        ({"jobs": []},),
        (page(None),),
        (page(job(), total=True),),
        (page(job(), total=-1),),
        (page(job(), total="1"),),
        (page(job(), total=0),),
        (page(job(), total=2), page(job(41), total=3)),
        (page(job(), job()),),
        (page(job(), total=2), page(job(), total=2)),
        (page(job(), total=2), page(job(conclusion="failure"), total=2)),
        (page(),) * 11,
        (page(*(job(i) for i in range(1, 102))),),
    ],
)
def test_inconsistent_or_oversized_pages_are_rejected(run, scope, pages):
    with pytest.raises(ContractError):
        normalize_actions_attempt(run, pages, scope=scope)


def test_bounded_import_preserves_known_incomplete_large_inventory(run, scope):
    pages = tuple(page(*(job(i) for i in range(start, start + 100)), total=1000) for start in range(1, 1001, 100))
    full = normalize_actions_attempt(run, pages, scope=scope)
    assert len(full.records) == 1000
    assert full.complete is True
    partial = normalize_actions_attempt(run, (page(job(), total=1001),), scope=scope)
    assert partial.complete is False
    assert len(partial.records) == 1


def test_unused_labels_urls_steps_and_trust_claims_are_not_retained(run, scope):
    baseline = normalize_actions_attempt(run, (page(job()),), scope=scope)
    secret = "private-import-marker"
    extra = {
        "name": secret,
        "url": secret,
        "verified": True,
        "assessment": {"verification": "verified"},
        "complete": True,
    }
    run.update(extra)
    item = job(**extra, steps=[{"name": secret, "conclusion": "success"}])
    payload = {**page(item), **extra}
    batch = normalize_actions_attempt(run, (payload,), scope=scope)
    result = evaluate_check(request(), batch)
    assert batch == baseline
    assert batch.digest() == baseline.digest()
    assert result.source_verification == "unverified"
    assert secret not in json.dumps(result.to_dict())
    assert secret not in repr(batch)


@pytest.mark.parametrize("field", ["head_sha", "workflow_id", "event"])
def test_validation_errors_never_echo_untrusted_values(run, scope, field):
    secret = "private-import-marker"
    run[field] = secret
    with pytest.raises(ContractError) as exc:
        normalize_actions_attempt(run, (page(job()),), scope=scope)
    assert secret not in str(exc.value)


def test_non_object_run_is_rejected(scope):
    with pytest.raises(ContractError):
        normalize_actions_attempt([], (), scope=scope)
