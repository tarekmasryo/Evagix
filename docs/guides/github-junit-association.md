# Associate a JUnit artifact with GitHub (preview)

`evagix junit-github` compares an original local artifact ZIP with live GitHub.com
metadata. It links the archive's bytes to a selected artifact and run, compares
the provider's `head_sha` with an explicit expected revision, and checks whether
the selected run attempt is current. This feature is under development after the
prepared `0.2.0a1` preview and is not in the published `0.1.2` release.

The command does **not** establish which attempt produced the artifact, which code
the tests actually executed, or whether a task is complete. Those limitations
remain explicit even when every comparison matches.

## Explicit invocation

Download the original ZIP from the run's artifact download link. Keep those exact
bytes: an extracted XML file or a reconstructed ZIP cannot be compared with
GitHub's archive digest. Select the artifact ID and attempt explicitly; Evagix
does not choose a successful run or infer an attempt from an artifact name.

The following identifiers are placeholders:

```bash
evagix junit-github original-artifact.zip \
  --run https://github.com/owner/repository/actions/runs/123 \
  --attempt 1 --artifact-id 456 \
  --revision aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
```

Use `--format json` for the packaged `github-junit.schema.json` contract. Use
`--member results.xml` if the ZIP's sole member has a different name; the default
is `evagix-quality-junit.xml`, matching Evagix's own minimized transfer.

The expected revision is the run's provider `head_sha`. In particular, a PR run's
metadata does not establish that its head commit, rather than a test-merge commit
or another checkout, was executed. A revision mismatch is displayed even when
the archive belongs to the selected run. Working-tree changes are not covered.

Only this explicit command contacts GitHub. An optional `EVAGIX_GITHUB_TOKEN`
supplies read access when needed; public metadata can be read without a token,
subject to rate limits. The command never downloads or uploads report contents,
extracts files, executes tests, or changes the repository. Existing `junit-report`
and default scans remain offline and unchanged.

## What is verified

The command reads the local ZIP once into a bounded buffer and parses that same
buffer. It collects repository identity, run metadata, the selected attempt, and
artifact metadata through the existing bounded HTTPS client. It rechecks the
run, attempt and artifact fields before returning an association.

| Result | Meaning |
| --- | --- |
| `archive_binding` | The exact ZIP's SHA-256 and length match the artifact's provider digest and size, differ, or cannot be compared. |
| `artifact_run_match` | The artifact's run, repository, head repository and provider revision agree with the selected run. |
| `revision_match` | The run's provider `head_sha` matches the caller's expected revision. |
| `selected_attempt_status` | The requested attempt is current, stale compared with a later attempt, or could not be checked. |
| `artifact_attempt_binding` | Always `unknown`: the artifact API does not supply an authoritative producing attempt or job ID. |
| `tested_revision_binding` | Always `unknown`: metadata association is not proof of the actual checkout or test inputs. |
| `execution_verification` | Always `unverified`: a workflow can upload fabricated or incomplete results. |

An attempt suffix in an artifact name, an XML property, a timestamp or file mtime
does not establish attempt provenance. An independently collected attempt result
does not authenticate an artifact's producer. The current workflow's attempt
checks remain useful transfer guards, with this separate limitation.

Only an archive with a matching digest and artifact/run identity has its parsed
JUnit results included in this association report. A known revision mismatch or
stale selected attempt remains visible alongside those results. An expired
artifact or missing digest makes collection incomplete. Changed snapshots,
inaccessible endpoints and invalid metadata produce classified errors without
publishing a partial association.

## Outcomes and exit status

Run/attempt conclusions and XML outcomes are separate. For example, XML can report
passing tests while the workflow fails a coverage threshold or another job. No
job-level test attribution is inferred, and the command does not select or verify
all matrix jobs. JUnit counters preserve the [local reader's semantics](local-junit-reports.md):
`complete` XML does not prove full-suite selection or session completion.

| Exit | Meaning |
| --- | --- |
| `0` | Complete metadata/XML collection, matching archive/run/revision, and a current selected attempt. Failed, skipped-only or empty XML outcomes can still return `0`. |
| `1` | Incomplete collection, an archive/run/revision mismatch, or a stale selected attempt. |
| `2` | Invalid arguments, unreadable/unsafe input, malformed XML, or a provider/transport/stability error. |

No exit code approves a merge or proves the artifact-producing attempt.
`policy_decision` is always `not_evaluated`. Operational errors return a structured
report with fixed issue codes in JSON mode; invalid CLI arguments return a short
diagnostic on stderr.

The nested `junit` object retains the existing local-report schema and its fixed
trust fields. The enclosing association describes the archive's provider linkage;
it does not promote the local parser's observations to authenticated execution
evidence. Offline JSON Schema validators can register both packaged schemas by
their `$id`; schema validation does not require fetching schemas from the network.

The [combined PR summary](pr-review-summary.md#optional-github-junit-association)
can run this check with an explicit local ZIP and run/attempt/artifact IDs. It
derives the repository and expected head revision from the requested PR and
compares repository identities without changing this standalone command.

## Input and transport limits

- Local input must be a regular, non-symlink ZIP of at most 8,100,000 bytes.
- Exactly one file member, with the explicitly selected safe relative XML name,
  is supported. Duplicate names, extra files, directory entries, symlinks,
  encrypted members and unsupported compression are rejected. Nothing is extracted.
- Stored and DEFLATE compression are supported; the expanded XML is limited to
  8,000,000 bytes and the existing bounded JUnit parser's limits.
- GitHub metadata requests use the existing fixed-host TLS client, no redirects
  or environment proxies, and its request, response and elapsed-time limits.
- Output omits archive paths and raw metadata errors. Existing JUnit redaction
  and omission of logs, messages and tracebacks still apply. Do not put secrets
  in test identities; pattern redaction cannot recognize arbitrary private text.

This first integration is standalone. The automatic PR summary still consumes
its existing extracted XML transfer and does not invoke this command. Connecting
it to an original ZIP transfer requires an explicit later workflow change.

## Provider references

- [GitHub artifact metadata and archive digest](https://docs.github.com/en/rest/actions/artifacts#get-an-artifact).
- [GitHub run-attempt metadata](https://docs.github.com/en/rest/actions/workflow-runs#get-a-workflow-run-attempt).
