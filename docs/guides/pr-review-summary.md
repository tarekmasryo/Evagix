# Combine advisory PR reports in a job summary

The preview `evagix.pr_summary` module combines observed PR checks,
deleted-file references, deleted-script instructions, supported test changes,
and lower literal CI coverage declarations
in one advisory Markdown report, without requiring an expectations file. An explicit file enables
expected-check comparison. An optional local pytest JUnit file adds a separate,
unverified test-report section. Alternatively, an explicit artifact ZIP can be
compared with GitHub run metadata. It collects the PR check inventory once and requires that its
base and head commits match the explicit commits supplied by the caller. All
repository inspections use that same pair. Existing standalone commands, JSON
schemas, and exit-code meanings are unchanged.

This module is included in the unpublished [0.2.0a1 preview](preview-release.md),
and is not included in the published `0.1.2` release. For local evaluation, use
the preview wheel. The CI recipe below uses a separately reviewed commit
containing the feature. Do not install the inspected PR's code as the
verification tool.

The test-change section is under development after the prepared preview. Use a
reviewed build containing this addition to evaluate it. Evagix's automatic CI
report includes the section through the reviewed tool pin described below.

The coverage-declaration section is also under development after the prepared
preview. It is included when running a reviewed build containing this addition;
the automatic CI tool pin does not yet include it.

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
behavior. Existing JSON schemas are unchanged. Evagix's automatic CI job uses
this development-preview association for its minimized transfer, as described below.

## Interpret the result

The reference and script sections inspect committed root `README.md` and `AGENTS.md`.
The [script section](deleted-scripts.md) checks supported literal commands,
assuming a repository-root working directory. It does not execute scripts,
prove execution failure, or infer replacement paths. Editing an uncommitted
instruction does not change the report.

The [test-change section](test-changes.md) compares the unique merge base with
the requested head. It reports removed Python test-file paths and supported
literal unconditional `pytest.mark.skip` additions on existing named tests.
Git rename candidates appear separately; conditional skips, new test names and
working-tree changes remain outside the supported comparison. No tests are
imported, collected or executed. A removal or skip may be intentional; the section
does not establish lost coverage, weaker tests or a failed acceptance criterion.

Incomplete test inspection, including unsupported or unreadable changed source,
keeps the other sections visible and returns `1`. A complete JUnit report or
successful GitHub check cannot override that limitation. Fatal inspection or
rendering errors return `2` without partial combined output.

The [coverage-declaration section](coverage-thresholds.md) compares the same
merge base and requested head for lower literal `pytest-cov` thresholds in
changed existing GitHub Actions workflows. Matching uses the workflow path,
job and a unique step identity. Increases and unchanged values produce no
reduction finding. Missing, dynamic or ambiguous declarations remain unresolved;
they are not assigned a threshold of zero. Effective coverage and test execution
are not evaluated.

Coverage findings remain advisory, including when GitHub checks or JUnit cases
report failures. Incomplete coverage inspection keeps the other sections visible
and returns `1`; a passing check or complete JUnit report cannot override it.
Operational or rendering failures return `2` without partial output.

| Exit | Meaning |
| --- | --- |
| `0` | All five inspections and any selected JUnit input completed within their stated scopes, with matching/current artifact linkage when requested. Failed checks/tests, missing expected checks, broken links, stale script instructions, removed test-file paths, added skips or lower coverage declarations can still be present. |
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
`69701c2ee29fa4e97f630bf430c714110cbe74f0`, using that commit's build constraints
in an isolated environment. Updating this pin is a separate reviewed change;
the tool and its constraints are not loaded from the inspected checkout. The PR's head
checkout is read only as Git data by the installed tool, outside the checkout's
import path. The workflow itself is still PR-controlled, so this is not a trusted
policy-enforcement boundary.

The pinned version reports checks, deleted-file references, deleted-script
instructions, supported test changes and a GitHub-associated JUnit section when a
usable transfer is available. The four inspections use the requested base and head commits;
the JUnit section compares the artifact with the current run, selected attempt
and PR identities. Actual tested-code and producing-attempt provenance remain
unknown. Incomplete inspection makes the review incomplete.

This pin excludes the newer coverage-declaration section. Enabling it in the
automatic report requires a separate reviewed tool-pin update.

The `Quality gates` job writes pytest XML to the runner's temporary directory,
without changing pytest's exit status or the coverage threshold. On PR runs,
`scripts/prepare_ci_junit.py` reads that file with the bounded reader. Only a
complete supported report is converted into a transfer file: suite counters and
case outcome markers are retained, while **all original suite/test names,
class names, messages, logs, properties, paths and other metadata are omitted**.
Labels such as `suite-1` and `case-2` are ordinal placeholders, not test names.
Failures, skips and zero-test reports remain distinguishable. The raw XML is
never selected for upload by this workflow.

One minimized XML artifact is retained for one day. The upload step exposes its
artifact ID; the reporting job downloads that explicit ID from the current run
only when the producer's attempt matches the workflow attempt. It retains the
original ZIP without extracting or recompressing it, preserving the bytes needed
for digest comparison. Exactly one regular, non-symlink downloaded file is passed
to the installed tool, together with the run ID, attempt and artifact ID. Archive
size and contents are checked by the bounded reader.

The tool compares the archive digest and size with GitHub metadata, its run and
repository identities with the PR, and the provider revision with the requested
head. It also checks selected-attempt currentness and metadata stability. Missing
metadata, mismatches and stale evidence are not treated as a complete association.
The workflow is still running while this job collects evidence; neither its
eventual conclusion nor the actual tested checkout is inferred.

Rerunning only the reporting job does not reuse an artifact from an earlier
attempt: rerun `Quality gates` and the dependent review to get a new transfer.
The attempt guard and artifact name are not proof of which attempt produced the
XML. Original names and failure details remain in the existing test-job logs.
The summary provides aggregate counts and association diagnostics; ordinal
labels remain only in the minimized artifact. The other twelve platform jobs
do not contribute JUnit files in this integration.

Incomplete or rejected source reports are not converted into replacement XML.
Their fixed collection state is passed separately. A missing, failed or stale
transfer leaves the other advisory sections visible with a JUnit-unavailable
notice and exit `1`; an incomplete source is identified explicitly. A downloaded
file is still untrusted. Archive or metadata mismatches return `1` with the
available advisory sections; counts are omitted when archive/run or repository
identity cannot be established. Detected corrupt ZIP, malformed XML or a
rendering/provider error retains the module's existing exit `2` and
unavailable-review behavior. A failed upload/download step
also remains a failed workflow step. Cancellation or runner loss may prevent a
summary altogether.

Open **Actions → CI → Summary** to read the report. No expectations file,
repository variable or PR comment is required. The minimized JUnit artifact is
the only additional uploaded file; it contains no original free-text fields.
The job has read-only permissions, including `actions: read` for run and artifact
metadata. It uses the workflow token only for metadata collection and checkout;
no personal token or repository secret is required. The artifact action retains
its current-run scope, with no cross-run token or download fallback.

Failed observed checks, broken links, stale script instructions, removed test-file
paths and added unconditional skip findings do not fail this advisory job.
Reported JUnit failures/skips do not change that behavior;
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
