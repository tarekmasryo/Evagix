# Check verification contract

This preview Python API evaluates one claim: a named job in a named workflow
succeeded for an explicit repository and immutable Git revision. It does not
change an existing CLI command, report schema, readiness score, or default scan.
It performs no I/O, authentication, command execution, or network access.

## Inputs and authority

`CheckSubject` contains `repository`, `revision`, `subject_kind` (`commit` or
`test_merge`), `workflow`, and `job`. Workflow and job values are caller-defined
stable identifiers, not an inferred mapping from display names. All five fields
must match exactly. Revisions are full lowercase 40- or 64-character Git object
IDs; abbreviated hashes, branch names, and "latest" are not accepted.

`CheckRequest` contains a subject, an explicitly selected `run_id`, and a positive
integer `attempt` (at most 9,007,199,254,740,991). The caller must select these from its own trusted policy and
collection logic. The engine never selects a run by lexical ordering, chooses any
successful attempt, or discovers which checks are required. Evaluate each required
job separately; omitting an optional agent claim must not remove a required request.

`EvidenceBatch` describes a source (`source_kind`: `ci` or `local`, and
`source_id`), collection completeness (`complete`), and up to 1,000 records.
Each `RunEvidence` has `record_id`, `subject`, `run_id`, `attempt`, `state`, and
`conclusion`. Supported states are `queued`, `in_progress`, `completed`, and
`cancelled`. Conclusions are null, `success`, `failure`, `skipped`, `neutral`,
`cancelled`, or `timed_out`; only a completed record may have a conclusion.

The request JSON has `schema_version: "1.0"`, `kind: "check_succeeded"`,
`subject`, `run_id`, and `attempt`. Batch JSON has `schema_version: "1.0"`,
`kind: "check_evidence"`, `source_kind`, `source_id`, `complete`, and `records`.
Subject and record fields use the names above. Parsers reject missing or unknown
fields, invalid types, booleans used as attempts, and unsupported enum values.
Identity strings are nonempty, single-line, at most 256 characters, and have no
leading or trailing whitespace. Errors identify the invalid field, not its value.

`SourceAssessment` is a separate in-process input from the trusted caller. It
contains `batch_digest`, `verification` (`verified` or `unverified`), and
`verifier`. There is no JSON parser for an assessment. A batch cannot grant itself
trust by setting `verified`, naming a CI provider, or supplying a digest.

The batch digest binds all record, source, and completeness fields using canonical
JSON and SHA-256, exposed by `EvidenceBatch.digest()`. Encode JSON as UTF-8 with
sorted keys, no ASCII escaping, and separators `,` and `:` without whitespace.
Sort records by their individually encoded JSON bytes, preserving duplicates,
then encode the complete batch payload. Hash the prefix
`evagix.check-evidence.v1` followed by a NUL byte followed by those payload bytes.
Reordering is immaterial, while
changing a record or collection metadata invalidates the binding. A digest proves
content equality, not authenticity. `caller_verified` means that the supplied
assessment is marked `verified` and bound to this batch; the evaluator itself does
not authenticate the source. Both CI and local sources require the same assessment.
The optional [GitHub collector](github-check-collection.md) authenticates the origin
of provider metadata and binds an assessment to its normalized batch. This does
not establish which code was actually tested or authenticate required-check policy.

## Result and decision rules

Results keep `condition` (`supported`, `contradicted`, `unverified`),
`source_verification` (`caller_verified`, `unverified`, `binding_mismatch`),
`completeness` (`complete`, `incomplete`), and `evidence_match`
(`match`, `mismatch`, `unknown`) separate. Collection completeness is the supplied
collector statement, not a claim that every task requirement was checked.
`run_state` and `conclusion` describe an unambiguous selected record, or are null.
`engine_status` is `completed` for a returned result; a queued CI job is not an
engine error. Invalid inputs raise `ContractError`, never a successful result.
`policy_decision` is `not_evaluated`: no result authorizes merging or execution.

Selection checks use only records for the exact subject, then the requested run,
then the requested attempt. A higher observed attempt in that run makes the
selection inconsistent. Records with identical state and conclusion are harmless
duplicates even when their record IDs differ; retain all their IDs. Differing state or
conclusion values for the selected attempt are a conflict. Stable record IDs
provide traceability and are not evidence of authenticity.

The following precedence determines `reason` and `condition`. Matching and source
dimensions are still recorded independently when a prerequisite fails.

| Situation | Condition | Reason |
| --- | --- | --- |
| Assessment digest differs | unverified | `source_binding_mismatch` |
| No verified assessment | unverified | `source_unverified` |
| Incomplete collection | unverified | `incomplete_inventory` |
| No records | unverified | `no_evidence` |
| No exact subject | unverified | `subject_mismatch` |
| Selected run absent | unverified | `run_mismatch` |
| Higher attempt observed | unverified | `inconsistent_attempt_inventory` |
| Selected attempt absent | unverified | `attempt_mismatch` |
| Conflicting selected records | unverified | `conflicting_results` |
| Selected record not completed | unverified | `run_not_completed` |
| Completed record without conclusion | unverified | `conclusion_missing` |
| Completed success, all prerequisites met | supported | `check_succeeded` |
| Completed failure, all prerequisites met | contradicted | `check_failed` |
| Other completed conclusion | unverified | `non_success_conclusion` |

`evidence_match` is `match` for an unambiguous selected attempt, `mismatch` for a
different subject/run/attempt, and `unknown` for no records, inconsistent attempts,
or conflicting results. It describes identity matching, not source trust.

Results include the request, source description, batch digest, and a stable reason
code. Sorted `evidence_ids` identify the selected records, including conflicting
records; an inconsistent attempt inventory instead cites the records in that run.
Output is redacted with Evagix's existing
redaction layer. Raw identities are retained internally for matching and hashing:
two different secrets must not become the same identity after redaction. Redacted
reports are display artifacts, not replayable evidence or authenticated inputs.

## Acceptance and evaluation

Acceptance tests cover typed and JSON boundaries, exact identity matching, digest
binding, missing and conflicting evidence, retries, source-kind independence,
redaction, and unchanged existing CLI/schema behavior. No runtime dependency is
needed; JSON Schema validation is a development-time check.

The [GitHub Actions snapshot importer](github-actions-evidence.md) supplies a
bounded offline normalization path. It does not authenticate imported evidence
or change this contract's source-assessment requirements.

A separate, frozen, specification-based synthetic case set evaluates the same
call path. Its fixture assessment simulates a trusted caller and does not test
authentication. Record the case-set digest, implementation digest, disagreements,
false support decisions, and counts by segment. Require no disagreements and no
false support decisions. This is a contract gate, not a production accuracy claim.
Once cases inform a fix they are regression data, not an untouched holdout; retain
the first result and disclose any such reuse. Real repository sampling, external
annotation, CI provenance validation, and user-value comparisons remain separate.

## Limits

The result covers only the specified immutable revision and job. It does not
cover a working tree, establish test quality, authenticate a GitHub run, verify
all matrix jobs, satisfy natural-language requirements, or prove task completion.
No timestamps or file modification times are used to establish applicability.
The existing offline spike remains a development demonstration, not this API's
authentication layer.

## Python usage

```python
from evagix.verification import (
    CheckRequest, CheckSubject, EvidenceBatch, RunEvidence, evaluate_check,
)

subject = CheckSubject("example/project", "a" * 40, "commit", "tests", "python:3.11")
request = CheckRequest(subject, "run-42", 1)
record = RunEvidence("record-42", subject, "run-42", 1, "completed", "success")
batch = EvidenceBatch("local", "imported-report", (record,), complete=True)
result = evaluate_check(request, batch)
assert result.condition == "unverified"
assert result.reason == "source_unverified"
```

Use `parse_request(dict)` and `parse_batch(dict)` for JSON-decoded inputs.
Constructing `SourceAssessment(batch.digest(), "verified", verifier_id)` is a
trusted caller's assertion, not a way to authenticate an imported file. The caller
must independently establish the producer, subject, selected run and attempt, and
collection completeness. For live GitHub.com metadata, use the separately invoked
[collector](github-check-collection.md); importing an arbitrary file remains unverified.

Use `result.to_dict()` for the centrally redacted report. Raw model fields are for
internal comparison, not logging; model representations omit their field values.
The packaged JSON Schema validates the report and defines request and batch inputs
under `$defs`. Invalid input raises `ContractError` with a value-free message. The
API is stateless, synchronous, and performs no I/O; callers own reading and writing.

## Reproducing the contract evaluation

From a development checkout, after the acceptance tests pass:

```bash
python -m pytest tests/verification --no-cov
python -m scripts.evaluate_check_verification --output check-evaluation.json
```

The evaluation utility reads the frozen corpus only when explicitly invoked. It
checks the manifest digest, case count, and unique IDs, then reports each expected
and actual result, counts by segment, and an implementation fingerprint covering
the preview engine, redaction modules, schema, and runner. Exit codes are `0` for
agreement on all cases, `1` for a disagreement, and `2` for invalid evaluation
inputs or an operational failure. Output files are created exclusively; use a new
filename for each run to preserve earlier results. Acceptance tests use separate
development cases and never load the frozen corpus.

The [fixture notes](https://github.com/tarekmasryo/Evagix/blob/9da38d431618d506e9a79be097273dc6d678c217/tests/fixtures/check-verification/README.md) describe
provenance and reuse restrictions. The fingerprint identifies inspected source
content; it does not authenticate the evaluator or record its Python environment.
