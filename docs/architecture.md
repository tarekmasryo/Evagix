# Evagix Architecture

Evagix is a local-first evidence/readiness gate for AI-assisted repositories.

The architecture is evidence-first:

```text
CLI command
  -> config loading + validation
  -> repository evidence collection
  -> rule/finding alignment
  -> readiness/context/README evaluation
  -> scoring and policy decisions
  -> reports and generated context rendering
  -> centralized final output redaction
  -> terminal, file, CI, and integration emission
```

## Design goals

- Keep all inspection deterministic and local-first.
- Keep public CLI behavior, JSON schemas, and exit codes stable.
- Separate evidence collection from decisions, scoring, and rendering.
- Prefer source-grounded `unknown` over guessing.
- Make new rules, ecosystems, reports, and agent targets fit clear extension points.

## Responsibility boundaries

| Layer | Responsibility | Must not do |
| --- | --- | --- |
| `commands/` | CLI parser registration and orchestration | Domain detection, scoring, rendering internals |
| `config.py`, `config_loader.py`, `config_models.py`, `config_validate.py` | Config loading, models, defaults, and validation | Repository scanning or report rendering |
| `scanning/` and `scanners/` | Collect local evidence and repository facts | Print CLI output or decide CI failure policy |
| `ecosystems/` | Ecosystem-specific evidence hints | Render reports or mutate generated files |
| `rules/` | Stable rule/finding identity and metadata | Read the filesystem directly |
| `readme/` | README parsing, claim detection, and evidence matching | Write files or render SARIF |
| `context/` | Agent-context discovery, checks, drift integration, and context scoring | Run project commands |
| `validation/` | Doctor/check/audit decisions and readiness policy | Generate markdown/SARIF directly where report helpers exist |
| `scoring/` | Score aggregation and thresholds | Collect repository evidence |
| `reports/` | JSON, Markdown, SARIF, annotations, PR comments | Decide severity or recompute scores |
| `rendering/` | Generated context rendering, target payloads, markers, fingerprints | Scan repositories |
| `core/` | Small shared IO/path/error/model/collection helpers | Domain-specific rules |
| `security/` | Deterministic credential redaction at output boundaries | Repository scanning policy or secret storage |
| `command_text.py` | Shared parsing of documented shell examples and fenced blocks | Ecosystem validation or policy decisions |
| `command_analysis.py` / `command_shell.py` | Cross-shell command normalization, token analysis, wrappers, and risk classification | Execute repository commands |
| `command_recipes.py` | Bounded inspection of supported task recipes and referenced local shell scripts | General-purpose build-system execution |
| `agent_context_registry.py` | Canonical supported agent-context paths shared by discovery and safety checks | Tool-specific rendering logic |

## Scanning and evidence boundaries

Repository traversal and safety-sensitive text reads are bounded. When a read or traversal is truncated, Evagix reports incomplete evidence instead of treating the inspected prefix as a complete result.

General scans skip common generated, vendor, cache, examples, demos, samples, and fixtures directories. Repositories that keep deployable code or real agent instructions in those locations should scan a narrower workspace whose governed content is not hidden by those low-signal defaults.

Evagix evaluates static repository evidence. Findings and scores do not prove runtime correctness, deployment success, external availability, or the absence of vulnerabilities. Command analysis is also static: inspected repository commands are never executed during scanning.

## Applied design patterns

Evagix uses a small set of explicit patterns where they reduce coupling:

- **Registry:** stable rule IDs, ecosystem profiles, command registration, and target metadata are declared centrally and consumed by focused layers.
- **Adapter:** generated context targets translate one shared evidence model into tool-specific formats without duplicating repository scanning.
- **Facade:** backward-compatible public modules expose explicit imports through `__all__`; wildcard re-exports are intentionally avoided.
- **Immutable value objects:** findings, evidence records, target definitions, and redaction rules normalize data at construction boundaries.
- **Pipeline:** scanning, evaluation, policy, rendering, and final output redaction remain separate deterministic stages.

These patterns are used selectively. Evagix avoids abstract factories, dependency-injection frameworks, or inheritance hierarchies where small pure functions and typed data models are clearer.

## Rule identity contract

Every emitted finding code should map to `evagix.rules.registry.RuleDefinition`.

```text
finding.code == rule.id
SARIF ruleId == rule.id
docs/rules-reference.md anchor == rule.docs_anchor
```

This prevents drift between CLI output, JSON, SARIF, docs, waivers, and scoring policy.

## Adding a new rule safely

1. Add or reuse evidence collection in `scanning/`, `readme/`, or `context/`.
2. Add a `RuleDefinition` in `evagix.rules.registry`.
3. Emit findings using that stable rule id.
4. Add/extend tests that prove the rule can produce the finding and that the rule id is registered.
5. Document the rule in `docs/rules-reference.md`, with a short overview in `docs/rules.md`.
6. Keep report rendering in `reports/` or `rendering/`, not inside evidence collectors.

## Adding a new ecosystem safely

1. Add ecosystem-specific hints under `evagix/ecosystems/` or `evagix/scanning/`.
2. Keep `scan_repo(...)` as the stable public orchestration entrypoint.
3. Add tests for positive evidence, missing evidence, invalid manifests, and command inference.
4. Do not let one ecosystem invalidate another in polyglot repositories.

## Adding a new generated context target safely

1. Add target metadata and renderer in `rendering/target_renderers.py` or related rendering modules.
2. Preserve generated markers, ownership metadata, and fingerprints even when output sections are filtered.
3. Add repeated compile/idempotency plus stale/tamper regression tests.
4. Fail validation for configured paths that exist as user-owned files instead of silently adopting them.

## Generated onboarding artifacts

Generated onboarding reports are optional and created on demand unless `[policy].require_onboarding_pack = true` is configured.


## Legacy rule IDs

Some uppercase rule IDs are retained as v0.1.x compatibility aliases. New integrations should prefer the canonical lower-case or dotted rule IDs documented in `docs/rules-reference.md`. Any ID migration requires an explicit compatibility plan.
