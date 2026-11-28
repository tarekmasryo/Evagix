# Command guide

Evagix has several commands because it supports repository inspection, generated-context governance, README evidence checks, and PR risk review. Most users only need a small path first.

The new evidence and deletion reports below are included in the unpublished
`0.2.0a1` preview. See [installation and upgrade notes](guides/preview-release.md)
before trying them with a stable installation.

## First-time local use

```bash
evagix doctor .
evagix readme-audit .
evagix eval-context . --strict
evagix check .
```

Use this path when you want to understand the current repository state without changing files.

## Command inventory

This compact inventory mirrors the registered CLI. Use `evagix <command> --help` for complete flags and examples.

Human-readable terminal styling is enabled on supported interactive terminals. Disable it with the global `--no-color` option or the `NO_COLOR` environment variable; non-TTY, redirected, piped, CI, and machine-readable output remains plain.

| Group | Commands |
| --- | --- |
| Inspect | `evagix scan`, `evagix suggest`, `evagix profiles`, `evagix targets`, `evagix policy`, `evagix classify`, `evagix explain` |
| Generate and maintain | `evagix compile`, `evagix sync`, `evagix check`, `evagix onboard`, `evagix baseline`, `evagix diff`, `evagix init`, `evagix init-ci`, `evagix scoped` |
| Readiness and reports | `evagix doctor`, `evagix report`, `evagix readme-audit`, `evagix decide`, `evagix plan`, `evagix drift`, `evagix eval-context`, `evagix evidence`, `evagix audit` |
| Preview and experimental | `evagix agents`, `evagix prepare`, `evagix context-pack`, `evagix mcp` |
| Git-aware review | `evagix changed`, `evagix pr-risk` |
| Remediation | `evagix fix` |
| Explicit GitHub evidence (preview, network required) | `evagix pr-checks`, `evagix verify-check`, `evagix junit-github` |
| Local test reports (preview, offline) | `evagix junit-report` |

## Local pytest JUnit report (preview)

```bash
evagix junit-report results.xml
evagix junit-report results.xml --format json
```

Reads one local pytest report without running tests or using the network. It
shows reported passed, failed, error and skipped case counts; `--all` includes
passed text rows. Source verification remains `unverified`, revision binding and
run completion remain `unknown`, and merge policy is not evaluated.

Exit `0` means consistent report collection, even when tests failed or all rows
were skipped. Exit `1` means incomplete data; `2` means unreadable, malformed or
unsafe input. See [supported formats, trust limits and examples](guides/local-junit-reports.md).
This addition is under development after the prepared `0.2.0a1` preview.

## GitHub JUnit artifact association (preview)

`evagix junit-github ARCHIVE --run RUN_URL --attempt N --artifact-id N --revision SHA`
compares an original local artifact ZIP with live GitHub metadata. It checks the
archive digest, run identity, expected provider revision and whether the selected
attempt is current. The artifact-producing attempt and actual tested code remain
unknown; run conclusions and XML outcomes are shown separately.

Exit `0` means complete matching collection with a current selected attempt,
not test success or merge approval. Exit `1` means incomplete, mismatched or stale
evidence; `2` means invalid input or an operational error. This optional addition
is under development after the prepared `0.2.0a1` preview. See the
[artifact association guide](guides/github-junit-association.md) for input limits,
credentials, JSON output and the distinction between run and attempt association.

## Pull request check report (preview)

```bash
evagix pr-checks https://github.com/owner/repository/pull/123
```

Start from a PR URL to see reported failures, pending checks, other outcomes, and
detail links, with head and test-merge inventories kept separate. No request JSON
or local checkout is needed. `--all` includes passed text/Markdown rows; `--format json`
includes every collected row. Network/authentication is explicit, using only
`EVAGIX_GITHUB_TOKEN` when set. See the [PR check guide](guides/pull-request-checks.md).

**This command is a report, not a CI acceptance gate.** Exit `0` means complete
collection, even when checks failed; `1` means incomplete inventory, and `2` means
invalid input or collection failure. Required-check policy and merge readiness
are not evaluated. The JSON shape is defined in `github-pr-checks.schema.json`.

Add `--expectations checks.json` to compare this inventory with explicit expected
revision scopes, check names, kinds, and producer IDs. This mode reports passed,
failed, pending, missing, or unverified expectations using the separate preview
`github-pr-expectations.schema.json` contract. The supplied list is not treated
as authenticated repository policy. Exit codes still describe collection, not
acceptance: missing or failed expectations can appear in an exit-`0` report.
See the [expectations format and trust boundaries](guides/pull-request-checks.md#compare-caller-supplied-expectations).

`--format markdown` renders either mode for job summaries, with redacted literal
values and explicit revision/collection scope. Oversized Markdown returns `2`
without partial stdout. The [optional CI summary recipe](guides/pr-review-summary.md)
combines checks, deleted-file references, deleted-script instructions, and
supported test changes for the same immutable base/head pair. Repository findings
remain advisory; an incomplete inspection makes the combined report incomplete.
The test-change section is a development-preview addition; the currently pinned
automatic CI report does not include it yet.
The `evagix.pr_summary` module needs no expectations file: it reports observed
checks with required-check coverage explicitly unknown. Its optional
`--expectations` path is read only from the requested base commit; an invalid
explicit file fails rather than falling back to inventory mode.
An optional `--junit-report PATH` adds local pytest outcomes as a separate,
unverified section. It does not associate the report with GitHub jobs or the
requested commits. Without this option the existing report is unchanged; see
the [local input contract](guides/pr-review-summary.md#optional-local-pytest-junit-report).
Alternatively, `--junit-archive PATH --junit-run-id N --junit-attempt N --junit-artifact-id N`
compares an original artifact ZIP with GitHub metadata and the requested PR head.
This mode is mutually exclusive with local XML input and preserves unknown
producing-attempt and tested-code provenance. See the
[association options and exit meanings](guides/pr-review-summary.md#optional-github-junit-association).

## Selected GitHub check (preview)

```bash
evagix verify-check --request check-request.json --github-repo owner/repository --format json
```

This preview command collects GitHub.com metadata for one explicitly
selected `push` job execution. It uses `EVAGIX_GITHUB_TOKEN` only when set; public
metadata can be read anonymously. It does not run repository commands or change
existing scans. See [request format, permissions, limits, and evidence meaning](guides/github-check-collection.md).

Its exit codes are `0` for supported provider-reported success, `1` for a
contradicted/unverified claim, and `2` for invalid input or an operational failure.
JSON uses the existing check-verification schema; expected errors go to stderr.
The result does not evaluate a merge policy or prove test execution on the claimed code.

## Deleted file references (preview)

```bash
evagix changed . --references --base main --head HEAD
```

This opt-in mode reports explicit local Markdown links in root `README.md` and
`AGENTS.md` whose regular-file targets existed at the merge base and are absent
at the committed head. Working-tree changes are excluded. Findings are advisory;
exit `0` means complete inspection, `1` incomplete inspection, and `2` an input
or operational error. JSON uses the separate `reference-drift.schema.json`
preview contract. Without this flag, `changed` keeps its existing behavior.
See [supported links, comparison rules, and limitations](guides/deleted-references.md).

Reference reports also support `--format markdown`. It preserves advisory
exit semantics and refuses oversized output rather than silently truncating it.

## Deleted script instructions (preview)

```bash
evagix changed . --scripts --base main --head HEAD
```

This separate opt-in mode reports supported literal script commands in root
`README.md` and `AGENTS.md` whose tracked targets were removed since the
merge base. It assumes a repository-root working directory and does not execute
scripts or infer replacement paths. JSON uses `script-drift.schema.json`;
text, Markdown, and GitHub annotations are also supported. Exit codes are `0`
for complete advisory inspection, `1` for incomplete inspection, and `2`
for input or operational errors. `--scripts` and `--references` are mutually
exclusive; existing modes are unchanged. See the
[supported commands and limits](guides/deleted-scripts.md).

## Test changes (preview)

```bash
evagix changed . --tests --base main --head HEAD
```

This opt-in advisory mode reports removed Python test-file paths and new supported
unconditional pytest skip declarations on existing named tests. Git rename
candidates are shown separately; conditional skips are excluded. It reads
committed snapshots without importing or executing tests. JSON uses the separate
`test-changes.schema.json` contract. Exit codes are `0` for complete inspection,
`1` for incomplete inspection and `2` for input/operational errors, independently
of finding counts. `--tests`, `--scripts` and `--references` are mutually exclusive.
This addition is under development after the prepared `0.2.0a1` preview. See
[supported syntax, renames and limits](guides/test-changes.md).

## CI gate

```bash
evagix check .
evagix doctor . --strict --fail-under 80
evagix readme-audit . --strict --fail-on unsupported
evagix eval-context . --strict --fail-on high
```

This checks generated-context drift, readiness, unsupported README claims, and high-risk agent-context findings. Evagix does not run project test/lint/typecheck commands by default.


## CI and pre-commit integration

Generate a downstream GitHub Actions workflow with the same governance gates:

```bash
evagix init-ci . --fail-under 85
```

Pin a specific GitHub fork or tag when the package is not installed from PyPI:

```bash
evagix init-ci . --install-mode github --repo tarekmasryo/Evagix --ref v0.1.2
```

Use editable installation only for local Evagix development:

```bash
evagix init-ci . --fail-under 85 --install-mode editable
```

The generated workflow checks drift without running `evagix sync .` first. On self-hosted GitHub Actions runners, keep the runner current enough for the Node.js runtime used by the pinned action versions.

Evagix also provides pre-commit hooks for downstream repositories:

```yaml
repos:
  - repo: https://github.com/tarekmasryo/Evagix
    rev: v0.1.2
    hooks:
      - id: evagix-check
      - id: evagix-doctor
```

## Command semantics that matter in CI

### Generated onboarding reports

`evagix onboard .` creates optional `.evagix/` onboarding reports for humans and agents. These reports are optional unless `[policy].require_onboarding_pack = true` is configured.

### `evagix check .`

`check` verifies Evagix-managed generated context freshness and self-governance drift. It is intentionally narrow: it does not mean the whole repository is production-ready, and it does not replace `doctor`, `readme-audit`, or `eval-context`.

For a full readiness gate, run:

```bash
evagix check .
evagix doctor . --strict --fail-under 80
evagix readme-audit . --strict --fail-on unsupported
evagix eval-context . --strict --fail-on high
```

### Doctor agent-context safety

`doctor` inspects discovered agent-context files and configured custom targets for dangerous-command and prompt-injection indicators by default. It reports unsafe paths, invalid UTF-8, and incomplete reads within that scope. Scanning never executes the documented commands.

`--strict` still enables the additional context-quality and repository-evidence checks; default safety checks do not require missing setup, test, or style sections to be reported. Strict mode includes the same context-safety checks without scanning them twice.

**Upgrade impact:** repositories previously accepted by default `doctor` can receive new findings and lower scores. The existing exit policy is unchanged: `doctor` exits `1` for error-level findings or a score below its configured threshold. Warning-level findings alone need not produce a nonzero exit. Review the new findings and your existing `--fail-under` policy before upgrading CI; no new flag, schema, or exit code is required.

### `--strict` versus failure policy

`--strict` enables stricter evaluation. It does not always fail CI by itself. Use `--fail-under` or `--fail-on` to define the failure policy explicitly.

One safety exception is deliberate: `readme-audit --strict` exits `1` when README analysis is truncated, invalid UTF-8, or fails to read. A partial or unreadable file cannot support a trustworthy clean result. Non-strict mode still emits the incomplete finding but remains reporting-only unless an explicit failure policy selects it.

External or missing agent context is deliberately unscored. JSON reports use `score: null`, an explicit `score_type`, and `management: external|missing`; Markdown reports show `N/A (unscored)`. `eval-context --fail-under` exits `1` for an unscored report because no structural score exists to satisfy the threshold.

## Exit-code contract

Existing repository commands use the following process-exit contract for automation.
The explicit GitHub commands use their separate contracts documented above.

| Code | Meaning |
| --- | --- |
| `0` | The command completed and its configured policy gate passed. |
| `1` | A repository finding, readiness threshold, drift check, configured failure policy, or safe output-write guard failed. |
| `2` | Command-line usage was invalid, a requested mode is unsupported, or an experimental command was invoked outside its supported mode. |

`manual_review_required` is a README-claim verdict, not a separate process code. It exits `0` by default and exits `1` only when the caller explicitly selects `--fail-on manual-review`. Unexpected Python exceptions are not converted into a misleading policy result; they remain operational failures with a traceback for maintainers.

## Debugging evidence

```bash
evagix evidence . --format json
evagix scan . --format json
evagix explain <finding-code>
```

Use these commands when you need machine-readable facts or want to understand why a finding appeared.

## PR review

```bash
evagix changed . --base main
evagix pr-risk . --base main
```

These commands inspect changed files and produce advisory review/merge/block guidance. `pr-risk` should not replace `check`, `doctor`, `readme-audit`, `eval-context`, tests, dependency audits, or human review.

## Generated context workflow

```bash
evagix compile .
evagix sync . --plan
evagix sync .
evagix check .
```

By default, `compile` writes only `.evagix/context.md` and `.evagix/context.json`. Tool-specific agent files are opt-in.

## Repository orientation and setup commands

These commands cover initial inspection and opt-in setup. Inspection commands do not modify the repository unless an explicit output path is supplied.

| Command | Purpose | Read/write behavior | Important flags | Exit codes | JSON stability |
| --- | --- | --- | --- | --- | --- |
| `evagix classify .` | Classify the primary repository type and secondary capabilities from detected evidence. | Read-only. | `--json`, `--profile` | `0` classification completed; nonzero on invalid input or operational failure. | Stable; see `classification-report.schema.json`. |
| `evagix decide .` / `evagix plan .` | Recommend safe next actions and explicit human approval gates. | Read-only by default; writes only with `--output`. | `--format text\|markdown\|json`, `--output`, `--force`, `--profile` | `0` report completed; `1` guarded output-write failure. | Stable; see `decision-plan.schema.json`. |
| `evagix init .` | Create the initial `evagix.toml` policy configuration. | Writes `evagix.toml`; refuses an existing file unless forced. | `--profile`, `--force` | `0` created; `1` existing/write failure; `2` invalid profile. | No JSON output. |
| `evagix init-ci .` | Create a GitHub Actions workflow that installs Evagix and runs drift/readiness gates. | Writes `.github/workflows/evagix.yml`; refuses an existing file unless forced. | `--install-mode`, `--repo`, `--ref`, `--package-version`, `--fail-under`, `--force` | `0` created; `1` existing/write failure; `2` unsafe or invalid install configuration. | No JSON output. |
| `evagix profiles [name]` | List policy profiles or show one profile's details. | Read-only. | Optional profile name. | `0` success; `1` unknown profile. | No JSON mode. |
| `evagix suggest .` | Print prioritized next actions derived from repository facts and doctor findings. | Read-only. | `--profile` | `0` success; nonzero on invalid input or operational failure. | No JSON mode. |

## Advanced and preview commands

These commands are useful for staged adoption and early feedback. See the stable and preview contract sections in [Schemas](schemas.md); packaging a schema does not by itself promote a preview API to stable.

| Command | Purpose | Read/write behavior | Important flags | Exit codes | JSON stability |
| --- | --- | --- | --- | --- | --- |
| `evagix baseline .` | Create a staged-adoption configuration from current non-error findings. | Writes `evagix.toml`; refuses an existing file by default. | `--force`, `--profile` | `0` success; `1` write/config failure. | No JSON output. |
| `evagix audit .` | Emit a lightweight strict governance audit plus readiness summary. | Read-only unless `--output` is supplied. | `--format text\|json`, `--output`, `--force`, `--profile` | `0` only when governance and readiness pass; `1` when either fails or output is guarded. | Stable; exposes `governance_ok`, `readiness_ok`, and `overall_ok`. |
| `evagix mcp .` | Detect common MCP configuration files without claiming a security audit. | Read-only. | `--format text\|json` | `0` successful detection; nonzero on operational failure. | Preview, not schema-backed. |
| `evagix context-pack .` | Print a source-grounded context summary. | Read-only; prints to stdout. | None. | `0` success; operational failures remain nonzero. | No JSON mode. |
| `evagix prepare . --plan` | Print an experimental repository preparation plan. | Read-only; does not write project files. | `--plan` is required. | `0` plan rendered; `2` unsupported invocation without `--plan`. | No JSON mode. |
| `evagix fix <code> .` / `evagix fix . --plan` | Preview a registered remediation or a repository-level fix plan. | Dry-run by default; writes only with `--apply`. | `--plan`, `--apply`, `--force`, `--fail-under` | `0` plan/apply success; `1` guarded write failure; `2` missing finding code. | No JSON mode. |

## Machine-readable contract stability

Stable JSON outputs are listed in the stable schema table in [Schemas](schemas.md); each has a packaged JSON Schema and an executable contract test. Preview contracts are listed separately and may evolve before a stable release. Their packaged schemas describe the current output, not a promise of stability. Pin the preview version when consuming those reports.
