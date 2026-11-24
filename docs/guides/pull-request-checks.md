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
