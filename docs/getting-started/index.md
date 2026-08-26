# Quick Start

Get from installation to useful findings without changing project files.

## Install

Evagix requires Python 3.11 or newer.

```bash
python -m pip install evagix
evagix --version
```

## Run the first check

From the repository root:

```bash
evagix doctor .
```

`doctor` evaluates evidence-backed repository readiness and reports the findings that contribute to the result.

For stricter evaluation without defining a CI threshold yet:

```bash
evagix doctor . --strict
```

## Check specific surfaces

Use targeted commands when you need to inspect a particular surface:

```bash
evagix readme-audit .
evagix eval-context . --strict
```

- `readme-audit` checks README claims against local repository evidence.
- `eval-context` checks detected agent-facing instructions and managed context.

If the repository uses Evagix-managed generated context:

```bash
evagix check .
```

`check` validates generated-context freshness and drift. It is intentionally narrower than whole-repository readiness.

## Investigate a finding

Use the finding code printed by Evagix:

```bash
evagix explain <finding-code>
```

For machine-readable evidence:

```bash
evagix evidence . --format json
evagix scan . --format json
```

## Add policy only when needed

You do not need configuration for the first checks.

Create `evagix.toml` when you need repository-specific profiles, thresholds, targets, exclusions, command overrides, or waivers:

```bash
evagix init .
```

`init` writes a file. Review the generated policy before committing it.

## Next

- [Configuration](../configuration.md) — repository-specific policy.
- [CI Integration](../guides/ci.md) — thresholds and automation.
- [CLI Reference](../commands.md) — complete command map.
- [Rules](../rules.md) — severity, categories, and finding behavior.
