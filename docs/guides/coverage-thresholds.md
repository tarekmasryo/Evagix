# Review lower CI coverage declarations

`changed --coverage` is an offline, advisory preview for reductions in literal
`pytest-cov` thresholds declared in GitHub Actions workflows. It compares the
unique merge base of the selected refs with the committed head. This addition
is under development after the prepared `0.2.0a1` preview; it is not in the
published `0.1.2` package.

```bash
evagix changed . --coverage --base main --head HEAD
evagix changed . --coverage --base main --head HEAD --format json
evagix changed . --coverage --base main --head HEAD --format markdown
```

For the same workflow, job and identified step, changing this declaration:

```yaml
jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - name: Coverage
        run: python -m pytest --cov=app --cov-fail-under=80
```

to `--cov-fail-under=70` produces `ci.coverage-threshold-lowered`, with the
previous and current values and both source locations. An increase or unchanged
numeric value produces no reduction finding. Review whether the change is
intentional. Findings do not assert that coverage fell or that a required check
was weakened.

## Supported comparison

- Only changed, existing, regular tracked `.github/workflows/*.yml` and `*.yaml`
  files are compared, case-sensitively. Added workflows and other CI formats
  are outside scope. Removed or renamed workflows leave an explicit limitation;
  there is no inferred threshold of zero or workflow-rename matching.
- Declarations match by workflow path, literal job key and unique step `id`,
  falling back to a unique literal step `name` when no ID is present. There is
  no positional or fuzzy identity matching.
- The bounded reader accepts block mappings and sequences. A supported `run`
  is a plain scalar or literal block (`|`, `|-`, `|+`) containing one nonblank,
  noncomment command line. Folded/quoted run scalars, explicit block indentation
  indicators, anchors, aliases, merged/duplicate keys and unsupported structures
  make the affected inspection incomplete. This is not a full YAML validator.
- A command must directly invoke `pytest` or `python -m pytest` (including
  `python3`, versioned `python3.N` and their `.exe` forms). Shell wrappers,
  chaining, substitutions, continuations and quoted executable names are not
  supported. Explicit shells, including inherited defaults, must be `bash` or
  `sh`. Without an explicit shell the report compares declarations only; it
  does not establish their execution semantics on a runner.
- Exactly one full `--cov-fail-under=N` or `--cov-fail-under N` must supply a
  decimal literal from 0 to 100, at most 64 characters. Values are compared
  without floating-point rounding. Missing, repeated or dynamic values are
  unresolved, not zero.
- Remaining parsed arguments must match in order. A changed command, test
  selection or coverage target makes comparison unresolved. Supported value
  options are `--cov`, `--cov-report`, `--cov-config`, `--cov-precision`,
  `--junitxml`, `--junit-xml`, `--rootdir`, `--confcutdir`, `--maxfail`, `-c`,
  `-k` and `-m`. Supported switches are `--cov-branch`, `--cov-append`,
  `--no-cov-on-fail`, `--disable-warnings`, `--strict-markers`, `-q`, `-qq`,
  `-v`, `-vv` and `-x`; literal positional arguments are also accepted.
- The only supported variable expansion is a double-quoted `$NAME` inside a
  JUnit output option's value. This permits declarations such as
  `--junitxml="$RUNNER_TEMP/results.xml"`; the value is compared literally,
  without resolving the variable. Other expansions, unquoted globs, GitHub
  expressions and unknown options remain unsupported.

The [GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
defines the source structure. The [pytest-cov configuration reference](https://pytest-cov.readthedocs.io/en/latest/config.html)
documents the command-line threshold. Evagix does not resolve configuration,
environment variables, pytest `addopts`, matrix values, conditions, installed
plugins, wrappers or reusable workflows into an effective coverage policy.
An unchanged command's configuration or execution environment may still change.
Measured coverage, test execution, required-check policy and merge readiness
remain unevaluated.

## Revisions, limits and output

Refs resolve to immutable commits. Staged, unstaged and untracked changes are
excluded. Missing Git objects/history and ambiguous merge bases are errors;
the command does not fetch history or execute repository commands, hooks or
filters.

The reader is bounded to 40 changed existing workflow files, 500,000 bytes per
source, 10,000 source lines/parser nodes, 32 nesting levels and 200 findings.
An additional eligible item beyond a budget makes inspection incomplete.
Unavailable, oversized, non-UTF-8 or nonregular sources and unmatched previous
declarations produce limitations. Findings from independently readable sources
remain visible. `complete` means complete within this declared scope, not a
complete audit of CI.

| Exit | Meaning |
| --- | --- |
| `0` | Inspection complete within scope, with or without advisory findings. |
| `1` | Inspection incomplete; review the reported limitations. |
| `2` | Invalid input, unavailable Git metadata, operational error or oversized Markdown output. |

Formats are `text`, `json`, `markdown` and `github-annotations`. JSON uses the
separate `coverage-drift.schema.json` preview contract, with string-valued
thresholds, one-based source lines/character columns and
`policy_decision: not_evaluated`. Annotation findings are notices; limitations
are warnings. Outputs redact sensitive metadata and omit raw commands. Display
identities must not be reused as raw evidence keys after redaction.

`--coverage`, `--tests`, `--scripts` and `--references` are mutually exclusive.
Existing commands and report contracts are unchanged without the new option.
This inspection is not yet included in the combined PR summary or the pinned
automatic CI report.
