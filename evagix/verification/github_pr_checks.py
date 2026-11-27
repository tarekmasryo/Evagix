"""Bounded, advisory snapshots of the checks GitHub reports for a pull request."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from evagix.security.redaction import redact_for_output
from evagix.verification.github_collection import GitHubCollectionError, _Client, _has_next, _repository_name

_MAX_ID = 2**63 - 1
_PAGES_PER_STREAM = 3


def _invalid() -> GitHubCollectionError:
    return GitHubCollectionError("invalid_response")


def _object(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        raise _invalid()
    return value


def _integer(value: object, *, minimum: int = 1) -> int:
    if type(value) is not int or not minimum <= value <= _MAX_ID:
        raise _invalid()
    return value


def _text(value: object, *, limit: int = 1024) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= limit
        or any(unicodedata.category(c) in {"Cc", "Cs", "Zl", "Zp"} for c in value)
    ):
        raise _invalid()
    return value


def _sha(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value) is None:
        raise _invalid()
    return value


def _pull_url(value: object) -> tuple[str, int]:
    if type(value) is not str:
        raise GitHubCollectionError("invalid_pull_request")
    match = re.fullmatch(r"https://github\.com/([^/?#]+/[^/?#]+)/pull/([1-9][0-9]{0,18})/?", value)
    if match is None or int(match[2]) > _MAX_ID:
        raise GitHubCollectionError("invalid_pull_request")
    try:
        repository = _repository_name(match[1])
    except GitHubCollectionError:
        raise GitHubCollectionError("invalid_pull_request") from None
    return repository, int(match[2])


def _link(value: object) -> str | None:
    # Detail links are displayed only. Never request them or send credentials.
    if (
        type(value) is not str
        or len(value) > 2048
        or any(c.isspace() or unicodedata.category(c)[0] == "C" for c in value)
    ):
        return None
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return None
        if parsed.port is not None and parsed.port != 443:
            return None
    except ValueError:
        return None
    return value


@dataclass(frozen=True, repr=False)
class PullRequestChecks:
    """An advisory report; completeness covers endpoint inventories, not policy."""

    _payload: dict[str, Any]
    _head_repository_id: int | None = None

    @property
    def head_repository_id(self) -> int | None:
        """Observed PR source repository, kept outside the existing JSON contract."""
        return self._head_repository_id

    @property
    def complete(self) -> bool:
        return bool(self._payload["completeness"] == "complete")

    def to_dict(self) -> dict[str, Any]:
        return dict(redact_for_output(self._payload))


def _pr_snapshot(payload: object, repository: str, repository_id: int, number: int) -> dict[str, Any]:
    pr = _object(payload)
    base, head = _object(pr.get("base")), _object(pr.get("head"))
    base_repo = _object(base.get("repo"))
    if (
        _integer(pr.get("number")) != number
        or _integer(base_repo.get("id")) != repository_id
        or _text(base_repo.get("full_name"), limit=140).lower() != repository.lower()
    ):
        raise GitHubCollectionError("scope_mismatch")
    state = pr.get("state")
    merged, mergeable = pr.get("merged"), pr.get("mergeable")
    if (
        state not in ("open", "closed")
        or type(merged) is not bool
        or (mergeable is not None and type(mergeable) is not bool)
    ):
        raise _invalid()
    if state == "open" and merged:
        raise _invalid()
    merge_sha = None if pr.get("merge_commit_sha") is None else _sha(pr["merge_commit_sha"])
    head_repository = head.get("repo")
    head_repository_id = None if head_repository is None else _integer(_object(head_repository).get("id"))
    return {
        "id": _integer(pr.get("id")),
        "base_sha": _sha(base.get("sha")),
        "head_sha": _sha(head.get("sha")),
        "base_ref": _text(base.get("ref")),
        "head_ref": _text(head.get("ref")),
        "head_repository_id": head_repository_id,
        "state": state,
        "merged": merged,
        "mergeable": mergeable,
        "merge_sha": merge_sha,
    }


def _check(value: object, revision: str) -> dict[str, Any]:
    check = _object(value)
    if _sha(check.get("head_sha")) != revision:
        raise GitHubCollectionError("scope_mismatch")
    status = _text(check.get("status"), limit=64)
    if "conclusion" not in check:
        raise _invalid()
    conclusion = check["conclusion"]
    if conclusion is not None:
        conclusion = _text(conclusion, limit=64)
    result = "unknown"
    if status in {"queued", "in_progress", "waiting", "pending", "requested"} and conclusion is None:
        result = "pending"
    elif status == "completed":
        if conclusion == "success":
            result = "passed"
        elif conclusion in {"failure", "timed_out", "action_required", "startup_failure"}:
            result = "failed"
        elif conclusion in {"skipped", "neutral", "cancelled", "stale"}:
            result = "other"
    app = check.get("app")
    producer, producer_id = None, None
    if app is not None:
        app = _object(app)
        producer, producer_id = _text(app.get("name"), limit=256), _integer(app.get("id"))
    return {
        "kind": "check_run",
        "id": _integer(check.get("id")),
        "name": _text(check.get("name")),
        "producer": producer,
        "producer_id": producer_id,
        "status": status,
        "conclusion": conclusion,
        "result": result,
        "url": _link(check.get("html_url")) or _link(check.get("details_url")),
    }


def _status(value: object) -> dict[str, Any]:
    status = _object(value)
    state = _text(status.get("state"), limit=64)
    creator = status.get("creator")
    producer, producer_id = None, None
    if creator is not None:
        creator = _object(creator)
        producer, producer_id = _text(creator.get("login"), limit=256), _integer(creator.get("id"))
    return {
        "kind": "commit_status",
        "id": _integer(status.get("id")),
        "name": _text(status.get("context")),
        "producer": producer,
        "producer_id": producer_id,
        "status": state,
        "conclusion": None,
        "result": {"success": "passed", "failure": "failed", "error": "failed", "pending": "pending"}.get(
            state, "unknown"
        ),
        "url": _link(status.get("target_url")),
    }


def _inventory(
    client: _Client, repo_path: str, repository_id: int, revision: str, *, statuses: bool
) -> tuple[list[dict[str, Any]], bool]:
    path = f"{repo_path}/commits/{revision}/{'status' if statuses else 'check-runs'}"
    filters = {} if statuses else {"filter": "latest"}
    suffix = "" if statuses else "&filter=latest"
    total: int | None = None
    combined_state: str | None = None
    records: list[dict[str, Any]] = []
    ids: set[int] = set()
    contexts: set[str] = set()
    more = True
    for page_number in range(1, _PAGES_PER_STREAM + 1):
        page, links = client.get(f"{path}?per_page=100&page={page_number}{suffix}")
        count = _integer(page.get("total_count"), minimum=0)
        if total is not None and count != total:
            raise _invalid()
        total = count
        if statuses:
            if (
                _sha(page.get("sha")) != revision
                or _integer(_object(page.get("repository")).get("id")) != repository_id
            ):
                raise GitHubCollectionError("scope_mismatch")
            state = _text(page.get("state"), limit=64)
            if combined_state is not None and state != combined_state:
                raise _invalid()
            combined_state = state
        values = page.get("statuses" if statuses else "check_runs")
        if type(values) is not list or len(values) > 100:
            raise _invalid()
        for value in values:
            record = _status(value) if statuses else _check(value, revision)
            if record["id"] in ids or (statuses and record["name"] in contexts):
                raise _invalid()
            ids.add(record["id"])
            contexts.add(record["name"])
            records.append(record)
        if len(records) > total:
            raise _invalid()
        more = _has_next(links, path, page_number + 1, filters=filters)
        if not more:
            break
    return records, not more and len(records) == total


def collect_pr_checks(url: str, *, token: str | None = None) -> PullRequestChecks:
    """Collect observed head/test-merge checks without evaluating required policy."""
    repository, number = _pull_url(url)
    # The 2026 API removed merge_commit_sha; this supported version retains it.
    client = _Client(token, api_version="2022-11-28")
    repo_path = f"/repos/{repository}"
    repo, _ = client.get(repo_path)
    repository_id = _integer(repo.get("id"))
    if _text(repo.get("full_name"), limit=140).lower() != repository.lower():
        raise GitHubCollectionError("scope_mismatch")
    pr_path = f"{repo_path}/pulls/{number}"
    before, _ = client.get(pr_path)
    snapshot = _pr_snapshot(before, repository, repository_id, number)
    merge_status = "not_applicable" if snapshot["state"] == "closed" else "unavailable"
    targets = [("head", snapshot["head_sha"])]
    if (
        snapshot["state"] == "open"
        and snapshot["mergeable"] is True
        and snapshot["merge_sha"] is not None
        and snapshot["merge_sha"] != snapshot["head_sha"]
    ):
        merge_status = "available"
        targets.append(("test_merge", snapshot["merge_sha"]))
    revisions = []
    for kind, revision in targets:
        checks, checks_complete = _inventory(client, repo_path, repository_id, revision, statuses=False)
        statuses, statuses_complete = _inventory(client, repo_path, repository_id, revision, statuses=True)
        revisions.append(
            {
                "kind": kind,
                "sha": revision,
                "completeness": "complete" if checks_complete and statuses_complete else "incomplete",
                "checks": sorted(checks + statuses, key=lambda c: (c["kind"], c["name"], c["id"])),
            }
        )
    after, _ = client.get(pr_path)
    if _pr_snapshot(after, repository, repository_id, number) != snapshot:
        raise GitHubCollectionError("pr_changed")
    return PullRequestChecks(
        {
            "schema_version": "1.0",
            "kind": "github_pr_checks",
            "repository": repository,
            "repository_id": repository_id,
            "pull_request": number,
            "state": snapshot["state"],
            "base_sha": snapshot["base_sha"],
            "head_sha": snapshot["head_sha"],
            "test_merge_status": merge_status,
            "completeness": "complete" if all(r["completeness"] == "complete" for r in revisions) else "incomplete",
            "policy_decision": "not_evaluated",
            "required_checks": "unknown",
            "revisions": revisions,
        },
        _head_repository_id=snapshot["head_repository_id"],
    )
