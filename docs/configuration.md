# Configuration

This page documents `evagix.toml`, profiles, targets, policy thresholds, ignores, and command overrides.

## Policy config

Create a config:

```bash
evagix init . --profile ai-service --profile python-backend
```

Example `evagix.toml`:

```toml
[targets]
universal_md = true
universal_json = true
agents = true
claude = false
gemini = false
cursor = false
copilot = false
windsurf = false

# Optional universal exports/adapters:
# agent_brief = true
# safety_policy = true
# repo_map = true
# agent_tasks = true
# continue = true
# cline = true
# roo = true
# aider = true
# openhands = true
# generic = true

# Optional custom output for custom agents or local LLM wrappers.
# [[targets.custom]]
# name = "local_agent"
# path = ".evagix/local-agent.json"
# format = "json"
# include = ["facts", "commands", "risks", "policies", "repo_map"]
# `include` filters content sections only. Evagix always preserves
# ownership metadata and fingerprints required for safe, idempotent updates.

[profiles]
profiles = ["ai-service", "python-backend"]

[policy]
fail_on_stale = true
fail_under = 85
# Optional; default false. When true, doctor reports missing .evagix onboarding reports.
require_onboarding_pack = false
ignore_findings = ["missing-typecheck"]

[severity]
missing-ci = "error"
missing-llm-eval = "warning"

[commands]
# These replace auto-detected commands with repo-specific truth.
test = "make test"
lint = "make lint"
smoke = "python -m scripts.smoke"
eval = "python -m scripts.eval_ai_context"

[ignore]
# Reduce scanner noise from archived, vendor, or generated areas.
paths = ["archive/", "vendor/"]

[readme_audit]
# Real claims accepted by maintainers stay visible as waived and reduce the score.
waive_claims = ["enterprise-ready"]
# `ignore_claims` remains a deprecated compatibility alias for `waive_claims`.

[rules]
general = [
  "Keep API and retrieval behavior backward compatible unless explicitly requested."
]
forbidden = [
  "Do not regenerate embeddings or reset vector indexes without explicit approval."
]
```

Built-in profiles:

```bash
evagix profiles
evagix profiles ai-service
```

- `python-backend`
- `ai-service`
- `ml-dashboard`
- `frontend-app`
- `polyglot-monorepo`
- `infra-heavy`

## Context exports and targets

By default, `evagix compile .` writes only the universal Evagix-managed exports:

| Target | Output |
|---|---|
| `universal_md` | `.evagix/context.md` |
| `universal_json` | `.evagix/context.json` |

All other built-in targets are opt-in:

| Target | Output |
|---|---|
| `agent_brief` | `.evagix/agent-brief.md` |
| `safety_policy` | `.evagix/safety-policy.md` |
| `repo_map` | `.evagix/repo-map.md` |
| `agent_tasks` | `.agent_tasks/README.md` |
| `agents` | `AGENTS.md` |
| `claude` | `CLAUDE.md` |
| `gemini` | `GEMINI.md` |
| `cursor` | `.cursor/rules/project.mdc` |
| `copilot` | `.github/copilot-instructions.md` |
| `windsurf` | `.windsurf/rules/evagix.md` |
| `continue` | `.continue/rules/evagix.md` |
| `cline` | `.clinerules` |
| `roo` | `.roo/rules/evagix.md` |
| `aider` | `CONVENTIONS.md` |
| `openhands` | `.openhands/skills/repository/SKILL.md` |
| `generic` | `GENERIC_EVAGIX.md` |

The `agents` target writes `AGENTS.md` for OpenAI Codex and other coding agents that support the AGENTS.md convention. Evagix does not provide a built-in `codex` target or generate `CODEX.md` as a default instruction file.

List or inspect targets and generate only the exports a repository uses:

```bash
evagix targets list
evagix targets show agents
evagix compile . --target agents
evagix compile . --target claude --target gemini
```

Enable or disable built-in targets in `[targets]`, as shown above. Custom targets use `[[targets.custom]]` and may select content sections with `include`; Evagix always preserves the ownership metadata required for safe updates.

Generated exports include an ownership marker, source fingerprint, and content digest. The last successful digest for each generated target is stored in `.evagix/integrity.json`. `evagix check .` can therefore report repository drift and manual modification independently. Missing opt-in files do not fail a repository unless they are explicitly configured or requested.

Evagix does not overwrite user-owned files without an explicit supported force option. A file without valid Evagix ownership metadata remains external and is not reported as a healthy generated target.

The optional `agent_tasks` target writes reusable task templates under `.agent_tasks/`:

```bash
evagix compile . --target agent_tasks
```

Those templates cover bug fixes, refactoring, features, tests, and security review using the same governed repository facts as the other context exports.

### Custom target ownership

Configured output paths are treated as Evagix-managed only when they retain the generated marker, source fingerprint, and content-digest metadata. For JSON targets, `include` can remove optional content sections, but it never removes ownership metadata such as `_evagix_generated`, `_evagix_fingerprint`, `_evagix_content_digest`, `schema_version`, `tool`, `repository`, and `fingerprint`. The source fingerprint detects repository drift; the content digest detects manual changes to the last generated body. A target can therefore be reported as both stale and tampered. This keeps repeated `compile`, `sync`, and `check` operations deterministic and idempotent.

If a configured path already contains user-owned content without Evagix ownership metadata, `check` fails instead of reporting a misleading success. Move the user-owned file, choose another target path, or explicitly review and regenerate it before using that path as a managed target.

---


### README exclusions and waivers

Evagix distinguishes text that is not a repository claim from a real claim accepted by policy:

- `<!-- evagix:audit-ignore-start -->` / `<!-- evagix:audit-ignore-end -->` excludes documentation examples and quoted material from claim extraction.
- `[readme_audit].waive_claims` keeps matching real claims in every report with verdict `waived`; waived claims are not counted as supported and reduce the static-evidence score.
- The legacy `ignore_claims` key remains accepted as a compatibility alias, but it has the same visible waiver semantics and no longer hides claims silently.

Use exclusions only for non-claims. Use waivers for genuine claims that require an explicit maintainer decision.

### Configured command safety

Every command that can enter generated agent context is checked before `compile` or `sync` writes files. Clearly destructive commands and direct download-and-execute pipelines are blocked. Ambiguous guidance remains reviewable through findings rather than being treated as verified project truth.

## Onboarding pack policy

By default, Evagix treats the generated onboarding pack as optional. Repositories can generate `.evagix/context.md`, `.evagix/context.json`, and reports such as `.evagix/summary.md`, `.evagix/report.json`, and `.evagix/scorecard.json` on demand with `evagix onboard .`.

Set `require_onboarding_pack = true` only when your repository policy requires those generated onboarding reports to be committed:

```toml
[policy]
require_onboarding_pack = true
```

With this policy enabled, `doctor` reports `missing-onboarding-pack` when `AGENTS.md` exists but the onboarding pack is incomplete.
