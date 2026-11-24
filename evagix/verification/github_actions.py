"""Normalize declared GitHub Actions snapshots without collecting or trusting them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from evagix.verification.contracts import (
    MAX_ATTEMPT,
    MAX_RECORDS,
    CheckSubject,
    Conclusion,
    ContractError,
    EvidenceBatch,
    RunEvidence,
    RunState,
)

_MAX_ID = 2**63 - 1
_PAGE_SIZE = 100
_MAX_PAGES = MAX_RECORDS // _PAGE_SIZE
_STATUSES = {"queued", "in_progress", "completed"}
_CONCLUSIONS = {"success", "failure", "neutral", "cancelled", "skipped", "timed_out"}


def _integer(value: object, field: str, *, minimum: int = 1, maximum: int = _MAX_ID) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ContractError(f"Invalid GitHub {field}")
    return value


def _object(value: object, field: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ContractError(f"Invalid GitHub {field}")
    return value


@dataclass(frozen=True, repr=False)
class GitHubActionsScope:
    """Declared collection scope, not authenticated provenance or a check request."""

    repository_id: int
    run_id: int
    attempt: int
    pagination_complete: bool = False

    def __post_init__(self) -> None:
        _integer(self.repository_id, "repository ID")
        _integer(self.run_id, "run ID")
        _integer(self.attempt, "attempt", maximum=MAX_ATTEMPT)
        if type(self.pagination_complete) is not bool:
            raise ContractError("Invalid GitHub pagination completeness")


def normalize_actions_attempt(
    run_payload: object,
    job_pages: tuple[object, ...],
    *,
    scope: GitHubActionsScope,
) -> EvidenceBatch:
    """Import one push run attempt; the returned batch has no source assessment.

    Pages must be declared to come from the attempt-specific jobs endpoint.
    SHA matching describes provider metadata, not the files actually tested.
    """
    if not isinstance(scope, GitHubActionsScope):
        raise ContractError("Invalid GitHub collection scope")
    run = _object(run_payload, "run")
    repository = _object(run.get("repository"), "repository")
    head_repository = _object(run.get("head_repository"), "head repository")
    if (
        _integer(repository.get("id"), "repository ID") != scope.repository_id
        or _integer(head_repository.get("id"), "head repository ID") != scope.repository_id
        or _integer(run.get("id"), "run ID") != scope.run_id
        or _integer(run.get("run_attempt"), "attempt", maximum=MAX_ATTEMPT) != scope.attempt
    ):
        raise ContractError("GitHub run does not match collection scope")
    if run.get("event") != "push":
        raise ContractError("Unsupported GitHub event")
    workflow_id = _integer(run.get("workflow_id"), "workflow ID")
    repository_id = f"github:repository:{scope.repository_id}"
    workflow = f"github-actions:workflow:{workflow_id}"
    # Reuse the contract's full-revision validation even for an empty inventory.
    revision = run.get("head_sha")
    if type(revision) is not str:
        raise ContractError("Invalid GitHub revision")
    subject = CheckSubject(repository_id, revision, "commit", workflow, "unselected")
    if type(job_pages) is not tuple or len(job_pages) > _MAX_PAGES:
        raise ContractError("Invalid GitHub job pages")

    total: int | None = None
    identifiers: set[int] = set()
    records = []
    for payload in job_pages:
        page = _object(payload, "jobs page")
        count = _integer(page.get("total_count"), "job count", minimum=0)
        if total is not None and total != count:
            raise ContractError("Inconsistent GitHub job counts")
        total = count
        jobs = page.get("jobs")
        if type(jobs) is not list or len(jobs) > _PAGE_SIZE:
            raise ContractError("Invalid GitHub jobs")
        for value in jobs:
            job = _object(value, "job")
            identifier = _integer(job.get("id"), "job ID")
            if identifier in identifiers:
                raise ContractError("Duplicate GitHub job ID")
            identifiers.add(identifier)
            if _integer(job.get("run_id"), "job run ID") != scope.run_id or job.get("head_sha") != subject.revision:
                raise ContractError("GitHub job does not match run")
            if (
                "run_attempt" in job
                and _integer(job["run_attempt"], "job attempt", maximum=MAX_ATTEMPT) != scope.attempt
            ):
                raise ContractError("GitHub job does not match attempt")
            status = job.get("status")
            if type(status) is not str or status not in _STATUSES:
                raise ContractError("Unsupported GitHub job status")
            if "conclusion" not in job:
                raise ContractError("Missing GitHub job conclusion")
            conclusion = job["conclusion"]
            if conclusion is not None and (type(conclusion) is not str or conclusion not in _CONCLUSIONS):
                raise ContractError("Unsupported GitHub job conclusion")
            job_id = f"github-actions:job:{identifier}"
            records.append(
                RunEvidence(
                    job_id,
                    CheckSubject(repository_id, subject.revision, "commit", workflow, job_id),
                    str(scope.run_id),
                    scope.attempt,
                    cast(RunState, status),
                    cast(Conclusion | None, conclusion),
                )
            )
    if total is not None and len(records) > total:
        raise ContractError("GitHub jobs exceed reported total")
    return EvidenceBatch(
        source_kind="ci",
        source_id=f"github-actions:repository:{scope.repository_id}:run:{scope.run_id}:attempt:{scope.attempt}",
        records=tuple(sorted(records, key=lambda record: record.record_id)),
        complete=scope.pagination_complete and total is not None and len(records) == total,
    )
