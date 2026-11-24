# Importing GitHub Actions evidence

This preview Python API normalizes an already collected GitHub.com Actions
snapshot into the [check verification contract](check-verification-contract.md).
It performs no network access, authentication, file access, or command execution.
Existing CLI commands, schemas, and default scans are unchanged.

An imported batch has no `SourceAssessment`. Evaluating it without a separately
verified source returns `unverified`, even when a job reports `success`.

For explicit network collection, see [Collecting a GitHub check result](github-check-collection.md).
That separate adapter does not change this importer's offline trust boundary.

## Supported snapshot

Import `GitHubActionsScope` and `normalize_actions_attempt` from
`evagix.verification.github_actions`. The function accepts:

- A JSON-decoded workflow run object.
- A tuple of JSON-decoded pages from the **attempt-specific** jobs endpoint:
  `/repos/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt_number}/jobs`.
- A declared `GitHubActionsScope(repository_id, run_id, attempt,
  pagination_complete=False)`, supplied separately from those objects.

Only `push` runs with the same repository and head repository are supported.
Other events, including `pull_request`, `pull_request_target`, and `merge_group`,
are rejected. This preview does not infer a test merge revision.

The run must include `id`, `repository.id`, `head_repository.id`, `workflow_id`,
`head_sha`, `run_attempt`, and `event`. Both repository IDs, the run ID, and the
attempt must match the declared scope. `head_sha` must be a full lowercase Git
object ID accepted by the existing contract. Missing metadata is not inferred
from a requested claim, a display name, or a timestamp.

Each job requires `id`, `run_id`, `head_sha`, `status`, and `conclusion`.
Its run ID and revision must match the run. If `run_attempt` is present it must
match the scope; otherwise the explicitly declared attempt endpoint supplies it.
The run's own `run_attempt` is mandatory for this importer, although GitHub's API
schema does not require it. An absent attempt never defaults to `1`.

Supported job statuses are `queued`, `in_progress`, and `completed`. A completed
job may have a null conclusion or `success`, `failure`, `skipped`, `neutral`,
`cancelled`, or `timed_out`. Other statuses and conclusions are rejected, including
GitHub's `waiting`, `requested`, `pending`, and `action_required`. Unsupported data
raises `ContractError`; jobs are never silently dropped or coerced to success.

## Identity and completeness

The importer uses numeric provider IDs, independently of names and URLs:

| Contract field | Imported value |
| --- | --- |
| Repository | `github:repository:<repository_id>` |
| Workflow | `github-actions:workflow:<workflow_id>` |
| Job and record ID | `github-actions:job:<job_id>` |
| Run | Decimal run ID |
| Subject kind | `commit` |
| Source | `github-actions:repository:<repository_id>:run:<run_id>:attempt:<attempt>` |

A job ID identifies one job execution, not a reusable logical job or matrix
configuration. The caller must select the required execution from trusted policy
and collection logic. Two jobs named `tests` remain distinct. This API does not
map workflow names to IDs, resolve required matrix members, select the latest
run, or combine earlier jobs with a partial rerun.

IDs must be positive integers no greater than `2**63 - 1`. Attempts use the
existing contract's bound. Boolean, floating-point, and string IDs are rejected.

Each page must contain a nonnegative integer `total_count` and a `jobs` list.
All pages must report the same total. Duplicate job IDs and a collected count
greater than the reported total are errors. The import is bounded to ten pages,
100 jobs per page, and 1,000 records. Oversized inputs are rejected, not truncated.
An inventory reporting more jobs than were supplied may still be imported as
incomplete within those input limits.

`complete` is true only when the caller declares `pagination_complete=True`, at
least one page exists, and the unique job count equals `total_count`. No pages
means incomplete; an explicit zero-job page may describe a complete empty
inventory. Records are sorted deterministically, and input objects are unchanged.

Completeness describes that declared attempt snapshot, not freshness, job
completion, all task requirements, or independently verified pagination. The
collector must follow GitHub pagination, check the endpoint and host, and handle
concurrent run updates before it can assess the source.

## Trust and execution limits

`head_sha` associates a run or job with a revision in provider metadata. It does
**not** establish which repository or revision a workflow actually checked out,
which tests ran, or whether a step failure was tolerated. A workflow can configure
another checkout or use `continue-on-error`. Even authenticated API metadata would
not by itself prove that tests passed on the claimed code.

The importer intentionally ignores display names, steps, URLs, and extra fields,
including trust-looking fields such as `verified`. They do not enter the batch
or its digest. Validation errors never include supplied values. The batch digest
binds the normalized contract fields; it is not a hash of the original HTTP
response and does not authenticate that response.

The optional live collector authenticates the source of GitHub metadata, with the
execution limits above. Do not create a verified assessment merely because this
import succeeds. Offline data may be internally consistent and still be fabricated
or stale.

## Python example

The following inputs are synthetic snapshots, not authenticated execution evidence:

```python
from evagix.verification import CheckRequest, CheckSubject, evaluate_check
from evagix.verification.github_actions import (
    GitHubActionsScope, normalize_actions_attempt,
)

revision = "a" * 40
run = {
    "id": 20, "repository": {"id": 10}, "head_repository": {"id": 10},
    "workflow_id": 30, "head_sha": revision, "run_attempt": 2, "event": "push",
}
pages = ({"total_count": 1, "jobs": [{
    "id": 40, "run_id": 20, "head_sha": revision, "run_attempt": 2,
    "status": "completed", "conclusion": "success",
}]},)
scope = GitHubActionsScope(10, 20, 2, pagination_complete=True)
batch = normalize_actions_attempt(run, pages, scope=scope)

# In an integration, selection must come from trusted policy and collection logic.
subject = CheckSubject(
    "github:repository:10", revision, "commit",
    "github-actions:workflow:30", "github-actions:job:40",
)
result = evaluate_check(CheckRequest(subject, "20", 2), batch)
assert result.evidence_match == "match"
assert result.completeness == "complete"
assert result.condition == "unverified"
assert result.reason == "source_unverified"
```

## Provider references

- [Workflow runs API](https://docs.github.com/en/rest/actions/workflow-runs#get-a-workflow-run)
- [Attempt-specific workflow jobs API](https://docs.github.com/en/rest/actions/workflow-jobs#list-jobs-for-a-workflow-run-attempt)
- [REST pagination](https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api)
- [Rerun behavior](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)
- [Checkout inputs](https://github.com/actions/checkout#usage)
- [Step outcomes and conclusions](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#steps-context)
