# Evagix Schemas

Evagix emits stable, machine-readable JSON for CI, dashboards, and automation. The schema files live in `evagix/schemas/` and describe the public JSON contracts used by the main commands and generated artifacts.

## Available schema files

| Schema | Command / Output |
| --- | --- |
| `evagix/schemas/audit-report.schema.json` | `evagix audit --format json` reports. |
| `evagix/schemas/changed-report.schema.json` | `evagix changed --format json` reports. |
| `evagix/schemas/classification-report.schema.json` | `evagix classify --json` reports. |
| `evagix/schemas/context-eval.schema.json` | `evagix eval-context --format json` reports. |
| `evagix/schemas/decision-plan.schema.json` | `evagix decide/plan --format json` decision output. |
| `evagix/schemas/doctor-report.schema.json` | `evagix doctor --format json` readiness reports. |
| `evagix/schemas/drift-report.schema.json` | `evagix drift --format json` reports. |
| `evagix/schemas/evidence.schema.json` | `evagix evidence --format json` evidence/debug output. |
| `evagix/schemas/evagix-config.schema.json` | `evagix.toml` configuration shape. |
| `evagix/schemas/policy-report.schema.json` | `evagix policy --json` policy reports. |
| `evagix/schemas/pr-risk-report.schema.json` | `evagix pr-risk --format json` reports. |
| `evagix/schemas/readme-audit.schema.json` | `evagix readme-audit --format json` reports. |
| `evagix/schemas/scan-facts.schema.json` | `evagix scan --format json` repository facts. |

## Stability policy

- Schema additions should be backward-compatible where possible.
- Breaking schema changes should be documented in `CHANGELOG.md`.
- Finding codes should align with `evagix/rules/registry.py` and `docs/rules-reference.md`.
- SARIF rule IDs should use the same stable finding IDs documented in the rule registry.

## Validation

Evagix's contract tests execute every **stable, schema-backed** JSON CLI output listed above and validate the resulting payload against its packaged schema using JSON Schema Draft 2020-12. The suite covers successful reports, reports that return a nonzero policy exit code, and the installed schema paths documented here. Preview or experimental JSON surfaces are not stable contracts unless they are added to this table with a packaged schema and an executable contract test.

A schema file being syntactically valid is not sufficient: changes to a renderer and its schema must be released together, and the real CLI payload must continue to validate.

The README-audit contract includes source-completeness fields: `status`, `complete`, `chars_read`, `max_chars`, and structured `findings`. Consumers must not infer a clean audit from an empty `claims` array when `complete` is `false`. The incomplete statuses are `truncated`, `invalid_utf8`, and `read_error`; `missing` and `empty` remain distinct explicit source states.

The scan-facts contract uses `schema_version: "1.0"` and requires separate `languages`, `runtimes`, `package_managers`, `ci_platforms`, `infrastructure_tools`, and `container_platforms` fields. Command evidence uses a fixed confidence mapping (`high=0.90`, `medium=0.65`, `low=0.35`) and declares whether evidence is verified, configured, declared, or inferred.

The audit contract exposes `governance_ok`, `readiness_ok`, and `overall_ok`; legacy `ok` is equal to `overall_ok`. Context evaluation includes `score_type` and `management`, and permits `score: null` only for external or missing unmanaged context.
