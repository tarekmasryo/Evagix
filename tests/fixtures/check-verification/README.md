# Check verification evaluation fixtures

`holdout-v1.json` contains separately authored, specification-based synthetic
cases derived only from the [check verification contract](../../../docs/guides/check-verification-contract.md).
The case author did not inspect the implementation, the development spike, or
acceptance tests, and did not run the evaluator or tune expectations to outputs.
All credential-like identifiers are synthetic and contain no real secrets.

## Freeze and maintenance

The corpus and its exact-byte SHA-256 in `manifest.json` are frozen before the
first execution. Maintain cases separately from the implementation and acceptance
tests. A changed corpus requires a new version and digest; preserve the original
artifact and first evaluation result. Record the implementation digest together
with the corpus digest for each evaluation.

If a consumed case informs a fix, it becomes regression data. Retain the first
result and disclose its reuse; do not describe the reused set as an untouched
holdout. A new independently maintained set is required for another untouched
holdout evaluation. Never silently relabel a case to match evaluator output.

## Fixture boundary

Each case supplies a complete JSON request, a JSON batch, a simulated assessment
mode, and a contract-derived expectation. Invalid-input cases intentionally violate
the JSON contract and use `expected.reason: null`; they must be rejected rather
than returned as ordinary results. Metadata and expectations are outside the
request and batch. The `assessment` field is fixture metadata, not a serialized
`SourceAssessment` or a self-attestation by the batch.

The assessment modes are `verified`, `unverified`, `missing`, and
`mismatched_digest`. They simulate an in-process trusted caller and do not test
producer authentication, provenance validation, or correct collection scope.

Report disagreements, false support decisions, and counts by segment. Require
zero disagreements and zero false support decisions for this contract gate.
The set has no real repository or field sampling and no external human review.
It supports no claim of production precision, recall, or user value.
