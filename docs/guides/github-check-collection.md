# Collecting a GitHub check result

For a report from a PR URL without preparing request JSON, start with
[pr-checks](pull-request-checks.md). The command below is the advanced interface
for an explicitly selected push job claim.

`verify-check` is an opt-in preview command in the development version. It asks
GitHub.com whether a specific job execution reports success for the repository,
revision, workflow, run, and attempt selected by the caller. Existing repository
scans remain offline; this command makes HTTPS requests and runs no project code.

## Select the check

Save a UTF-8 request file using the [check contract](check-verification-contract.md).
The values below are synthetic: replace every identifier and the revision with
the intended check's values before running the command.

```json
{
  "schema_version": "1.0",
  "kind": "check_succeeded",
  "subject": {
    "repository": "github:repository:10",
    "revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "subject_kind": "commit",
    "workflow": "github-actions:workflow:30",
    "job": "github-actions:job:40"
  },
  "run_id": "20",
  "attempt": 2
}
```

Use numeric IDs from GitHub's repository, workflow-run, and attempt-specific jobs
API responses. Repository, workflow, job, and run IDs must be positive canonical
decimal values no greater than `2**63 - 1`; the attempt uses the check contract's
bound. Display names are not identifiers. A job ID identifies one execution and
changes on rerun. The request file is limited to 65,536 characters; ambiguous JSON,
duplicate keys, non-finite numbers, and unsupported fields are rejected.

```bash
evagix verify-check --request check-request.json --github-repo owner/repository
evagix verify-check --request check-request.json --github-repo owner/repository --format json
```

Only `push` runs whose head repository matches the requested repository are
supported. Select the **current attempt of that run** explicitly. Earlier attempts,
PR/test-merge runs, and other event types are unsupported. The command does not
discover required checks, choose a successful job, resolve matrix membership,
combine old jobs with partial reruns, or verify that a selected run is the latest
run on a branch. Selection and required-check policy remain the caller's responsibility.

## Authentication and network boundary

Public metadata can be collected anonymously, subject to GitHub's rate limits.
For authenticated access, set `EVAGIX_GITHUB_TOKEN` through your environment or CI
secret manager. Use repository metadata and Actions read permissions for the
selected repository. There is no token command-line flag. The collector does not
read `.env` files, Git credentials, GitHub CLI configuration, or other token variables.

The only destination is `https://api.github.com`, using REST API version
`2026-03-10` and certificate/hostname verification. Redirects and environment/system
proxies are disabled. A renamed repository must be supplied by its current name;
GitHub Enterprise hosts and proxy-dependent networks are not supported in this
preview. Repository names and numeric IDs enter request URLs; the request JSON,
repository files, and local code are not uploaded. An optional token is sent only
as an authorization header to that fixed origin.

Collection uses 6–15 requests: repository metadata, the run, its selected attempt,
up to ten jobs pages, and final run/attempt checks. Limits are 100 jobs per page,
1,000 collected jobs, 2 MB per response body, and 8 MB in total. The client requests
uncompressed JSON and does not retry automatically. Missing pages or the page
limit produce an incomplete inventory; malformed responses, identity conflicts,
and request/byte/time limits produce an operational error.

A 30-second elapsed budget is checked between requests and body chunks, with at
most 10 seconds per socket operation. This is **not a hard wall-clock deadline**:
an in-flight operation can cross the budget, and OS DNS resolution can outlast a
socket timeout. Use an external process timeout when a strict deadline is required.

## What the result establishes

The collector checks repository identity and compares the run and attempt before
and after reading jobs. A changed attempt, revision, workflow, state, or conclusion
is rejected. A completed, unchanged run with all reported jobs is required for a
complete inventory. These reads detect observed changes; GitHub does not provide
an atomic snapshot across the endpoints.

The result uses the existing check schema. `source_verification: caller_verified`
means the evaluator received a digest-bound assessment from this live collector;
the verifier is `github.com-rest:2026-03-10:tls`. The digest covers normalized
evidence, not raw HTTP bytes. It is neither a signature nor a portable attestation.
Importing the same JSON from a file with the
[offline importer](github-actions-evidence.md) does not authenticate it.

| Exit | Meaning |
| --- | --- |
| `0` | The selected job's reported success is supported by matching, complete, source-assessed evidence. |
| `1` | The result is `contradicted` or `unverified`; inspect `reason` and the separate evidence dimensions. |
| `2` | Invalid request/usage, unsupported metadata, or collection/evaluation failure. |

Text output includes the result, reason, selected IDs, and evidence dimensions.
`--format json` emits the unchanged `CheckResult` report. Expected operational
errors go to stderr with no JSON result on stdout. No result authorizes merging:
`policy_decision` remains `not_evaluated`.

A completed `failure` contradicts the selected claim. `skipped`, `neutral`,
`cancelled`, `timed_out`, missing conclusions, missing jobs, and incomplete
inventories do not support success. Other jobs can fail while the selected job
succeeds; evaluate each required job separately.

**Provider metadata is not execution provenance.** A workflow can check out another
revision, tolerate a failing step, or skip the tests you intended. This command
does not inspect checkout steps, authenticate required-check policy, prove test
quality, cover dirty working-tree changes, or establish task completion. A request
chosen by the same agent being reviewed is not an independently approved policy.

## Python integration

`collect_actions_attempt(repository, *, scope, token=None)` from
`evagix.verification.github_collection` returns `CollectedEvidence` with `batch`
and `assessment`. Pass both to `evaluate_check` with the original selected request.
The supplied scope's `pagination_complete` is ignored: the collector derives
completeness from its own reads. `GitHubCollectionError.code` classifies expected
collection failures; its message contains no credential or response contents.
Existing offline normalization and evaluation APIs retain their behavior.

## Provider references

- [Workflow run attempts](https://docs.github.com/en/rest/actions/workflow-runs#get-a-workflow-run-attempt)
- [Attempt jobs](https://docs.github.com/en/rest/actions/workflow-jobs#list-jobs-for-a-workflow-run-attempt)
- [REST API versions](https://docs.github.com/en/rest/about-the-rest-api/api-versions)
- [REST pagination](https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api)
- [Rerun behavior](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)
- [Checkout inputs](https://github.com/actions/checkout#usage)
