# Local pytest JUnit reports (preview)

`evagix junit-report PATH` reads an explicitly selected local report produced by
pytest's `--junitxml` option. It displays reported outcomes without running tests,
reading project configuration, contacting services or evaluating merge policy.
This addition is under development after the prepared `0.2.0a1` preview; it is
not available in the published `0.1.2` release.

If a report already exists, inspect it directly:

```bash
evagix junit-report results.xml
evagix junit-report results.xml --all
evagix junit-report results.xml --format json
```

To create a report yourself, run pytest separately in a project you trust:

```bash
python -m pytest --junitxml=results.xml
```

Evagix does not run this command. Generating XML does not preserve pytest's exit
code inside the report; inspect the test process result separately.

## Reading the result

The summary counts observed `testcase` rows, classified as `passed`, `failed`,
`error` or `skipped`. Rows containing multiple outcome markers use the priority
`error`, then `failure`, then `skipped`. A row without those markers is a
**reported pass**, not independent proof that a test body completed.

Suite `observed` counters count individual `failure`, `error` and `skipped`
markers, separately from the row summary. Pytest can record multiple errors in
one row or repeat an identity in separate rows after a call and teardown failure.
Evagix preserves both; it does not deduplicate by test name.

`reported_outcome` means:

| Value | Meaning within this file |
| --- | --- |
| `failed` | At least one observed row has a failure or error, even if counts elsewhere are incomplete. |
| `passed` | The report is internally consistent, at least one row reports a pass, and no row reports failure/error. Skipped rows may also be present. |
| `skipped_only` | The consistent report contains only skipped rows, including pytest xfail markers. |
| `empty` | Suites are present with consistent zero counts; no test execution is established. |
| `unknown` | The report cannot support an aggregate outcome. |

Text output hides passed rows unless `--all` is supplied. JSON always contains all
accepted rows. Case names are untrusted display data: credential patterns are
redacted and control/format characters escaped for terminal output. Long labels
are shortened after redaction, with `identity_truncated: true` and a text note.
This affects display only; case rows and counts are retained. Display identities
must not be used as unique IDs or replayable evidence. Failure
messages, tracebacks, captured stdout/stderr, properties, hostnames and source
paths are omitted in both formats. Redaction is pattern-based, so avoid putting
secrets in test names or parametrized IDs.

## Collection is separate from execution

| Exit | `collection_status` | Meaning |
| --- | --- | --- |
| `0` | `complete` | Supported XML was read and its declared counters agree with its observed rows/markers. This includes reports with failed, skipped or zero tests. |
| `1` | `incomplete` | Required counts/names are missing, counts disagree, structure is unsupported, or a resource limit prevents inspection. |
| `2` | `error` | Input is unreadable, not a regular file, malformed, unsafe XML or uses an unsupported encoding declaration. Invalid CLI arguments also return `2`. |

Missing or invalid numeric counters are reported as `null` and make collection
incomplete. For well-formed supported reports, count/name issues preserve observed
rows. Malformed XML, unsupported structures and resource-limit failures discard
partial observations, rather than presenting a partial parse as a clean report.
An unsupported structure or resource limit can stop the reader before it checks
the remaining XML. Such input stays incomplete even if its unread remainder is
malformed; incomplete collection does not establish XML well-formedness.
Errors produce a generic structured report in JSON mode, without echoing paths,
XML fragments or system exception messages.

`complete` covers the supplied report only. It does not prove that the planned
suite was fully selected, that the session finished, that a missing shard ran, or
that an early stop did not occur. Even a well-formed report from a pytest run
stopped with `-x` may be internally consistent.

These trust fields remain independent and fixed:

- `source_kind: local_file` and `source_verification: unverified`.
- `revision_binding: unknown` and `run_completion: unknown`.
- `policy_decision: not_evaluated`.

Neither XML properties, a commit string, timestamps, filename nor file mtime
authenticate execution or bind it to the working tree. Parsing does not establish
test quality, task completion or API compatibility. The reader does not create a
trusted `SourceAssessment` or feed the existing check verifier automatically.

## Supported input and limits

The supported subset is pytest's UTF-8 XML 1.0 output (`xunit1`/`legacy` and
`xunit2`): a single `testsuite`, or a `testsuites` wrapper containing direct suites.
Every suite must declare nonnegative integer `tests`, `failures`, `errors` and
`skipped` counters. `tests` is compared with case rows; other counters are compared
with outcome marker events. File and line attributes are not required.

Nested suites, namespaced structures, aggregate counters on the wrapper and
unrecognized elements (including plugin-specific retry outcomes) are unsupported
and produce incomplete collection. Other JUnit dialects are not claimed as
supported. The input format cannot authenticate which program produced it.

Limits are 8,000,000 input bytes, 10,000 case rows, 100 suites, 100,000 XML elements,
16 levels of nesting. Exceeding these input limits never yields a clean report.
Names/classnames are displayed up to 2,048 redacted characters plus an ellipsis;
this display limit does not make an otherwise consistent report incomplete. Only regular
files are read; direct symlinks and special files are rejected. DTD/entity
declarations and processing instructions are rejected. No XML references are
fetched, no XInclude is processed, and compressed input is unsupported.

The packaged preview schema is `evagix/schemas/junit-report.schema.json`.
Existing CLI commands, JSON contracts and default scans are unchanged.
The separate opt-in [`junit-github` command](github-junit-association.md) can
compare an original artifact ZIP with GitHub run metadata. It does not change
this local reader's trust fields or authenticate the artifact-producing attempt.
The [combined PR summary](pr-review-summary.md#optional-local-pytest-junit-report)
can include this report through its optional `--junit-report PATH` argument.
That section retains the same trust limits and is not associated with the PR's
commits or GitHub jobs. Without the option, PR summaries are unchanged.

Evagix's own PR workflow supplies a minimized transfer from its `Quality gates`
job. That transfer replaces suite and test identities with ordinal labels and
omits all original free-text fields before upload. Incomplete or rejected source
files are not uploaded. The workflow identifies the transfer attempt separately;
the reader still does not authenticate the execution or tested revision. See the
[workflow scope and unavailable-report behavior](pr-review-summary.md#evagixs-own-pull-request-workflow).

See pytest's [JUnit output documentation](https://docs.pytest.org/en/stable/how-to/output.html#creating-junitxml-format-files)
and Python's [XML security guidance](https://docs.python.org/3/library/xml.html#xml-security).
