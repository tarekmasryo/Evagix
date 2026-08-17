# Command guide

Evagix has several commands because it supports repository inspection, generated-context governance, README evidence checks, and PR risk review. Most users only need a small path first.

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

| Group | Commands |
| --- | --- |
| Inspect | `evagix scan`, `evagix suggest`, `evagix profiles`, `evagix targets`, `evagix policy`, `evagix classify`, `evagix explain` |
| Generate and maintain | `evagix compile`, `evagix sync`, `evagix check`, `evagix onboard`, `evagix baseline`, `evagix diff`, `evagix init`, `evagix init-ci`, `evagix scoped` |
| Readiness and reports | `evagix doctor`, `evagix report`, `evagix readme-audit`, `evagix decide`, `evagix plan`, `evagix drift`, `evagix eval-context`, `evagix evidence`, `evagix audit` |
| Preview and experimental | `evagix agents`, `evagix prepare`, `evagix context-pack`, `evagix mcp` |
| Git-aware review | `evagix changed`, `evagix pr-risk` |
| Remediation | `evagix fix` |

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
evagix init-ci . --install-mode github --repo tarekmasryo/Evagix --ref v0.1.0
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
    rev: v0.1.0
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

### `--strict` versus failure policy

`--strict` enables stricter evaluation. It does not always fail CI by itself. Use `--fail-under` or `--fail-on` to define the failure policy explicitly.

One safety exception is deliberate: `readme-audit --strict` exits `1` when README analysis is truncated, invalid UTF-8, or fails to read. A partial or unreadable file cannot support a trustworthy clean result. Non-strict mode still emits the incomplete finding but remains reporting-only unless an explicit failure policy selects it.

External or missing agent context is deliberately unscored. JSON reports use `score: null`, an explicit `score_type`, and `management: external|missing`; Markdown reports show `N/A (unscored)`. `eval-context --fail-under` exits `1` for an unscored report because no structural score exists to satisfy the threshold.

## Exit-code contract

Evagix uses a small, stable process-exit contract for automation:

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

These commands are useful for staged adoption and early feedback. Preview and experimental JSON is not a stable public schema unless `docs/schemas.md` lists it.

| Command | Purpose | Read/write behavior | Important flags | Exit codes | JSON stability |
| --- | --- | --- | --- | --- | --- |
| `evagix baseline .` | Create a staged-adoption configuration from current non-error findings. | Writes `evagix.toml`; refuses an existing file by default. | `--force`, `--profile` | `0` success; `1` write/config failure. | No JSON output. |
| `evagix audit .` | Emit a lightweight strict governance audit plus readiness summary. | Read-only unless `--output` is supplied. | `--format text\|json`, `--output`, `--force`, `--profile` | `0` only when governance and readiness pass; `1` when either fails or output is guarded. | Stable; exposes `governance_ok`, `readiness_ok`, and `overall_ok`. |
| `evagix mcp .` | Detect common MCP configuration files without claiming a security audit. | Read-only. | `--format text\|json` | `0` successful detection; nonzero on operational failure. | Preview, not schema-backed. |
| `evagix context-pack .` | Print a source-grounded context summary. | Read-only; prints to stdout. | None. | `0` success; operational failures remain nonzero. | No JSON mode. |
| `evagix prepare . --plan` | Print an experimental repository preparation plan. | Read-only; never writes project files in v0.1.0. | `--plan` is required. | `0` plan rendered; `2` unsupported invocation without `--plan`. | No JSON mode. |
| `evagix fix <code> .` / `evagix fix . --plan` | Preview a registered remediation or a repository-level fix plan. | Dry-run by default; writes only with `--apply`. | `--plan`, `--apply`, `--force`, `--fail-under` | `0` plan/apply success; `1` guarded write failure; `2` missing finding code. | No JSON mode. |

## Machine-readable contract stability

Stable JSON outputs are the commands listed in `docs/schemas.md`; each has a packaged JSON Schema and an executable contract test. A preview or experimental command is not a stable machine-readable contract merely because it can emit JSON. Such output may evolve until it is promoted by adding a packaged schema, documentation, and contract coverage.
