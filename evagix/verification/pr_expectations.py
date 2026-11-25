"""Compare caller-supplied expectations with an already collected PR inventory."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from typing import Any

from evagix.security.redaction import redact_for_output
from evagix.verification.contracts import ContractError
from evagix.verification.github_pr_checks import PullRequestChecks

_MAX_ID = 2**63 - 1
_MAX_CHECKS = 100
_REPORT_LIMIT = 8_000_000


def _id(value: object) -> None:
    if type(value) is not int or not 1 <= value <= _MAX_ID:
        raise ContractError("Invalid expectation identifier")


def _fields(value: object, keys: set[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ContractError("Invalid expectation fields")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _report_size(value: object) -> int:
    size = len(_canonical(value))
    if size > _REPORT_LIMIT:
        raise ContractError(f"Expectations report exceeds the {_REPORT_LIMIT}-byte size limit")
    return size


@dataclass(frozen=True, repr=False)
class ExpectedCheck:
    revision: str
    kind: str
    name: str
    producer_id: int

    def __post_init__(self) -> None:
        if type(self.revision) is not str or self.revision not in {"head", "test_merge"}:
            raise ContractError("Invalid expectation revision")
        if type(self.kind) is not str or self.kind not in {"check_run", "commit_status"}:
            raise ContractError("Invalid expectation kind")
        if (
            type(self.name) is not str
            or not 1 <= len(self.name) <= 1024
            or any(unicodedata.category(c) in {"Cc", "Cs", "Zl", "Zp"} for c in self.name)
        ):
            raise ContractError("Invalid expectation name")
        _id(self.producer_id)

    def _payload(self) -> dict[str, Any]:
        return {"revision": self.revision, "kind": self.kind, "name": self.name, "producer_id": self.producer_id}


@dataclass(frozen=True, repr=False)
class CheckExpectations:
    repository_id: int
    checks: tuple[ExpectedCheck, ...]

    def __post_init__(self) -> None:
        _id(self.repository_id)
        if type(self.checks) is not tuple or not 1 <= len(self.checks) <= _MAX_CHECKS:
            raise ContractError("Expected checks must contain 1 to 100 entries")
        if not all(isinstance(check, ExpectedCheck) for check in self.checks):
            raise ContractError("Invalid expected check")
        if len(set(self.checks)) != len(self.checks):
            raise ContractError("Duplicate expected check")

    def digest(self) -> str:
        payload = {
            "schema_version": "1.0",
            "repository_id": self.repository_id,
            "checks": sorted((check._payload() for check in self.checks), key=_canonical),
        }
        return hashlib.sha256(b"evagix.pr-expectations.v1\0" + _canonical(payload)).hexdigest()


def parse_expectations(payload: object) -> CheckExpectations:
    data = _fields(payload, {"schema_version", "repository_id", "checks"})
    if type(data["schema_version"]) is not str or data["schema_version"] != "1.0":
        raise ContractError("Unsupported expectations version")
    if type(data["checks"]) is not list or not 1 <= len(data["checks"]) <= _MAX_CHECKS:
        raise ContractError("Expected checks must contain 1 to 100 entries")
    checks = tuple(
        ExpectedCheck(**_fields(item, {"revision", "kind", "name", "producer_id"})) for item in data["checks"]
    )
    return CheckExpectations(data["repository_id"], checks)


@dataclass(frozen=True, repr=False)
class CheckExpectationsReport:
    _payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = dict(redact_for_output(self._payload))
        _report_size(payload)
        return payload


def _compare(expected: ExpectedCheck, revision: dict[str, Any] | None) -> dict[str, Any]:
    observed = (
        [dict(row) for row in revision["checks"] if row["kind"] == expected.kind and row["name"] == expected.name]
        if revision is not None
        else []
    )
    matches = [row for row in observed if row["producer_id"] == expected.producer_id]
    outcome = "unverified"
    if revision is None:
        reason = "revision_unavailable"
    elif revision["completeness"] != "complete":
        reason = "incomplete_inventory"
    elif any(row["producer_id"] is None for row in observed):
        reason = "producer_unknown"
    elif len(matches) > 1:
        reason = "ambiguous_matches"
    elif not matches:
        outcome, reason = "missing", "producer_mismatch" if observed else "not_observed"
    else:
        result = matches[0]["result"]
        if result in {"passed", "failed", "pending"}:
            outcome = result
            reason = {"passed": "reported_success", "failed": "reported_failure", "pending": "reported_pending"}[result]
        else:
            reason = "non_success_conclusion" if result == "other" else "unknown_outcome"
    return {
        "expected": expected._payload(),
        "revision_sha": revision["sha"] if revision is not None else None,
        "inventory": revision["completeness"] if revision is not None else "unavailable",
        "outcome": outcome,
        "reason": reason,
        "observed": sorted(observed, key=lambda row: row["id"]),
    }


def compare_pr_checks(report: PullRequestChecks, expectations: CheckExpectations) -> CheckExpectationsReport:
    """Compare exact raw identities, not redacted names; this grants no policy authority."""
    if not isinstance(report, PullRequestChecks) or not isinstance(expectations, CheckExpectations):
        raise ContractError("Invalid expectations comparison input")
    # This path accepts the collector's internal snapshot, not imported report JSON.
    # Matching after redaction could equate distinct credential-like check names.
    source = report._payload
    if source["repository_id"] != expectations.repository_id:
        raise ContractError("Expectations repository does not match the collected repository")
    revisions = {revision["kind"]: revision for revision in source["revisions"]}
    payload = {
        "schema_version": "1.0",
        "kind": "github_pr_expectations",
        **{
            key: source[key]
            for key in (
                "repository",
                "repository_id",
                "pull_request",
                "base_sha",
                "head_sha",
                "test_merge_status",
                "completeness",
            )
        },
        "expectations_digest": expectations.digest(),
        "expectations_authority": "caller_supplied",
        "policy_decision": "not_evaluated",
        "results": [],
    }
    results: list[dict[str, Any]] = []
    # Count each row before retaining it. Distinct expected publishers can refer
    # to the same collected candidates; the expanded report must remain bounded.
    size = _report_size(payload)
    for expected in expectations.checks:
        row = _compare(expected, revisions.get(expected.revision))
        size += _report_size(row) + bool(results)
        if size > _REPORT_LIMIT:
            raise ContractError(f"Expectations report exceeds the {_REPORT_LIMIT}-byte size limit")
        results.append(row)
    payload["results"] = results
    return CheckExpectationsReport(payload)
