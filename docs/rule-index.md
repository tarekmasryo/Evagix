# Rule Reference

Browse Evagix's **165 public rules** by registry category, or jump directly to an exact finding ID with site search. The complete registry remains the canonical source for rule metadata and stable anchors.

## Browse by category

| Category | Rules | Covers |
| --- | ---: | --- |
| [Agent context](rules-reference.md#agent-context) | 27 | Agent instructions, conflicts, context poisoning, truncation, and unsafe guidance. |
| [CI](rules-reference.md#ci) | 1 | Presence of repository CI evidence. |
| [Commands](rules-reference.md#commands) | 16 | Install, test, lint, typecheck, build, run, and deterministic command evidence. |
| [Documentation](rules-reference.md#documentation) | 3 | README presence, command gaps, and stale command guidance. |
| [Generated context](rules-reference.md#generated-context) | 12 | Managed context ownership, freshness, drift, tampering, and onboarding targets. |
| [Infrastructure](rules-reference.md#infrastructure) | 2 | Kubernetes and Terraform runtime claims. |
| [README evidence](rules-reference.md#readme-evidence) | 74 | Claim-to-evidence validation for documented capabilities and repository readiness. |
| [Repository](rules-reference.md#repository) | 10 | Repository structure, migrations, detected tooling, runtime ambiguity, and scan signals. |
| [Safety](rules-reference.md#safety) | 20 | Dangerous commands, environment exposure, supply-chain signals, and unsafe text. |

## Look up an exact rule

If you already have a finding code, open site search with `Ctrl` + `K` and enter the rule ID. Stable rule IDs and documentation anchors let the same finding resolve consistently across CLI output, reports, SARIF, waivers, and documentation.

Examples:

```text
missing-test
agent-context.dangerous-command
readme-evidence.production-ready.unsupported
dangerous-command.curl-pipe-shell
```

## Understand rule metadata

Every canonical rule entry documents the fields needed to interpret a finding, including category, severity, confidence, CI-failure behavior, what the rule checks, and rule-specific remediation or waiver guidance where relevant.

Start with [Rules](rules.md) for the severity model and finding behavior. Open the [Complete Rule Registry](rules-reference.md) when you need exact metadata, remediation guidance, or a stable rule anchor.
