# CI Integration
Evagix works best in CI when failure policy is explicit. A strict evaluation mode and a failing gate are related, but they are not the same thing.

## Minimal gate

A practical repository gate can combine generated-context drift, readiness, unsupported README claims, and high-risk agent-context findings:

```bash
evagix check .
evagix doctor . --strict --fail-under 80
evagix readme-audit . --strict --fail-on unsupported
evagix eval-context . --strict --fail-on high
```

Normal Evagix CI checks inspect repository evidence rather than executing the repository's test, lint, typecheck, build, or application commands. Keep those execution gates alongside Evagix so each layer validates the concern it owns.

## GitHub Actions

Create a downstream workflow with an explicit readiness threshold:

```bash
evagix init-ci . --fail-under 85
```

The command writes `.github/workflows/evagix.yml` and refuses to overwrite an existing workflow unless `--force` is supplied.

### Install modes

For a released PyPI package, use the generated PyPI mode or select it explicitly:

```bash
evagix init-ci . --install-mode pypi --package-version 0.1.0 --fail-under 85
```

To pin a specific GitHub repository and ref:

```bash
evagix init-ci . --install-mode github --repo tarekmasryo/Evagix --ref v0.1.0 --fail-under 85
```

Editable installation is intended for local Evagix development rather than downstream repositories:

```bash
evagix init-ci . --install-mode editable --fail-under 85
```

## Pre-commit

Evagix exposes downstream pre-commit hooks:

```yaml
repos:
  - repo: https://github.com/tarekmasryo/Evagix
    rev: v0.1.0
    hooks:
      - id: evagix-check
      - id: evagix-doctor
```

Pin a released tag rather than a moving branch for reproducible automation.

## Failure policy

`--strict` enables stricter evaluation; pipeline failure remains controlled by the command's explicit threshold or failure-policy flags.

Use the supported policy flags to define what should fail the pipeline:

- `doctor`: use `--fail-under` for a readiness threshold.
- `readme-audit`: use `--fail-on` for selected claim verdicts.
- `eval-context`: use `--fail-on` and/or `--fail-under` for context findings and score policy.

One deliberate safety exception exists: `readme-audit --strict` exits `1` when README analysis is truncated, invalid UTF-8, or fails to read, because incomplete source text cannot support a trustworthy clean result.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | The command completed and its configured policy gate passed. |
| `1` | A repository finding, readiness threshold, drift check, configured failure policy, or guarded output write failed. |
| `2` | Command-line usage was invalid, a requested mode is unsupported, or an experimental command was invoked outside its supported mode. |

Operational Python exceptions remain operational failures rather than being converted into a policy result.

## Generated workflow

The generated workflow checks drift without running `evagix sync .` first. This is intentional: a CI gate should detect stale generated context rather than silently regenerate it before validation.

On self-hosted GitHub Actions runners, keep the runner current enough for the Node.js runtime required by the pinned action versions.

## Related

- [CLI Reference](../commands.md) for full command semantics and machine-readable output stability.
- [Configuration](../configuration.md) for repository-specific thresholds, profiles, and policy.
- [Schemas](../schemas.md) for stable machine-readable contracts.
