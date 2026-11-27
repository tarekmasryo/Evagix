# Combine advisory PR reports in a job summary

The preview `evagix.pr_summary` module combines observed PR checks,
deleted-file references, and deleted-script instructions in one advisory Markdown
report, without requiring an expectations file. An explicit file enables
expected-check comparison. An optional local pytest JUnit file adds a separate,
unverified test-report section. Alternatively, an explicit artifact ZIP can be
compared with GitHub run metadata. It collects the PR check inventory once and requires that its
base and head commits match the explicit commits supplied by the caller. Both
repository inspections use that same pair. Existing standalone commands, JSON
schemas, and exit-code meanings are unchanged.

This module is included in the unpublished [0.2.0a1 preview](preview-release.md),
and is not included in the published `0.1.2` release. For local evaluation, use
the preview wheel. The CI recipe below uses a separately reviewed commit
containing the feature. Do not install the inspected PR's code as the
verification tool.

## Local invocation

Run from outside the inspected checkout using an independently installed Evagix:

```bash
python -I -m evagix.pr_summary https://github.com/owner/repository/pull/123 \
  --repo /path/to/checkout \
  --base FULL_BASE_COMMIT \
  --head FULL_HEAD_COMMIT
```

Replace the commit placeholders with full lowercase commit IDs. Branch names,
abbreviations, and tag-object IDs are rejected. Both commits and their required
Git objects must already exist locally; the module never fetches them.

Without `--expectations`, the summary reports observed checks and explicitly
leaves required-check coverage unknown. It does not infer required checks from
CI configuration or discover an expectations file automatically. An empty
inventory is not evidence that tests ran or that no checks are required.

To compare an explicit list, add `--expectations .github/evagix-checks.json`.
This optional argument is a repository-relative Git path, read from the requested
base commit. It must identify a regular tracked file containing valid UTF-8 JSON no
larger than 65,536 bytes, following the
[expectations format](pull-request-checks.md#compare-caller-supplied-expectations).
Edits or deletions to that file in the PR or working tree do not replace the base
version. A missing, nonregular, oversized, or malformed base file fails before
network collection; it does not fall back to inventory mode. The supplied base
remains a caller-selected snapshot, not
proof that a protected acceptance policy authorized its contents.

Only `EVAGIX_GITHUB_TOKEN` supplies optional authentication. The module uses the
existing [GitHub collector boundary](github-check-collection.md#authentication-and-network-boundary).
It does not read credential files or infer credentials from GitHub CLI.

## Optional local pytest JUnit report

Add `--junit-report /path/to/results.xml` to the invocation above to include one
explicitly selected local report. Relative paths use the caller's working
directory, not `--repo`. The option may appear only once. No report is discovered,
generated, downloaded or read from Git automatically. Without this option, output
and exit behavior are unchanged.

The section reuses the bounded [local pytest reader](local-junit-reports.md).
It shows case-row counts, reported failures/errors/skips and collection issues;
passed rows are hidden. Failure bodies, logs, properties and source paths are
omitted. Names remain untrusted display text and are redacted and escaped.

The local report is **not associated with a GitHub job or either requested
commit**. Its source remains unverified, revision binding and run completion
remain unknown, and no merge policy is evaluated. A SHA or timestamp inside XML
does not change that. GitHub check outcomes and local test outcomes remain
separate; one cannot validate or override the other.

A consistent report with failures, only skipped tests or zero tests does not
fail collection. An incomplete report is displayed with the other sections and
makes the combined exit status `1`. Reader errors, including unreadable input,
detected malformed XML and rejected unsafe declarations, return `2`, with a
diagnostic on stderr and no combined stdout, before GitHub collection.
Unsupported structure or resource limits can stop inspection before XML
well-formedness is established; these remain incomplete, never a clean result.
An oversized rendered section or summary also returns `2` without partial output.

This option is under development after the prepared `0.2.0a1` preview. Evagix's
own CI reporting job attaches a minimized report from `Quality gates`, as
described below. The optional integration recipe later in this guide does not
collect or attach JUnit automatically.

## Optional GitHub JUnit association

Select an original local artifact ZIP to include the
[GitHub association check](github-junit-association.md) in the same report:

```bash
python -I -m evagix.pr_summary https://github.com/owner/repository/pull/123 \
  --repo /path/to/checkout --base FULL_BASE_COMMIT --head FULL_HEAD_COMMIT \
  --junit-archive /path/to/original-artifact.zip \
  --junit-run-id 456 --junit-attempt 1 --junit-artifact-id 789
```

The run and artifact IDs belong to the PR's base repository. The expected provider
revision is always the explicit `--head`; it cannot be overridden with an older
revision. The original ZIP must already exist locally; nothing is downloaded,
uploaded, extracted or executed. Relative paths use the caller's working directory.
The default sole member is `evagix-quality-junit.xml`; use `--junit-member results.xml`
for a different supported member. All four required options must appear together
and once. The member option may appear once and requires an archive. This mode
cannot be combined with `--junit-report`.

After local committed inputs and any explicit base expectations are validated,
the archive is inspected and associated, then the existing PR collector
checks its before/after snapshot against the requested base and head. The summary
compares the run's numeric repository and head-repository IDs with the observed PR
identities, including forks. A missing head repository leaves that comparison
unknown. XML counts are omitted when repository identity cannot be matched; the
remaining sections and explicit linkage diagnostics stay visible.

The section reports archive/run linkage, provider revision matching, selected
attempt currentness, run/attempt outcomes and XML counters separately. Failed,
skipped-only or empty XML does not fail collection. A complete matching association
does not override failed checks, broken references or an incomplete inspection.
`current` means latest attempt **within the selected run**, not latest workflow or
PR run. The producing attempt, job, actual tested checkout, full-suite execution
and task completion remain unverified. A matching SHA does not prove that a run
was triggered by this PR. Test names and free-text failure details are omitted.

| Exit | Additional meaning when an archive is selected |
| --- | --- |
| `0` | Existing inspections are complete, archive/run/revision and repository identities match, and the selected attempt is current. Test success and merge readiness are not evaluated. |
| `1` | Any inspection is incomplete, or the association is stale, mismatched or has an unknown PR repository identity. The available sections remain visible. |
| `2` | Invalid option combinations, unreadable/unsafe/corrupt input, provider errors, changed PR revisions or rendering errors. No combined stdout is emitted. |

The local XML reader and summaries without either JUnit option retain their
behavior. Existing JSON schemas are unchanged. This development-preview option
does not update the tool pin or enable archive association in Evagix's automatic
CI job; that job continues to use the local XML transfer described below.

## Interpret the result

The repository sections inspect committed root `README.md` and `AGENTS.md`.
The [script section](deleted-scripts.md) checks supported literal commands,
assuming a repository-root working directory. It does not execute scripts,
prove execution failure, or infer replacement paths. Editing an uncommitted
instruction does not change the report.

| Exit | Meaning |
| --- | --- |
| `0` | The three existing inspections and any selected JUnit input completed within their stated scopes, with matching/current artifact linkage when requested. Failed checks/tests, missing expected checks, broken links, or stale script instructions can still be present. |
| `1` | At least one selected report is incomplete, or an optional artifact association is stale, mismatched or has unknown PR identity; all sections describe their available evidence. |
| `2` | Invalid input (including JUnit reader errors), unavailable local objects, collection failure, changed PR revisions, comparison failure, or output limit. No combined report is written to stdout. |

The summary is advisory. It does not prove test execution, enforce required-check
policy, approve merging, or validate all task requirements. With an expectations
file, a missing check means that it was not observed in the collected snapshot;
it may not have started yet.
Unavailable test-merge data and insufficient API permissions must not be
interpreted as missing checks. Recollect after pending checks finish.

Passed rows are hidden in the combined summary. To inspect them, use the
standalone `evagix pr-checks PR_URL --all --format markdown` command.

Each Markdown section is bounded to 450,000 UTF-8 bytes. The combined summary is
bounded to 950,000 bytes after redaction, below GitHub's per-step summary limit.
Excess output is rejected rather than silently truncated. Use the individual
JSON commands when a complete machine-readable report is needed.

## Evagix's own pull-request workflow

The repository's `CI` workflow includes an `Evagix advisory PR review` job.
It waits for quality, platform tests, self-governance, build, and artifact-install
jobs, including failures or skipped dependencies. It runs only on `pull_request`
events and does not start after workflow cancellation. Push and release gates
are unchanged.

The job installs the tool from reviewed commit
`76d423ed45aa43240899c9198ad61be9aa296eb7`, using that commit's build constraints
in an isolated environment. Updating this pin is a separate reviewed change;
the tool and its constraints are not loaded from the inspected checkout. The PR's head
checkout is read only as Git data by the installed tool, outside the checkout's
import path. The workflow itself is still PR-controlled, so this is not a trusted
policy-enforcement boundary.

The pinned version reports checks, deleted-file references, deleted-script
instructions and an optional JUnit section. The three existing sections use the
requested base and head commits; the JUnit section retains unknown revision
binding and run completion. Incomplete inspection makes the review incomplete.

The `Quality gates` job writes pytest XML to the runner's temporary directory,
without changing pytest's exit status or the coverage threshold. On PR runs,
`scripts/prepare_ci_junit.py` reads that file with the bounded reader. Only a
complete supported report is converted into a transfer file: suite counters and
case outcome markers are retained, while **all original suite/test names,
class names, messages, logs, properties, paths and other metadata are omitted**.
Labels such as `suite-1` and `case-2` are ordinal placeholders, not test names.
Failures, skips and zero-test reports remain distinguishable. The raw XML is
never selected for upload by this workflow.

One minimized XML artifact is retained for one day. Its name includes the
workflow attempt, and the reporting job downloads it only from the current run
and matching attempt. Rerunning only the reporting job does not reuse an artifact
from an earlier attempt: rerun `Quality gates` and the dependent review to get a
new transfer. Original names and failure details remain in the existing test-job
logs; the summary provides counts and ordinal rows only. This is a transfer
association, not authentication of the report or proof of the tested revision.
The other twelve platform jobs do not contribute JUnit files in this integration.

Incomplete or rejected source reports are not converted into replacement XML.
Their fixed collection state is passed separately. A missing, failed or stale
transfer leaves the other advisory sections visible with a JUnit-unavailable
notice and exit `1`; an incomplete source is identified explicitly. A downloaded
file is still untrusted and is reparsed by the independently installed tool.
Detected malformed XML or a rendering/collection error retains the module's
existing exit `2` and unavailable-review behavior. A failed upload/download step
also remains a failed workflow step. Cancellation or runner loss may prevent a
summary altogether.

Open **Actions → CI → Summary** to read the report. No expectations file,
repository variable or PR comment is required. The minimized JUnit artifact is
the only additional uploaded file; it contains no original free-text fields.
The job has read-only permissions and uses the workflow token only for metadata
collection and checkout; no personal token or repository secret is required.

Failed observed checks, broken links, and stale script instructions do not fail
this advisory job. Reported JUnit failures/skips do not change that behavior;
the original test jobs retain their own results. Incomplete inspection or an operational error does fail the
job (and the workflow run), so
an unavailable review is not presented as a clean result. Existing jobs retain
their own results. Do not make the advisory job a required merge check.

Tool installation or checkout failure produces an unavailable-review summary
when the final step can run. A cancelled or timed-out runner cannot be guaranteed
to publish a summary. Fork approval and token restrictions still apply; there is
no privileged fallback. Other workflows may remain pending when this job runs.

## Optional job for another pull-request workflow

The following job is a recipe to add to a workflow that already uses
`pull_request`. Replace `tests` in `needs` with the test job IDs from that
workflow. It runs after those jobs finish, including when they fail; unrelated
provider checks can still be pending.

Before enabling the job, set the repository variable `EVAGIX_TOOL_SHA` to a
reviewed full commit ID from `tarekmasryo/Evagix` containing the optional-file
behavior documented here. A missing or invalid value fails installation. Do not
use the inspected PR's head, a moving branch, or `v0.1.2`.

The recipe needs no expectations file. To enable comparison, review the file
into the base branch first and add `--expectations .github/evagix-checks.json` to
the summary invocation. Keep this reporting job out of its own expectations
list: it cannot observe itself as completed while generating the report.

```yaml
jobs:
  evagix-review:
    name: Evagix advisory PR review
    needs: [tests]
    if: ${{ always() && !cancelled() && github.event_name == 'pull_request' }}
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: read
      pull-requests: read
      checks: read
      statuses: read
    steps:
      - uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0
        with:
          python-version: '3.11'

      - name: Install reviewed verification tool
        working-directory: ${{ runner.temp }}
        env:
          EVAGIX_TOOL_SHA: ${{ vars.EVAGIX_TOOL_SHA }}
        run: |
          if [[ ! "$EVAGIX_TOOL_SHA" =~ ^[0-9a-f]{40}$ ]]; then
            echo 'Set EVAGIX_TOOL_SHA to a reviewed full tool commit.' >&2
            exit 2
          fi
          python -I -m venv "$RUNNER_TEMP/evagix-summary-env"
          "$RUNNER_TEMP/evagix-summary-env/bin/python" -I -m pip install \
            "evagix @ git+https://github.com/tarekmasryo/Evagix.git@$EVAGIX_TOOL_SHA"

      - name: Fetch inspected commits as data
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          fetch-depth: 0
          persist-credentials: false
          submodules: false
          lfs: false
          path: inspected

      - name: Publish advisory review summary
        if: ${{ always() }}
        working-directory: ${{ runner.temp }}
        env:
          PR_URL: https://github.com/${{ github.repository }}/pull/${{ github.event.pull_request.number }}
          BASE_SHA: ${{ github.event.pull_request.base.sha }}
          HEAD_SHA: ${{ github.event.pull_request.head.sha }}
          EVAGIX_GITHUB_TOKEN: ${{ github.token }}
        run: |
          report="$RUNNER_TEMP/evagix-pr-review.md"
          set +e
          "$RUNNER_TEMP/evagix-summary-env/bin/python" -I -m evagix.pr_summary \
            "$PR_URL" --repo "$GITHUB_WORKSPACE/inspected" \
            --base "$BASE_SHA" --head "$HEAD_SHA" > "$report"
          review_status=$?
          set -e
          if [[ ( "$review_status" == 0 || "$review_status" == 1 ) && -s "$report" ]]; then
            cat "$report" >> "$GITHUB_STEP_SUMMARY"
            exit "$review_status"
          fi
          printf '%s\n' '## Evagix review unavailable' '' \
            'The review could not inspect matching committed inputs and GitHub evidence. See the operational error; no clean result is implied.' \
            >> "$GITHUB_STEP_SUMMARY"
          exit 2
```

The checkout is inspected as Git data. The job neither installs dependencies from
it nor executes its scripts, tests, hooks, or configuration. Python isolation and
the temporary virtual environment keep checkout modules out of the tool's import
path. The summary is written directly to GitHub's per-step file; it is not copied
to the command log or posted as a PR comment. No additional artifact is uploaded.

This recipe remains advisory: a PR-controlled workflow is not a trusted
enforcement boundary. Taking expectations from the base commit does not prevent a
PR from editing the workflow itself. Do not use the job's successful exit as a
merge-approval rule. Existing `init-ci` readiness and integrity gates are unchanged.

Fork approval rules, token permissions, or missing local objects can prevent a
report. Those conditions produce an unavailable review, not a passing review or
an assertion that required checks are missing. If the PR base or head changes
after the triggering event, the module refuses to combine results for different
snapshots. Run a new review with the current explicit revisions.

The recipe is an optional integration example for other repositories. Local
shell tests and review do not establish hosted-workflow validation; confirm the
report in an actual run after enabling the job.

## References

- [GitHub pull-request event and merge-revision semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request)
- [Job summaries and their per-step size limit](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#step-isolation-and-limits)
- [Risks of untrusted code checkout](https://docs.github.com/en/actions/reference/security/secure-use#mitigating-the-risks-of-untrusted-code-checkout)
- [Deleted-file reference scope](deleted-references.md)
  and [GitHub check comparison scope](pull-request-checks.md)
