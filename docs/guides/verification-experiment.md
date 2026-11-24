# Offline verification experiment

`scripts/verification_spike.py` is a development-only decision-model experiment.
It is not an installed Evagix command, a CI adapter, or proof that an agent
completed a task. It does not execute repository commands or use the network.

Run it from a source checkout:

```bash
python -m scripts.verification_spike
```

The experiment evaluates one explicit claim type: a named check and job
succeeded for a particular repository, revision, and subject kind (`commit`
or `test_merge`). Required checks come from the test harness separately from
optional submitted claims. Omitting a claim does not remove a required check.

## Evidence boundaries

- Provenance is **simulated** by harness-owned fixture objects. Object identity
  is not authentication and must not be used as a production trust mechanism.
- The harness selects the run and latest attempt; the script cannot discover
  which CI run should be trusted.
- Unrecognized sources, mismatched subjects, incomplete inventories, missing
  attempts, conflicting results, and unfinished runs cannot satisfy a claim.
- `skipped`, `neutral`, and other non-success/non-failure conclusions remain
  unverified. An explicit failure contradicts the scoped success claim.
- A result for committed code does not establish coverage of a dirty working
  tree. This experiment conservatively reports that case as not covered.
- Even a satisfied claim establishes only the result of that scoped check,
  not test quality, API compatibility, or task completion.

The output includes an intentionally weak `naive_any_success` comparator. It
illustrates mistakes in accepting any successful report; it does **not** model
GitHub branch protection or demonstrate an advantage over a correctly
configured CI system.

Before a production integration, define and independently test authenticated
evidence collection, run selection, matrix completeness, workflow identity,
policy authority, and behavior when CI metadata is unavailable. Product value
still requires evaluation against a competent simple alternative and real
developer workflows.

## Repository-scan benchmark

The separate development utility measures static scanning on a disposable
synthetic repository:

```bash
python -m scripts.benchmark_repo_scan --files 2000 --repeats 3 --warmups 1
```

Fixture creation is outside timed intervals. `--profile` performs separate
profiling runs, and `--output PATH` creates a report without overwriting an
existing file. Compare identical code, environments, fixtures, and scan
semantics except for the optimization under test. Results describe this
synthetic workload; they are not a guarantee for other repositories or systems.
