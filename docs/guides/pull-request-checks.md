# Inspect checks from a pull request URL

The development-version `pr-checks` command takes a GitHub.com PR URL. No local
checkout, request file, workflow ID, or job ID is needed.

```bash
evagix pr-checks https://github.com/owner/repository/pull/123
```

The report separates checks for the PR head from checks for an available
test-merge revision. It shows outcome counts and details for failed, pending,
other, or unknown outcomes. Passed rows are hidden by default; use `--all` to
include them. Detail links let you inspect the provider's logs or workflow.

```bash
evagix pr-checks https://github.com/owner/repository/pull/123 --all
evagix pr-checks https://github.com/owner/repository/pull/123 --format json
evagix pr-checks https://github.com/owner/repository/pull/123 --format markdown
```

Use the PR's main URL, without `/files`, query parameters, or fragments. JSON
always includes every collected row and follows the packaged
`github-pr-checks.schema.json` preview contract. The command writes no files,
posts no comments, triggers no workflows, and executes no repository commands.

## Read the report

- **Head:** check runs and commit statuses reported for the PR's current head SHA.
- **Test merge:** a separate inventory only for an open, unmerged PR whose
  `mergeable` field is true and whose test-merge SHA is available. A conflicting
  or still-calculating merge is `unavailable`; closed PRs are `not_applicable`.
  The merge commit recorded after merging is not treated as a test-merge result.
- **Passed:** a reported successful check run or commit status.
- **Failed:** a reported failure/error, timeout, or action-required outcome.
- **Pending:** a reported queued, running, or waiting check/status.
- **Other outcomes:** skipped, neutral, cancelled, or stale checks. These are
  retained with their raw conclusion; cancellation does not prove that no work ran.
- **Unknown:** an unsupported or inconclusive combination of state and conclusion.

An empty inventory means no results were reported by those endpoints. It does
not mean tests passed or even started. Same-name check runs retain their separate
IDs and producers; the command never chooses a successful record over another
record with the same name. Missing app/creator information is shown as unknown.

**This is an advisory report, not a CI acceptance gate.** Required-check policy
is `unknown`, and `policy_decision` is `not_evaluated`. Even an all-passed report
does not establish that all required checks exist, ran, or tested the intended
checkout. GitHub rulesets, classic protection, expected check publishers, and
task requirements are not evaluated. No administrative token is requested to
infer such a policy. The advanced [verify-check](github-check-collection.md)
command remains available for an explicitly selected push job claim.

| Exit | Meaning |
| --- | --- |
| `0` | The report's endpoint inventories were collected completely, including any failed or pending checks. |
| `1` | The report contains an incomplete endpoint inventory; do not infer absent checks from it. |
| `2` | Invalid input, unsupported/malformed metadata, changed PR, or collection failure; stderr explains the error. |

Do not use exit `0` as a merge condition. Expected operational errors produce
no JSON report on stdout. Default repository scans and their exit codes are unchanged.

## Compare caller-supplied expectations

The optional `--expectations` flag compares the same collected inventory with a
small explicit list. It does not discover required checks or authenticate a
repository acceptance policy.

```bash
evagix pr-checks https://github.com/owner/repository/pull/123 --expectations checks.json
evagix pr-checks https://github.com/owner/repository/pull/123 --expectations checks.json --all --format json
```

Example file with **synthetic identifiers**, which must be replaced with the
repository and producer IDs you intend to inspect:

```json
{
  "schema_version": "1.0",
  "repository_id": 17,
  "checks": [
    {"revision": "head", "kind": "check_run", "name": "Tests", "producer_id": 42},
    {"revision": "test_merge", "kind": "commit_status", "name": "integration", "producer_id": 73}
  ]
}
```

For `check_run`, `producer_id` is the GitHub App ID; for `commit_status`, it is
the status creator's user ID. Names match exactly, including case and whitespace.
The repository ID must match the collected PR repository. These selectors do not
establish workflow identity, checkout provenance, or the authority of the person
who wrote the file. Keep expectations in a source you trust; a PR can otherwise
change its own list to omit checks.

The UTF-8 file is limited to 65,536 characters and 1-100 unique selectors. Unknown
fields, duplicate JSON keys, noninteger IDs, and malformed selectors are rejected
before any network request. The file is read as data; no commands or external
schema references are executed or fetched.

The comparison payload and rendered output are bounded to 8,000,000 UTF-8 bytes
each. Exceeding either limit returns exit `2` with a size-limit error instead of
truncating the report or emitting partial JSON. Narrow the expectations list if
many selectors retain the same candidate records.

Each expectation has an outcome:

| Outcome | Meaning |
| --- | --- |
| `passed`, `failed`, `pending` | One matching producer/name/kind was found in a complete revision inventory with that provider-reported outcome. |
| `missing` | A complete revision inventory contains no matching expected identity; same-name checks from another known producer do not satisfy it. |
| `unverified` | The revision is unavailable, inventory is incomplete, the producer is unknown, matching records are ambiguous, or the conclusion does not establish success/failure/pending. |

Skipped or neutral checks do not become a pass. Multiple records for the same
expected identity remain ambiguous even if one passed. The report retains same-kind,
same-name candidates to explain mismatches; its digest identifies the supplied
expectations, not their authority. Text hides passed expectations unless `--all`
is set, while JSON includes every expectation and its observed candidates.

This mode follows the separate preview `github-pr-expectations.schema.json`
contract. **Exit codes still describe collection:** a complete report returns
`0` even for missing, failed, or unverified expectations; incomplete collection
returns `1`; invalid input, repository mismatch, or collection failure returns
`2`. The comparison remains advisory, with `expectations_authority` set to
`caller_supplied` and `policy_decision` set to `not_evaluated`.

Without `--expectations`, the existing report, JSON schema, and exits are unchanged.

## Markdown summaries

`--format markdown` renders either report for a GitHub job summary. `--all`
includes passed rows; otherwise the counts include them but their details are
hidden. Base/head revisions, test-merge availability, collection completeness,
and advisory boundaries remain visible. An empty or incomplete inventory does
not establish test success.

Provider text is redacted before rendering as literal code, including names
containing Markdown, HTML, or mentions. Control and direction-formatting
characters are escaped; ordinary Arabic remains readable. HTTPS detail links
use fixed labels and encoded delimiters. Unsafe or redacted URLs are displayed
as text rather than active links.

Markdown is limited to 450,000 UTF-8 bytes per report. A larger report returns
exit `2` with an error on stderr and no partial stdout; use JSON for the complete
data. This display limit does not change evidence completeness or JSON limits.

For a combined report with reference findings, use the
[optional PR summary recipe](pr-review-summary.md). It matches both reports to
the same explicit base/head pair instead of concatenating unrelated snapshots.

## Network access and permissions

The command explicitly contacts `https://api.github.com`. Public data is read
anonymously when available. For private or restricted data, provide
`EVAGIX_GITHUB_TOKEN` through the environment or a CI secret manager, with access
to the selected base repository and read access for metadata, pull requests,
checks, and commit statuses. It does not use GitHub CLI credentials, read `.env`,
accept a token argument, or request links returned by check providers.

This PR adapter pins REST version `2022-11-28`, which retains `merge_commit_sha`
and is supported by GitHub until March 10, 2028. Version `2026-03-10` removed that
field. This is an explicit adapter version, not a silent fallback; the existing
push-job collector remains on `2026-03-10`. Upgrade the PR adapter's merge-revision
discovery before that support deadline.

The [collector's fixed-origin TLS, redirect/proxy restrictions, credential
handling, and byte/time limits](github-check-collection.md#authentication-and-network-boundary)
also apply here. PR collection shares one budget across all endpoints: at most
15 requests, 2 MB per response body, and 8 MB total. The 30-second elapsed budget
and 10-second socket timeout are not a hard DNS/wall-clock deadline.

Each of the four possible streams (head/test-merge, check runs/statuses) is limited
to three pages of 100 records. A remaining next page or missing records marks
the inventory incomplete. Totals changing between pages, duplicate check IDs or
status contexts, foreign SHA/repository metadata, and mismatched pagination links
are rejected. The PR is reread after collection; changes to its head, base, merge
state, or revision invalidate the report.

## Provider boundaries

Check runs use GitHub's `filter=latest`, without filtering out pending checks.
Every returned execution is retained. This is not a reconstruction of the latest
Actions attempt for every workflow; GitHub limits the endpoint to the latest
1,000 check suites. Commit statuses use the combined `/status` endpoint, which
returns the latest status for each context; each page's SHA and repository ID
are checked. The command does not read the historical `/statuses` endpoint.

For fork PRs, both inventories are queried in the base repository. An empty
`pull_requests` array on a check does not remove it from the SHA-scoped inventory.
These are provider associations, not proof that a check ran exclusively for this
PR. A rerequest can also precede a provider updating its check run. PR stability
does not make check pagination atomic: the report describes the responses observed
during collection and can become stale afterward.

Output uses central secret redaction. Terminal control and direction-formatting
characters are escaped while ordinary Arabic remains readable. Unsafe detail
URLs are omitted; remaining provider URLs are displayed, never followed with the token.

## Provider references

- [Pull request and merge-SHA semantics](https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request)
- [Check runs for a revision](https://docs.github.com/en/rest/checks/runs#list-check-runs-for-a-git-reference)
- [Combined commit statuses](https://docs.github.com/en/rest/commits/statuses#get-the-combined-status-for-a-specific-reference)
- [Required status checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)
- [Supported REST versions](https://docs.github.com/en/rest/about-the-rest-api/api-versions#supported-api-versions)
- [2026 REST breaking changes](https://docs.github.com/en/rest/about-the-rest-api/breaking-changes#version-2026-03-10)
