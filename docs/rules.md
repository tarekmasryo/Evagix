# Evagix Rules

Verify what the repository claims, what local evidence proves, and what agent-facing context tells humans or coding agents to do.

This page is the human-readable rule overview. The full registry-aligned reference lives in [`docs/rules-reference.md`](rules-reference.md).

## Rule contract

Evagix uses stable rule/finding identifiers so CLI output, JSON reports, SARIF, docs, and waivers all speak the same language.

```text
finding.code == rule.id
SARIF ruleId == rule.id
docs/rules-reference.md anchor == rule.docs_anchor
```

Every emitted finding code should map to exactly one `RuleDefinition` in `evagix.rules.registry`. If a new finding is added without registry metadata, the registry-alignment tests fail.

## Severity model

| Severity | Meaning |
| --- | --- |
| `critical` | Dangerous enough to require immediate attention. |
| `high` | Strong evidence of stale, unsafe, or unsupported agent-facing behavior. |
| `medium` | Important evidence gap or maintainability risk. |
| `low` | Quality signal or adoption guidance. |
| `info` | Informational recommendation; should not fail default gates. |

## Categories

| Category | Rule count | Purpose |
| --- | ---: | --- |
| `agent_context` | 27 | Agent-facing instructions, command consistency, context size, and poisoning risk. |
| `ci` | 1 | CI evidence and repository validation workflows. |
| `commands` | 16 | Install/test/lint/typecheck/build command evidence. |
| `documentation` | 3 | README and documentation presence or freshness signals. |
| `generated_context` | 12 | Evagix-managed generated context freshness, tamper checks, and optional onboarding policy. |
| `infrastructure` | 2 | Runtime-impacting infrastructure evidence such as Kubernetes or Terraform. |
| `readme_evidence` | 74 | README claims matched against local repository evidence. |
| `repository` | 10 | General repository readiness, profiles, and governance signals. |
| `safety` | 20 | Dangerous commands, local secrets, and unsafe agent-facing patterns. |
| `Total` | 165 | Unique rules in the public registry. |

## How CI failure works

- Each rule has a default severity and `can_fail_ci` metadata.
- Commands such as `doctor`, `readme-audit`, and `eval-context` apply their own scoring and explicit `--fail-under` / `--fail-on` policy.
- Informational rules should guide cleanup without failing default gates.
- `policy.ignore_findings` should be used sparingly and documented.

## Generated-context policy

Evagix treats the full `.evagix/` onboarding pack as optional by default. Repositories can generate `.evagix/context.md`, `.evagix/context.json`, and reports such as `.evagix/summary.md`, `.evagix/report.json`, and `.evagix/scorecard.json` on demand with `evagix onboard .`.

Set `[policy].require_onboarding_pack = true` only when committed onboarding reports are part of your repository governance policy. When enabled, `missing-onboarding-pack` reports incomplete committed onboarding artifacts.

## Legacy IDs

Some uppercase IDs are retained for v0.1.x compatibility. New integrations should prefer canonical lower-case or dotted IDs. See [`docs/rules-reference.md#legacy-compatibility-aliases`](rules-reference.md#legacy-compatibility-aliases).

## Full reference

Open [`docs/rules-reference.md`](rules-reference.md) for every rule ID, category, severity, confidence, CI behavior, remediation, waiver guidance, and false-positive notes.
