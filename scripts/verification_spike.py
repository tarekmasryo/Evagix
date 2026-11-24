"""Experimental offline decision model; synthetic provenance is NOT CI authentication."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from typing import Literal

SubjectKind = Literal["commit", "test_merge"]
RunState = Literal["completed", "queued", "in_progress", "cancelled"]
Conclusion = Literal["success", "failure", "skipped", "neutral", "cancelled", "timed_out"]


@dataclass(frozen=True)
class CheckClaim:
    repository: str
    revision: str
    subject_kind: SubjectKind
    check: str
    job: str
    kind: Literal["check_succeeded"] = "check_succeeded"

    def __post_init__(self) -> None:
        if self.kind != "check_succeeded":
            raise ValueError("Only check_succeeded is supported")
        if self.subject_kind not in {"commit", "test_merge"}:
            raise ValueError("Unsupported subject kind")
        if not all(value.strip() for value in (self.repository, self.revision, self.check, self.job)):
            raise ValueError("Claim identity must be explicit and nonempty")


@dataclass(frozen=True)
class Evidence:
    subject: CheckClaim
    run_id: str
    attempt: int
    state: RunState
    conclusion: Conclusion | None = None

    def __post_init__(self) -> None:
        if not self.run_id.strip() or type(self.attempt) is not int or self.attempt < 1:
            raise ValueError("Run identity and a positive integer attempt are required")
        if self.state not in {"completed", "queued", "in_progress", "cancelled"}:
            raise ValueError("Unsupported operational state")
        if self.conclusion not in {None, "success", "failure", "skipped", "neutral", "cancelled", "timed_out"}:
            raise ValueError("Unsupported conclusion")
        if self.state != "completed" and self.conclusion is not None:
            raise ValueError("Only completed runs may carry a conclusion")


@dataclass(frozen=True)
class SyntheticFixtureSource:
    """Harness-owned assertions, not a security boundary or production trust API.

    Only the exact fixture objects in records receive simulated provenance.
    Local copies, even with identical fields, receive no such assessment.
    The harness selects the run and latest attempt; run IDs have no ordering.
    """

    records: tuple[Evidence, ...]
    selected_run_id: str
    latest_attempt: int
    inventory_complete: bool = True

    def __post_init__(self) -> None:
        if not self.selected_run_id.strip() or type(self.latest_attempt) is not int or self.latest_attempt < 1:
            raise ValueError("A selected run and positive latest attempt are required")

    def recognizes(self, evidence: Evidence) -> bool:
        return any(evidence is record for record in self.records)


@dataclass(frozen=True)
class Result:
    claim: CheckClaim
    source_verification: Literal["synthetic_verified", "unverified", "missing"]
    freshness: Literal["current", "stale", "unknown"]
    completeness: Literal["complete", "incomplete", "not_covered"]
    condition_result: Literal["satisfied", "contradicted", "unverified"]
    operational_state: str
    reason: str


def evaluate(
    claim: CheckClaim,
    reports: tuple[Evidence, ...],
    *,
    fixture_source: SyntheticFixtureSource | None = None,
    uncommitted_work: bool = False,
) -> Result:
    """Evaluate a scoped check result without execution, network, clocks, or mutation."""
    result = Result(claim, "missing", "unknown", "incomplete", "unverified", "missing", "no_evidence")
    if uncommitted_work:
        return replace(result, completeness="not_covered", operational_state="not_covered", reason="uncommitted_work")
    matching = tuple(report for report in reports if report.subject == claim)
    if not matching:
        if reports:
            return replace(result, source_verification="unverified", reason="subject_mismatch")
        return result
    verified = tuple(report for report in matching if fixture_source is not None and fixture_source.recognizes(report))
    if not verified or fixture_source is None:
        return replace(
            result, source_verification="unverified", operational_state="not_evaluated", reason="source_unverified"
        )
    result = replace(result, source_verification="synthetic_verified")
    if not fixture_source.inventory_complete:
        return replace(result, operational_state="incomplete", reason="inventory_incomplete")
    selected_run = tuple(report for report in verified if report.run_id == fixture_source.selected_run_id)
    if not selected_run:
        return replace(result, freshness="stale", reason="selected_run_missing")
    if any(report.attempt > fixture_source.latest_attempt for report in selected_run):
        return replace(result, operational_state="inconsistent", reason="attempt_inventory_inconsistent")
    selected = set(report for report in selected_run if report.attempt == fixture_source.latest_attempt)
    if not selected:
        return replace(result, freshness="stale", reason="latest_attempt_missing")
    result = replace(result, freshness="current")
    if len(selected) != 1:
        return replace(result, operational_state="conflicting", reason="conflicting_results")
    report = selected.pop()
    result = replace(result, operational_state=report.state)
    if report.state != "completed":
        return replace(result, reason="run_not_completed")
    if report.conclusion is None:
        return replace(result, reason="conclusion_missing")
    result = replace(result, completeness="complete")
    if report.conclusion == "success":
        return replace(result, condition_result="satisfied", reason="scoped_check_succeeded")
    if report.conclusion == "failure":
        return replace(result, condition_result="contradicted", reason="scoped_check_failed")
    return replace(result, reason=f"non_decisive_conclusion:{report.conclusion}")


@dataclass(frozen=True)
class Assessment:
    required_checks: tuple[Result, ...]
    submitted_claims: tuple[Result, ...]
    required_check_decision: Literal["satisfied", "contradicted", "unverified"]


def assess(
    required_checks: tuple[CheckClaim, ...],
    submitted_claims: tuple[CheckClaim, ...],
    reports: tuple[Evidence, ...],
    *,
    fixture_source: SyntheticFixtureSource | None = None,
    uncommitted_work: bool = False,
) -> Assessment:
    """Required checks are harness policy, independent of optional submitted claims."""
    required = tuple(
        evaluate(claim, reports, fixture_source=fixture_source, uncommitted_work=uncommitted_work)
        for claim in required_checks
    )
    submitted = tuple(
        evaluate(claim, reports, fixture_source=fixture_source, uncommitted_work=uncommitted_work)
        for claim in submitted_claims
    )
    decision: Literal["satisfied", "contradicted", "unverified"] = "unverified"
    if any(result.condition_result == "contradicted" for result in required):
        decision = "contradicted"
    elif required and all(result.condition_result == "satisfied" for result in required):
        decision = "satisfied"
    return Assessment(required, submitted, decision)


def naive_any_success(reports: tuple[Evidence, ...]) -> bool:
    """Intentionally weak demonstration baseline, not a model of GitHub CI."""
    return any(report.state == "completed" and report.conclusion == "success" for report in reports)


def demo() -> dict[str, object]:
    claim = CheckClaim("example/demo", "head-2", "commit", "tests", "python-3.11")
    success = Evidence(claim, "run-2", 1, "completed", "success")
    failure = replace(success, conclusion="failure")
    stale = replace(success, subject=replace(claim, revision="head-1"))
    rerun = replace(success, attempt=2, state="in_progress", conclusion=None)
    other_run = replace(success, run_id="run-1")
    scenarios = (
        ("current_success", (success,), 1, True, False),
        ("current_failure", (failure,), 1, True, False),
        ("stale_revision", (stale,), 1, True, False),
        ("untrusted_local_report", (success,), 1, False, False),
        ("newer_attempt_in_progress", (success, rerun), 2, True, False),
        ("older_run_success", (other_run,), 1, True, False),
        ("missing_required_check", (), 1, True, False),
        ("dirty_worktree", (success,), 1, True, True),
        ("skipped_check", (replace(success, conclusion="skipped"),), 1, True, False),
    )
    rows = []
    for name, reports, attempt, simulated, dirty in scenarios:
        source = SyntheticFixtureSource(reports, "run-2", attempt) if simulated else None
        assessment = assess((claim,), (), reports, fixture_source=source, uncommitted_work=dirty)
        rows.append(
            {
                "scenario": name,
                "naive_any_success": naive_any_success(reports),
                "assessment": asdict(assessment),
            }
        )
    return {
        "experiment_version": 1,
        "trust": "SIMULATED fixture provenance only; no actual CI authentication",
        "scope": "Decision-model demonstration, not a product-value benchmark or task-completion proof",
        "comparator": "Intentionally weak any-success demonstration; not a model of GitHub CI",
        "scenarios": rows,
    }


def main() -> int:
    print(json.dumps(demo(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
