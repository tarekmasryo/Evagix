# Evagix Rule Reference

This reference-style index mirrors the public rule registry; it is not a tutorial. It intentionally favors complete rule metadata over prose so CLI output, JSON reports, SARIF, docs, and waivers can refer to the same finding without drift.

For task-oriented usage, start with `README.md` and `docs/commands.md`; use this file when you need exact rule IDs, severities, or CI-failure behavior.

## Severity model

| Severity | Meaning |
| --- | --- |
| `critical` | Dangerous enough to require immediate attention. |
| `high` | Strong evidence of stale, unsafe, or unsupported agent-facing behavior. |
| `medium` | Important evidence gap or maintainability risk. |
| `low` | Quality signal or adoption guidance. |
| `info` | Informational recommendation; should not fail default gates. |

## Rule index

The index is grouped by registry category. Rule IDs and anchors remain stable so CLI output, JSON/SARIF reports, documentation, and waivers can link to the same finding.

### Agent context

| Rule ID | Category | Severity | Confidence | Can fail CI? |
| --- | --- | --- | --- | --- |
| [`agent-context.conflicting-build-commands`](#agent-context-conflicting-build-commands) | `agent_context` | `medium` | `high` | `true` |
| [`agent-context.conflicting-install-commands`](#agent-context-conflicting-install-commands) | `agent_context` | `medium` | `high` | `true` |
| [`agent-context.conflicting-lint-commands`](#agent-context-conflicting-lint-commands) | `agent_context` | `medium` | `high` | `true` |
| [`agent-context.conflicting-test-commands`](#agent-context-conflicting-test-commands) | `agent_context` | `high` | `high` | `true` |
| [`agent-context.conflicting-typecheck-commands`](#agent-context-conflicting-typecheck-commands) | `agent_context` | `medium` | `high` | `true` |
| [`agent-context.dangerous-command`](#agent-context-dangerous-command) | `agent_context` | `high` | `high` | `true` |
| [`agent-context.discovery-truncated`](#agent-context-discovery-truncated) | `agent_context` | `high` | `high` | `true` |
| [`agent-context.duplicated-instructions`](#agent-context-duplicated-instructions) | `agent_context` | `low` | `high` | `false` |
| [`agent-context.missing-build`](#agent-context-missing-build) | `agent_context` | `medium` | `high` | `false` |
| [`agent-context.missing-fingerprint`](#agent-context-missing-fingerprint) | `agent_context` | `medium` | `high` | `true` |
| [`agent-context.missing-install`](#agent-context-missing-install) | `agent_context` | `medium` | `high` | `false` |
| [`agent-context.missing-lint`](#agent-context-missing-lint) | `agent_context` | `medium` | `high` | `false` |
| [`agent-context.missing-test`](#agent-context-missing-test) | `agent_context` | `high` | `high` | `true` |
| [`agent-context.missing-typecheck`](#agent-context-missing-typecheck) | `agent_context` | `medium` | `high` | `false` |
| [`agent-context.not-configured`](#agent-context-not-configured) | `agent_context` | `low` | `high` | `false` |
| [`agent-context.overlong`](#agent-context-overlong) | `agent_context` | `medium` | `high` | `true` |
| [`agent-context.scan-truncated`](#agent-context-scan-truncated) | `agent_context` | `high` | `high` | `true` |
| [`agent-context.unsafe-symlink`](#agent-context-unsafe-symlink) | `agent_context` | `high` | `high` | `true` |
| [`AGENT_CONTEXT_DANGEROUS_COMMAND`](#agent-context-dangerous-command) | `agent_context` | `high` | `high` | `true` |
| [`context-poisoning.bypass-safety`](#context-poisoning-bypass-safety) | `agent_context` | `high` | `medium` | `true` |
| [`context-poisoning.discovery-truncated`](#context-poisoning-discovery-truncated) | `agent_context` | `high` | `medium` | `true` |
| [`context-poisoning.exfiltrate`](#context-poisoning-exfiltrate) | `agent_context` | `high` | `medium` | `true` |
| [`context-poisoning.ignore-instructions`](#context-poisoning-ignore-instructions) | `agent_context` | `high` | `medium` | `true` |
| [`context-poisoning.reveal-secrets`](#context-poisoning-reveal-secrets) | `agent_context` | `high` | `medium` | `true` |
| [`context-poisoning.scan-truncated`](#context-poisoning-scan-truncated) | `agent_context` | `high` | `medium` | `true` |
| [`context-poisoning.system-prompt`](#context-poisoning-system-prompt) | `agent_context` | `high` | `medium` | `true` |
| [`PROMPT_INJECTION_RISK`](#prompt-injection-risk) | `agent_context` | `high` | `medium` | `true` |

### CI

| Rule ID | Category | Severity | Confidence | Can fail CI? |
| --- | --- | --- | --- | --- |
| [`missing-ci`](#missing-ci) | `ci` | `medium` | `high` | `true` |

### Commands

| Rule ID | Category | Severity | Confidence | Can fail CI? |
| --- | --- | --- | --- | --- |
| [`formatter-only-lint`](#formatter-only-lint) | `commands` | `info` | `high` | `false` |
| [`frontend-install-not-deterministic`](#frontend-install-not-deterministic) | `commands` | `info` | `high` | `false` |
| [`inferred-install-command`](#inferred-install-command) | `commands` | `medium` | `high` | `true` |
| [`inferred-test-command`](#inferred-test-command) | `commands` | `medium` | `high` | `true` |
| [`llm-eval-gap`](#llm-eval-gap) | `commands` | `info` | `high` | `false` |
| [`missing-app-run`](#missing-app-run) | `commands` | `medium` | `high` | `true` |
| [`missing-backend-tests`](#missing-backend-tests) | `commands` | `medium` | `high` | `true` |
| [`missing-frontend-build`](#missing-frontend-build) | `commands` | `medium` | `high` | `true` |
| [`missing-frontend-typecheck`](#missing-frontend-typecheck) | `commands` | `info` | `high` | `false` |
| [`missing-install`](#missing-install) | `commands` | `medium` | `high` | `true` |
| [`missing-lint`](#missing-lint) | `commands` | `info` | `high` | `false` |
| [`missing-llm-eval`](#missing-llm-eval) | `commands` | `info` | `high` | `false` |
| [`missing-test`](#missing-test) | `commands` | `high` | `high` | `true` |
| [`missing-tests-folder`](#missing-tests-folder) | `commands` | `info` | `high` | `false` |
| [`missing-typecheck`](#missing-typecheck) | `commands` | `info` | `high` | `false` |
| [`nondeterministic-node-install`](#nondeterministic-node-install) | `commands` | `info` | `high` | `false` |

### Documentation

| Rule ID | Category | Severity | Confidence | Can fail CI? |
| --- | --- | --- | --- | --- |
| [`missing-readme`](#missing-readme) | `documentation` | `medium` | `high` | `true` |
| [`readme-command-gap`](#readme-command-gap) | `documentation` | `info` | `high` | `false` |
| [`readme-possible-stale-node-command`](#readme-possible-stale-node-command) | `documentation` | `info` | `high` | `false` |

### Generated context

| Rule ID | Category | Severity | Confidence | Can fail CI? |
| --- | --- | --- | --- | --- |
| [`generated-context-drift`](#generated-context-drift) | `generated_context` | `high` | `high` | `true` |
| [`generated-context-invalid-encoding`](#generated-context-invalid-encoding) | `generated_context` | `high` | `high` | `true` |
| [`generated-context-missing`](#generated-context-missing) | `generated_context` | `medium` | `high` | `true` |
| [`generated-context-unmanaged`](#generated-context-unmanaged) | `generated_context` | `high` | `high` | `true` |
| [`generated-context-truncated`](#generated-context-truncated) | `generated_context` | `high` | `high` | `true` |
| [`generated-context-tampered`](#generated-context-tampered) | `generated_context` | `high` | `high` | `true` |
| [`GENERATED_CONTEXT_DRIFT`](#generated-context-drift) | `generated_context` | `high` | `high` | `true` |
| [`EVAGIX_GENERATED_TARGET_TAMPERED`](#evagix-generated-target-tampered) | `generated_context` | `high` | `high` | `true` |
| [`missing-onboarding-pack`](#missing-onboarding-pack) | `generated_context` | `info` | `high` | `false` |
| [`missing-target`](#missing-target) | `generated_context` | `info` | `high` | `false` |
| [`MISSING_OPTIONAL_AGENT_FILE`](#missing-optional-agent-file) | `generated_context` | `info` | `high` | `false` |
| [`tampered-target`](#tampered-target) | `generated_context` | `high` | `high` | `true` |

### Infrastructure

| Rule ID | Category | Severity | Confidence | Can fail CI? |
| --- | --- | --- | --- | --- |
| [`kubernetes-runtime`](#kubernetes-runtime) | `infrastructure` | `medium` | `high` | `true` |
| [`terraform-runtime`](#terraform-runtime) | `infrastructure` | `medium` | `high` | `true` |

### README evidence

| Rule ID | Category | Severity | Confidence | Can fail CI? |
| --- | --- | --- | --- | --- |
| [`readme.empty`](#readme-empty) | `readme_evidence` | `medium` | `high` | `false` |
| [`readme.read-error`](#readme-read-error) | `readme_evidence` | `high` | `high` | `true` |
| [`readme.scan-truncated`](#readme-scan-truncated) | `readme_evidence` | `high` | `high` | `true` |
| [`readme-evidence.agent-instructions.manual_review_required`](#readme-evidence-agent-instructions-manual-review-required) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.agent-instructions.partially_supported`](#readme-evidence-agent-instructions-partially-supported) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.agent-instructions.unsupported`](#readme-evidence-agent-instructions-unsupported) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.agent-instructions.weak_evidence`](#readme-evidence-agent-instructions-weak-evidence) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.ai-llm.manual_review_required`](#readme-evidence-ai-llm-manual-review-required) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.ai-llm.partially_supported`](#readme-evidence-ai-llm-partially-supported) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.ai-llm.unsupported`](#readme-evidence-ai-llm-unsupported) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.ai-llm.weak_evidence`](#readme-evidence-ai-llm-weak-evidence) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.ci-cd.manual_review_required`](#readme-evidence-ci-cd-manual-review-required) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.ci-cd.partially_supported`](#readme-evidence-ci-cd-partially-supported) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.ci-cd.unsupported`](#readme-evidence-ci-cd-unsupported) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.ci-cd.weak_evidence`](#readme-evidence-ci-cd-weak-evidence) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.cli-tool.manual_review_required`](#readme-evidence-cli-tool-manual-review-required) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.cli-tool.partially_supported`](#readme-evidence-cli-tool-partially-supported) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.cli-tool.unsupported`](#readme-evidence-cli-tool-unsupported) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.cli-tool.weak_evidence`](#readme-evidence-cli-tool-weak-evidence) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.command.unsupported`](#readme-evidence-command-unsupported) | `readme_evidence` | `high` | `high` | `true` |
| [`readme-evidence.deployable.manual_review_required`](#readme-evidence-deployable-manual-review-required) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.deployable.partially_supported`](#readme-evidence-deployable-partially-supported) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.deployable.unsupported`](#readme-evidence-deployable-unsupported) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.deployable.weak_evidence`](#readme-evidence-deployable-weak-evidence) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.dockerized.manual_review_required`](#readme-evidence-dockerized-manual-review-required) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.dockerized.partially_supported`](#readme-evidence-dockerized-partially-supported) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.dockerized.unsupported`](#readme-evidence-dockerized-unsupported) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.dockerized.weak_evidence`](#readme-evidence-dockerized-weak-evidence) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.examples.manual_review_required`](#readme-evidence-examples-manual-review-required) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.examples.partially_supported`](#readme-evidence-examples-partially-supported) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.examples.unsupported`](#readme-evidence-examples-unsupported) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.examples.weak_evidence`](#readme-evidence-examples-weak-evidence) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.fastapi.manual_review_required`](#readme-evidence-fastapi-manual-review-required) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.fastapi.partially_supported`](#readme-evidence-fastapi-partially-supported) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.fastapi.unsupported`](#readme-evidence-fastapi-unsupported) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.fastapi.weak_evidence`](#readme-evidence-fastapi-weak-evidence) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.monitoring.manual_review_required`](#readme-evidence-monitoring-manual-review-required) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.monitoring.partially_supported`](#readme-evidence-monitoring-partially-supported) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.monitoring.unsupported`](#readme-evidence-monitoring-unsupported) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.monitoring.weak_evidence`](#readme-evidence-monitoring-weak-evidence) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.package-installable.manual_review_required`](#readme-evidence-package-installable-manual-review-required) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.package-installable.partially_supported`](#readme-evidence-package-installable-partially-supported) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.package-installable.unsupported`](#readme-evidence-package-installable-unsupported) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.package-installable.weak_evidence`](#readme-evidence-package-installable-weak-evidence) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.production-ready.manual_review_required`](#readme-evidence-production-ready-manual-review-required) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.production-ready.partially_supported`](#readme-evidence-production-ready-partially-supported) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.production-ready.unsupported`](#readme-evidence-production-ready-unsupported) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.production-ready.weak_evidence`](#readme-evidence-production-ready-weak-evidence) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.repo-readiness.manual_review_required`](#readme-evidence-repo-readiness-manual-review-required) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.repo-readiness.partially_supported`](#readme-evidence-repo-readiness-partially-supported) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.repo-readiness.unsupported`](#readme-evidence-repo-readiness-unsupported) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.repo-readiness.weak_evidence`](#readme-evidence-repo-readiness-weak-evidence) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.secure.manual_review_required`](#readme-evidence-secure-manual-review-required) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.secure.partially_supported`](#readme-evidence-secure-partially-supported) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.secure.unsupported`](#readme-evidence-secure-unsupported) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.secure.weak_evidence`](#readme-evidence-secure-weak-evidence) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.tested.manual_review_required`](#readme-evidence-tested-manual-review-required) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.tested.partially_supported`](#readme-evidence-tested-partially-supported) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.tested.unsupported`](#readme-evidence-tested-unsupported) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.tested.weak_evidence`](#readme-evidence-tested-weak-evidence) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.typed.manual_review_required`](#readme-evidence-typed-manual-review-required) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.typed.partially_supported`](#readme-evidence-typed-partially-supported) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.typed.unsupported`](#readme-evidence-typed-unsupported) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.typed.weak_evidence`](#readme-evidence-typed-weak-evidence) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.zero-dependencies.manual_review_required`](#readme-evidence-zero-dependencies-manual-review-required) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.zero-dependencies.partially_supported`](#readme-evidence-zero-dependencies-partially-supported) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.zero-dependencies.unsupported`](#readme-evidence-zero-dependencies-unsupported) | `readme_evidence` | `high` | `medium` | `true` |
| [`readme-evidence.zero-dependencies.weak_evidence`](#readme-evidence-zero-dependencies-weak-evidence) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-evidence.claim-waived`](#readme-evidence-claim-waived) | `readme_evidence` | `medium` | `medium` | `false` |
| [`readme-partial-claims`](#readme-partial-claims) | `readme_evidence` | `info` | `high` | `false` |
| [`readme-unsupported-claims`](#readme-unsupported-claims) | `readme_evidence` | `medium` | `high` | `true` |
| [`README_COMMAND_UNSUPPORTED`](#readme-command-unsupported) | `readme_evidence` | `high` | `high` | `true` |
| [`README_DOCKER_UNSUPPORTED`](#readme-docker-unsupported) | `readme_evidence` | `medium` | `high` | `true` |
| [`README_TESTS_UNSUPPORTED`](#readme-tests-unsupported) | `readme_evidence` | `medium` | `high` | `true` |

### Repository

| Rule ID | Category | Severity | Confidence | Can fail CI? |
| --- | --- | --- | --- | --- |
| [`active-profiles`](#active-profiles) | `repository` | `info` | `high` | `false` |
| [`database-runtime-unclear`](#database-runtime-unclear) | `repository` | `info` | `high` | `false` |
| [`database-without-migrations`](#database-without-migrations) | `repository` | `medium` | `high` | `true` |
| [`dev-tools-undetected`](#dev-tools-undetected) | `repository` | `info` | `high` | `false` |
| [`language-undetected`](#language-undetected) | `repository` | `medium` | `high` | `true` |
| [`missing-migration-marker`](#missing-migration-marker) | `repository` | `info` | `high` | `false` |
| [`ml-tools-undetected`](#ml-tools-undetected) | `repository` | `medium` | `high` | `true` |
| [`risk-flag`](#risk-flag) | `repository` | `medium` | `high` | `true` |
| [`risk-flags-detected`](#risk-flags-detected) | `repository` | `info` | `high` | `false` |
| [`scanner-warning`](#scanner-warning) | `repository` | `medium` | `high` | `true` |

### Safety

| Rule ID | Category | Severity | Confidence | Can fail CI? |
| --- | --- | --- | --- | --- |
| [`backend-security-scan-missing`](#backend-security-scan-missing) | `safety` | `info` | `high` | `false` |
| [`command-safety.discovery-truncated`](#command-safety-discovery-truncated) | `safety` | `high` | `high` | `true` |
| [`command-safety.scan-truncated`](#command-safety-scan-truncated) | `safety` | `high` | `high` | `true` |
| [`dangerous-command.cat-env`](#dangerous-command-cat-env) | `safety` | `high` | `high` | `true` |
| [`dangerous-command.chmod-777`](#dangerous-command-chmod-777) | `safety` | `high` | `high` | `true` |
| [`dangerous-command.curl-pipe-shell`](#dangerous-command-curl-pipe-shell) | `safety` | `high` | `high` | `true` |
| [`dangerous-command.docker-prune`](#dangerous-command-docker-prune) | `safety` | `high` | `high` | `true` |
| [`dangerous-command.embedded-credential`](#dangerous-command-embedded-credential) | `safety` | `high` | `high` | `true` |
| [`dangerous-command.env-exfiltration`](#dangerous-command-env-exfiltration) | `safety` | `high` | `high` | `true` |
| [`dangerous-command.local-script`](#dangerous-command-local-script) | `safety` | `high` | `high` | `true` |
| [`dangerous-command.obfuscated-execution`](#dangerous-command-obfuscated-execution) | `safety` | `high` | `high` | `true` |
| [`dangerous-command.package-script`](#dangerous-command-package-script) | `safety` | `high` | `high` | `true` |
| [`dangerous-command.print-env`](#dangerous-command-print-env) | `safety` | `high` | `high` | `true` |
| [`dangerous-command.rm-root`](#dangerous-command-rm-root) | `safety` | `high` | `high` | `true` |
| [`dangerous-command.ssh-key`](#dangerous-command-ssh-key) | `safety` | `high` | `high` | `true` |
| [`DANGEROUS_COMMAND_RM_RF_ROOT`](#dangerous-command-rm-rf-root) | `safety` | `critical` | `high` | `true` |
| [`env-file-present`](#env-file-present) | `safety` | `medium` | `high` | `true` |
| [`local-env-present`](#local-env-present) | `safety` | `medium` | `high` | `true` |
| [`python-supply-chain-audit-missing`](#python-supply-chain-audit-missing) | `safety` | `info` | `high` | `false` |
| [`text.invalid-utf8`](#text-invalid-utf8) | `safety` | `high` | `high` | `true` |

## Legacy compatibility aliases

The following uppercase IDs are retained for v0.1.x output compatibility. New integrations should prefer the canonical lower-case/dotted IDs when possible.

| Legacy ID | Canonical ID | Deprecated? |
| --- | --- | --- |
| `AGENT_CONTEXT_DANGEROUS_COMMAND` | `agent-context.dangerous-command` | `true` |
| `DANGEROUS_COMMAND_RM_RF_ROOT` | `dangerous-command.rm-root` | `true` |
| `GENERATED_CONTEXT_DRIFT` | `generated-context-drift` | `true` |
| `EVAGIX_GENERATED_TARGET_TAMPERED` | `generated-context-tampered` | `true` |
| `MISSING_OPTIONAL_AGENT_FILE` | `missing-target` | `true` |
| `PROMPT_INJECTION_RISK` | `context-poisoning.ignore-instructions` | `true` |
| `README_COMMAND_UNSUPPORTED` | `readme-evidence.command.unsupported` | `true` |
| `README_DOCKER_UNSUPPORTED` | `readme-evidence.dockerized.unsupported` | `true` |
| `README_TESTS_UNSUPPORTED` | `readme-evidence.tested.unsupported` | `true` |

## Entry conventions

Each rule entry keeps the rule-specific metadata and remediation needed to interpret a finding. Repeated generic boilerplate is intentionally omitted.

General guidance: treat findings as evidence prompts, fix the underlying repository evidence first, and use `policy.ignore_findings` only when a deliberate waiver is necessary. Rule-specific evidence, examples, waiver behavior, or false-positive notes are included when they add information beyond that default.

## Rules

<a id="agent-context-conflicting-build-commands"></a>
### `agent-context.conflicting-build-commands`

- **Title:** Conflicting build commands found in agent context
- **Category:** `agent_context`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Agent context files should not disagree about canonical validation commands.
- **How to fix:** Keep one canonical command and remove stale alternatives.

<a id="agent-context-conflicting-install-commands"></a>
### `agent-context.conflicting-install-commands`

- **Title:** Conflicting install commands found in agent context
- **Category:** `agent_context`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Agent context files should not disagree about canonical validation commands.
- **How to fix:** Keep one canonical command and remove stale alternatives.

<a id="agent-context-conflicting-lint-commands"></a>
### `agent-context.conflicting-lint-commands`

- **Title:** Conflicting lint commands found in agent context
- **Category:** `agent_context`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Agent context files should not disagree about canonical validation commands.
- **How to fix:** Keep one canonical command and remove stale alternatives.

<a id="agent-context-conflicting-test-commands"></a>
### `agent-context.conflicting-test-commands`

- **Title:** Conflicting test commands found in agent context
- **Category:** `agent_context`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Agent context files should not disagree about canonical validation commands.
- **How to fix:** Keep one canonical command and remove stale alternatives.

<a id="agent-context-conflicting-typecheck-commands"></a>
### `agent-context.conflicting-typecheck-commands`

- **Title:** Conflicting typecheck commands found in agent context
- **Category:** `agent_context`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Agent context files should not disagree about canonical validation commands.
- **How to fix:** Keep one canonical command and remove stale alternatives.

<a id="agent-context-dangerous-command"></a>
### `agent-context.dangerous-command`

- **Title:** Agent context contains a dangerous command
- **Category:** `agent_context`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Agent instruction files should not encourage destructive or exfiltration-prone commands.
- **How to fix:** Remove the command or rewrite it as a defensive warning.

<a id="agent-context-discovery-truncated"></a>
### `agent-context.discovery-truncated`

- **Title:** Agent context discovery was truncated
- **Category:** `agent_context`
- **Severity:** `high`
- **Confidence:** `high`
- **CI behavior:** Fails strict safety gates because the result is unsafe or incomplete.
- **Remediation:** Remove the unsafe value or make the complete file and traversal scope available for inspection.

<a id="agent-context-duplicated-instructions"></a>
### `agent-context.duplicated-instructions`

- **Title:** Repeated instruction text in agent files
- **Category:** `agent_context`
- **Severity:** `low`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Agent-facing context quality finding.
- **How to fix:** Keep agent context focused, safe, generated when appropriate, and aligned with repository evidence.

<a id="agent-context-missing-build"></a>
### `agent-context.missing-build`

- **Title:** Agent context does not document build command
- **Category:** `agent_context`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Agent context should document canonical validation commands when the repository supports or requires them.
- **How to fix:** Document the canonical command or adjust repository policy so agents do not guess.

<a id="agent-context-missing-fingerprint"></a>
### `agent-context.missing-fingerprint`

- **Title:** Generated context is missing fingerprint
- **Category:** `agent_context`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Agent-facing context quality finding.
- **How to fix:** Keep agent context focused, safe, generated when appropriate, and aligned with repository evidence.

<a id="agent-context-missing-install"></a>
### `agent-context.missing-install`

- **Title:** Agent context does not document install command
- **Category:** `agent_context`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Agent context should document canonical validation commands when the repository supports or requires them.
- **How to fix:** Document the canonical command or adjust repository policy so agents do not guess.

<a id="agent-context-missing-lint"></a>
### `agent-context.missing-lint`

- **Title:** Agent context does not document lint command
- **Category:** `agent_context`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Agent context should document canonical validation commands when the repository supports or requires them.
- **How to fix:** Document the canonical command or adjust repository policy so agents do not guess.

<a id="agent-context-missing-test"></a>
### `agent-context.missing-test`

- **Title:** Agent context does not document test command
- **Category:** `agent_context`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Agent context should document canonical validation commands when the repository supports or requires them.
- **How to fix:** Document the canonical command or adjust repository policy so agents do not guess.

<a id="agent-context-missing-typecheck"></a>
### `agent-context.missing-typecheck`

- **Title:** Agent context does not document typecheck command
- **Category:** `agent_context`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Agent context should document canonical validation commands when the repository supports or requires them.
- **How to fix:** Document the canonical command or adjust repository policy so agents do not guess.

<a id="agent-context-not-configured"></a>
### `agent-context.not-configured`

- **Title:** No agent context files found
- **Category:** `agent_context`
- **Severity:** `low`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Agent-facing context quality finding.
- **How to fix:** Keep agent context focused, safe, generated when appropriate, and aligned with repository evidence.

<a id="agent-context-overlong"></a>
### `agent-context.overlong`

- **Title:** Agent context is unusually large
- **Category:** `agent_context`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Agent-facing context quality finding.
- **How to fix:** Keep agent context focused, safe, generated when appropriate, and aligned with repository evidence.

<a id="agent-context-scan-truncated"></a>
### `agent-context.scan-truncated`

- **Title:** Agent context safety scan was truncated
- **Category:** `agent_context`
- **Severity:** `high`
- **Confidence:** `high`
- **CI behavior:** Fails strict safety gates because the result is unsafe or incomplete.
- **Remediation:** Remove the unsafe value or make the complete file and traversal scope available for inspection.

<a id="agent-context-unsafe-symlink"></a>
### `agent-context.unsafe-symlink`

- **Title:** Agent context path is a symlink
- **Category:** `agent_context`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Agent-facing context quality finding.
- **How to fix:** Keep agent context focused, safe, generated when appropriate, and aligned with repository evidence.

### `AGENT_CONTEXT_DANGEROUS_COMMAND`

- **Title:** Agent context contains a dangerous command
- **Category:** `agent_context`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Agent instruction files should not encourage destructive or exfiltration-prone commands.
- **How to fix:** Remove the command or rewrite it as a defensive warning.
- **Legacy status:** This uppercase ID is retained for v0.1.x output compatibility. Prefer the canonical ID shown in the alias table for new integrations when available.

<a id="context-poisoning-bypass-safety"></a>
### `context-poisoning.bypass-safety`

- **Title:** Instruction asks agent to bypass safety controls
- **Category:** `agent_context`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** Agent-facing text should not attempt to override safety or reveal confidential data.
- **How to fix:** Remove hostile instructions and keep negative safety guidance explicit.

<a id="context-poisoning-discovery-truncated"></a>
### `context-poisoning.discovery-truncated`

- **Title:** Context-poisoning discovery was truncated
- **Category:** `agent_context`
- **Severity:** `high`
- **Confidence:** `medium`
- **CI behavior:** Fails strict safety gates because the result is unsafe or incomplete.
- **Remediation:** Remove the unsafe value or make the complete file and traversal scope available for inspection.

<a id="context-poisoning-exfiltrate"></a>
### `context-poisoning.exfiltrate`

- **Title:** Instruction may encourage exfiltration
- **Category:** `agent_context`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** Agent-facing text should not attempt to override safety or reveal confidential data.
- **How to fix:** Remove hostile instructions and keep negative safety guidance explicit.

<a id="context-poisoning-ignore-instructions"></a>
### `context-poisoning.ignore-instructions`

- **Title:** Instruction asks agent to ignore previous instructions
- **Category:** `agent_context`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** Agent-facing text should not attempt to override safety or reveal confidential data.
- **How to fix:** Remove hostile instructions and keep negative safety guidance explicit.

<a id="context-poisoning-reveal-secrets"></a>
### `context-poisoning.reveal-secrets`

- **Title:** Instruction asks agent to reveal secrets
- **Category:** `agent_context`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** Agent-facing text should not attempt to override safety or reveal confidential data.
- **How to fix:** Remove hostile instructions and keep negative safety guidance explicit.

<a id="context-poisoning-scan-truncated"></a>
### `context-poisoning.scan-truncated`

- **Title:** Context-poisoning scan was truncated
- **Category:** `agent_context`
- **Severity:** `high`
- **Confidence:** `medium`
- **CI behavior:** Fails strict safety gates because the result is unsafe or incomplete.
- **Remediation:** Remove the unsafe value or make the complete file and traversal scope available for inspection.

<a id="context-poisoning-system-prompt"></a>
### `context-poisoning.system-prompt`

- **Title:** Context references system or hidden prompts
- **Category:** `agent_context`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** Agent-facing text should not attempt to override safety or reveal confidential data.
- **How to fix:** Remove hostile instructions and keep negative safety guidance explicit.

<a id="prompt-injection-risk"></a>
### `PROMPT_INJECTION_RISK`

- **Title:** Prompt/context poisoning phrase detected
- **Category:** `agent_context`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** Repository text may attempt to override agent safety, reveal secrets, or exfiltrate data.
- **How to fix:** Remove hostile instructions or clearly mark defensive guidance as a prohibition.
- **Legacy status:** This uppercase ID is retained for v0.1.x output compatibility. Prefer the canonical ID shown in the alias table for new integrations when available.

<a id="missing-ci"></a>
### `missing-ci`

- **Title:** No CI workflow detected
- **Category:** `ci`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="formatter-only-lint"></a>
### `formatter-only-lint`

- **Title:** Lint command appears formatter-only
- **Category:** `commands`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="frontend-install-not-deterministic"></a>
### `frontend-install-not-deterministic`

- **Title:** Frontend install is not deterministic
- **Category:** `commands`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="inferred-install-command"></a>
### `inferred-install-command`

- **Title:** Install command is inferred
- **Category:** `commands`
- **Severity:** `medium`
- **Confidence:** `high`
- **CI behavior:** Reduces readiness because inferred install evidence is not treated as fully verified.
- **Remediation:** Declare the canonical install command in project configuration, CI, a project script, or `evagix.toml`.

<a id="inferred-test-command"></a>
### `inferred-test-command`

- **Title:** Test command is inferred
- **Category:** `commands`
- **Severity:** `medium`
- **Confidence:** `high`
- **CI behavior:** Reduces readiness because inferred test evidence does not prove that a test suite exists.
- **Remediation:** Add real tests or test configuration and declare the canonical command in project configuration, CI, a project script, or `evagix.toml`.

<a id="llm-eval-gap"></a>
### `llm-eval-gap`

- **Title:** AI/Retrieval project lacks eval/smoke command
- **Category:** `commands`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Lightweight governance audit finding.
- **How to fix:** Review the repository workflow and add explicit validation or review notes where needed.

<a id="missing-app-run"></a>
### `missing-app-run`

- **Title:** Dashboard project lacks run/dev command
- **Category:** `commands`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="missing-backend-tests"></a>
### `missing-backend-tests`

- **Title:** Backend project lacks tests
- **Category:** `commands`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="missing-frontend-build"></a>
### `missing-frontend-build`

- **Title:** Frontend project lacks build command
- **Category:** `commands`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="missing-frontend-typecheck"></a>
### `missing-frontend-typecheck`

- **Title:** TypeScript frontend lacks typecheck command
- **Category:** `commands`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="missing-install"></a>
### `missing-install`

- **Title:** No install command detected
- **Category:** `commands`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="missing-lint"></a>
### `missing-lint`

- **Title:** No lint command detected
- **Category:** `commands`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="missing-llm-eval"></a>
### `missing-llm-eval`

- **Title:** AI/Retrieval project lacks eval/smoke command
- **Category:** `commands`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="missing-test"></a>
### `missing-test`

- **Title:** No test command detected
- **Category:** `commands`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="missing-tests-folder"></a>
### `missing-tests-folder`

- **Title:** No tests folder detected
- **Category:** `commands`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="missing-typecheck"></a>
### `missing-typecheck`

- **Title:** No typecheck command detected
- **Category:** `commands`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="nondeterministic-node-install"></a>
### `nondeterministic-node-install`

- **Title:** Node install command is not deterministic
- **Category:** `commands`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Lightweight governance audit finding.
- **How to fix:** Review the repository workflow and add explicit validation or review notes where needed.

<a id="missing-readme"></a>
### `missing-readme`

- **Title:** No README detected
- **Category:** `documentation`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="readme-command-gap"></a>
### `readme-command-gap`

- **Title:** README does not document detected commands
- **Category:** `documentation`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="readme-possible-stale-node-command"></a>
### `readme-possible-stale-node-command`

- **Title:** README mentions Node command without Node evidence
- **Category:** `documentation`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="generated-context-drift"></a>
### `generated-context-drift`

- **Title:** Generated context is stale
- **Category:** `generated_context`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Evagix-managed context exports must stay fresh and trustworthy.
- **How to fix:** Regenerate Evagix-managed context with `evagix sync . --plan` or `evagix compile .`.

<a id="generated-context-invalid-encoding"></a>
### `generated-context-invalid-encoding`

- **Title:** Generated context is not valid UTF-8
- **Category:** `generated_context`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** A managed generated-context target must decode completely as UTF-8 before Evagix can verify its fingerprint, ownership, or content.
- **How to fix:** Convert the target to valid UTF-8, review the resulting text, regenerate if appropriate, and rerun verification.
- **Evidence checked:** The complete byte stream of each configured generated-context target.
- **Bad example:** Invalid bytes are discarded and the remaining text is reported as fully verified.
- **Good example:** Invalid encoding produces an explicit incomplete-verification finding with no lossy decoding.
- **Waiver behavior:** Do not waive incomplete verification for managed agent-facing context.
- **False-positive notes:** The rule is deterministic and only fires when strict UTF-8 decoding fails.

<a id="generated-context-missing"></a>
### `generated-context-missing`

- **Title:** Configured generated context target is missing
- **Category:** `generated_context`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Evagix-managed context exports must stay fresh and trustworthy.
- **How to fix:** Run `evagix compile .` for the configured targets.

<a id="generated-context-unmanaged"></a>
### `generated-context-unmanaged`

- **Title:** Configured context target is not Evagix-managed
- **Category:** `generated_context`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** A configured context target exists but does not retain Evagix ownership metadata, so it cannot be updated or validated safely.
- **How to fix:** Move the user-owned file, choose a different target path, or review and regenerate it explicitly.
- **Evidence checked:** Configured generated-context paths and their ownership markers.
- **Bad example:** Evagix is configured to write a file that already exists as user-owned content.
- **Good example:** Configured targets retain the generated marker and current fingerprint.
- **Waiver behavior:** Prefer changing the target path or explicitly adopting the file rather than suppressing the finding.
- **False-positive notes:** A deliberately user-owned file should not also be configured as an Evagix-managed target.

<a id="generated-context-truncated"></a>
### `generated-context-truncated`

- **Title:** Generated context verification was truncated
- **Category:** `generated_context`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Evagix must read each managed context target completely before reporting it as verified.
- **How to fix:** Reduce or split oversized generated targets, then regenerate and verify them again.
- **Evidence checked:** The bounded read status for each Evagix-managed context file and integrity manifest.
- **Bad example:** A generated target exceeds the configured read limit, but the partial content is treated as fully verified.
- **Good example:** Every managed target fits inside the verification bound and is checked completely.
- **Waiver behavior:** Do not waive incomplete verification for agent-facing generated context.
- **False-positive notes:** This finding reports an explicit size boundary, not a heuristic content judgment.

<a id="generated-context-tampered"></a>
### `generated-context-tampered`

- **Title:** Generated context was manually modified
- **Category:** `generated_context`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Evagix-managed context exports must stay fresh and trustworthy.
- **How to fix:** Regenerate the file or deliberately convert it to user-owned context.

### `GENERATED_CONTEXT_DRIFT`

- **Title:** Generated agent context is stale
- **Category:** `generated_context`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Generated Evagix targets should match current repository facts and configuration.
- **How to fix:** Run `evagix sync . --plan`, review the diff, then regenerate context.
- **Legacy status:** This uppercase ID is retained for v0.1.x output compatibility. Prefer the canonical ID shown in the alias table for new integrations when available.

<a id="evagix-generated-target-tampered"></a>
### `EVAGIX_GENERATED_TARGET_TAMPERED`

- **Title:** Generated context target was manually modified
- **Category:** `generated_context`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Evagix-managed context exports must stay fresh and trustworthy.
- **How to fix:** Regenerate the target or convert it deliberately to user-owned context.
- **Legacy status:** This uppercase ID is retained for v0.1.x output compatibility. Prefer the canonical ID shown in the alias table for new integrations when available.

<a id="missing-onboarding-pack"></a>
### `missing-onboarding-pack`

- **Title:** Evagix onboarding pack is incomplete
- **Category:** `generated_context`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="missing-target"></a>
### `missing-target`

- **Title:** Optional generated context target is missing
- **Category:** `generated_context`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Evagix-managed context exports must stay fresh and trustworthy.
- **How to fix:** Generate the optional target only if that workflow is intentionally adopted.

<a id="missing-optional-agent-file"></a>
### `MISSING_OPTIONAL_AGENT_FILE`

- **Title:** Optional agent-context file is missing
- **Category:** `generated_context`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Evagix-managed context exports must stay fresh and trustworthy.
- **How to fix:** Add the optional vendor-specific file only if that workflow is intentionally adopted.
- **Legacy status:** This uppercase ID is retained for v0.1.x output compatibility. Prefer the canonical ID shown in the alias table for new integrations when available.

<a id="tampered-target"></a>
### `tampered-target`

- **Title:** Generated context target was manually modified
- **Category:** `generated_context`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Evagix-managed context exports must stay fresh and trustworthy.
- **How to fix:** Regenerate the target or remove the generated marker if the file is intentionally user-owned.

<a id="kubernetes-runtime"></a>
### `kubernetes-runtime`

- **Title:** Kubernetes runtime-impacting files detected
- **Category:** `infrastructure`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Lightweight governance audit finding.
- **How to fix:** Review the repository workflow and add explicit validation or review notes where needed.

<a id="terraform-runtime"></a>
### `terraform-runtime`

- **Title:** Terraform runtime-impacting files detected
- **Category:** `infrastructure`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Lightweight governance audit finding.
- **How to fix:** Review the repository workflow and add explicit validation or review notes where needed.

<a id="readme-empty"></a>
### `readme.empty`

- **Title:** README is empty
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** A selected README exists but contains no auditable text.
- **How to fix:** Document installation, usage, validation, and current limitations.
- **Evidence checked:** The complete selected README file.
- **Bad example:** An empty README is indistinguishable from a successful audit with no claims.
- **Good example:** The report exposes `status: empty` and a structured finding.
- **Waiver behavior:** Non-strict reporting remains advisory, but an empty README cannot receive a positive claim score.
- **False-positive notes:** Whitespace-only content is treated as text by the current reader and may produce no claims rather than this finding.

<a id="readme-read-error"></a>
### `readme.read-error`

- **Title:** README could not be read safely
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** The selected README must be a readable regular repository file before claim conclusions are trusted.
- **How to fix:** Restore read access, remove unsafe path indirection, and rerun the audit.
- **Evidence checked:** Safe bounded file access inside the repository trust boundary.
- **Bad example:** An access or path-safety error is swallowed and reported as no findings.
- **Good example:** Strict output fails with a path-only diagnostic and no raw exception leakage.
- **Waiver behavior:** Do not waive an incomplete evidence read in a release gate.
- **False-positive notes:** The diagnostic intentionally does not expose operating-system exception text.

<a id="readme-scan-truncated"></a>
### `readme.scan-truncated`

- **Title:** README analysis was truncated
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** README claim analysis must consume the full file within the documented 150,000-character bound.
- **How to fix:** Reduce or split the README, or deliberately raise and review the bounded limit before relying on the audit.
- **Evidence checked:** The selected README plus one character used only as a truncation probe.
- **Bad example:** A claim after the limit is missed and the inspected prefix is reported as clean.
- **Good example:** Prefix claims are still reported, the score is zero, and the audit is explicitly incomplete.
- **Waiver behavior:** Do not waive incomplete analysis in strict CI or release decisions.
- **False-positive notes:** The bound counts decoded Unicode characters rather than bytes and does not split multibyte characters.

<a id="readme-evidence-agent-instructions-manual-review-required"></a>
### `readme-evidence.agent-instructions.manual_review_required`

- **Title:** README claim `agent-instructions` is manual review required
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-agent-instructions-partially-supported"></a>
### `readme-evidence.agent-instructions.partially_supported`

- **Title:** README claim `agent-instructions` is partially supported
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-agent-instructions-unsupported"></a>
### `readme-evidence.agent-instructions.unsupported`

- **Title:** README claim `agent-instructions` is unsupported
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-agent-instructions-weak-evidence"></a>
### `readme-evidence.agent-instructions.weak_evidence`

- **Title:** README claim `agent-instructions` is weak evidence
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-ai-llm-manual-review-required"></a>
### `readme-evidence.ai-llm.manual_review_required`

- **Title:** README claim `ai-llm` is manual review required
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-ai-llm-partially-supported"></a>
### `readme-evidence.ai-llm.partially_supported`

- **Title:** README claim `ai-llm` is partially supported
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-ai-llm-unsupported"></a>
### `readme-evidence.ai-llm.unsupported`

- **Title:** README claim `ai-llm` is unsupported
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-ai-llm-weak-evidence"></a>
### `readme-evidence.ai-llm.weak_evidence`

- **Title:** README claim `ai-llm` is weak evidence
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-ci-cd-manual-review-required"></a>
### `readme-evidence.ci-cd.manual_review_required`

- **Title:** README claim `ci-cd` is manual review required
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-ci-cd-partially-supported"></a>
### `readme-evidence.ci-cd.partially_supported`

- **Title:** README claim `ci-cd` is partially supported
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-ci-cd-unsupported"></a>
### `readme-evidence.ci-cd.unsupported`

- **Title:** README claim `ci-cd` is unsupported
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-ci-cd-weak-evidence"></a>
### `readme-evidence.ci-cd.weak_evidence`

- **Title:** README claim `ci-cd` is weak evidence
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-cli-tool-manual-review-required"></a>
### `readme-evidence.cli-tool.manual_review_required`

- **Title:** README claim `cli-tool` is manual review required
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-cli-tool-partially-supported"></a>
### `readme-evidence.cli-tool.partially_supported`

- **Title:** README claim `cli-tool` is partially supported
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-cli-tool-unsupported"></a>
### `readme-evidence.cli-tool.unsupported`

- **Title:** README claim `cli-tool` is unsupported
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-cli-tool-weak-evidence"></a>
### `readme-evidence.cli-tool.weak_evidence`

- **Title:** README claim `cli-tool` is weak evidence
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-command-unsupported"></a>
### `readme-evidence.command.unsupported`

- **Title:** README command lacks repository evidence
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** A documented command should map to package scripts, manifests, CI, or ecosystem evidence.
- **How to fix:** Update the command, add the missing script/config, or mark the command as unavailable.

<a id="readme-evidence-deployable-manual-review-required"></a>
### `readme-evidence.deployable.manual_review_required`

- **Title:** README claim `deployable` is manual review required
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-deployable-partially-supported"></a>
### `readme-evidence.deployable.partially_supported`

- **Title:** README claim `deployable` is partially supported
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-deployable-unsupported"></a>
### `readme-evidence.deployable.unsupported`

- **Title:** README claim `deployable` is unsupported
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-deployable-weak-evidence"></a>
### `readme-evidence.deployable.weak_evidence`

- **Title:** README claim `deployable` is weak evidence
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-dockerized-manual-review-required"></a>
### `readme-evidence.dockerized.manual_review_required`

- **Title:** README claim `dockerized` is manual review required
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-dockerized-partially-supported"></a>
### `readme-evidence.dockerized.partially_supported`

- **Title:** README claim `dockerized` is partially supported
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-dockerized-unsupported"></a>
### `readme-evidence.dockerized.unsupported`

- **Title:** README claim `dockerized` is unsupported
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-dockerized-weak-evidence"></a>
### `readme-evidence.dockerized.weak_evidence`

- **Title:** README claim `dockerized` is weak evidence
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-examples-manual-review-required"></a>
### `readme-evidence.examples.manual_review_required`

- **Title:** README claim `examples` is manual review required
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-examples-partially-supported"></a>
### `readme-evidence.examples.partially_supported`

- **Title:** README claim `examples` is partially supported
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-examples-unsupported"></a>
### `readme-evidence.examples.unsupported`

- **Title:** README claim `examples` is unsupported
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-examples-weak-evidence"></a>
### `readme-evidence.examples.weak_evidence`

- **Title:** README claim `examples` is weak evidence
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-fastapi-manual-review-required"></a>
### `readme-evidence.fastapi.manual_review_required`

- **Title:** README claim `fastapi` is manual review required
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-fastapi-partially-supported"></a>
### `readme-evidence.fastapi.partially_supported`

- **Title:** README claim `fastapi` is partially supported
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-fastapi-unsupported"></a>
### `readme-evidence.fastapi.unsupported`

- **Title:** README claim `fastapi` is unsupported
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-fastapi-weak-evidence"></a>
### `readme-evidence.fastapi.weak_evidence`

- **Title:** README claim `fastapi` is weak evidence
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-monitoring-manual-review-required"></a>
### `readme-evidence.monitoring.manual_review_required`

- **Title:** README claim `monitoring` is manual review required
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-monitoring-partially-supported"></a>
### `readme-evidence.monitoring.partially_supported`

- **Title:** README claim `monitoring` is partially supported
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-monitoring-unsupported"></a>
### `readme-evidence.monitoring.unsupported`

- **Title:** README claim `monitoring` is unsupported
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-monitoring-weak-evidence"></a>
### `readme-evidence.monitoring.weak_evidence`

- **Title:** README claim `monitoring` is weak evidence
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-package-installable-manual-review-required"></a>
### `readme-evidence.package-installable.manual_review_required`

- **Title:** README claim `package-installable` is manual review required
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-package-installable-partially-supported"></a>
### `readme-evidence.package-installable.partially_supported`

- **Title:** README claim `package-installable` is partially supported
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-package-installable-unsupported"></a>
### `readme-evidence.package-installable.unsupported`

- **Title:** README claim `package-installable` is unsupported
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-package-installable-weak-evidence"></a>
### `readme-evidence.package-installable.weak_evidence`

- **Title:** README claim `package-installable` is weak evidence
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-production-ready-manual-review-required"></a>
### `readme-evidence.production-ready.manual_review_required`

- **Title:** README claim `production-ready` is manual review required
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-production-ready-partially-supported"></a>
### `readme-evidence.production-ready.partially_supported`

- **Title:** README claim `production-ready` is partially supported
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-production-ready-unsupported"></a>
### `readme-evidence.production-ready.unsupported`

- **Title:** README claim `production-ready` is unsupported
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-production-ready-weak-evidence"></a>
### `readme-evidence.production-ready.weak_evidence`

- **Title:** README claim `production-ready` is weak evidence
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-repo-readiness-manual-review-required"></a>
### `readme-evidence.repo-readiness.manual_review_required`

- **Title:** README claim `repo-readiness` is manual review required
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-repo-readiness-partially-supported"></a>
### `readme-evidence.repo-readiness.partially_supported`

- **Title:** README claim `repo-readiness` is partially supported
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-repo-readiness-unsupported"></a>
### `readme-evidence.repo-readiness.unsupported`

- **Title:** README claim `repo-readiness` is unsupported
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-repo-readiness-weak-evidence"></a>
### `readme-evidence.repo-readiness.weak_evidence`

- **Title:** README claim `repo-readiness` is weak evidence
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-secure-manual-review-required"></a>
### `readme-evidence.secure.manual_review_required`

- **Title:** README claim `secure` is manual review required
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-secure-partially-supported"></a>
### `readme-evidence.secure.partially_supported`

- **Title:** README claim `secure` is partially supported
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-secure-unsupported"></a>
### `readme-evidence.secure.unsupported`

- **Title:** README claim `secure` is unsupported
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-secure-weak-evidence"></a>
### `readme-evidence.secure.weak_evidence`

- **Title:** README claim `secure` is weak evidence
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-tested-manual-review-required"></a>
### `readme-evidence.tested.manual_review_required`

- **Title:** README claim `tested` is manual review required
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-tested-partially-supported"></a>
### `readme-evidence.tested.partially_supported`

- **Title:** README claim `tested` is partially supported
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-tested-unsupported"></a>
### `readme-evidence.tested.unsupported`

- **Title:** README claim `tested` is unsupported
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-tested-weak-evidence"></a>
### `readme-evidence.tested.weak_evidence`

- **Title:** README claim `tested` is weak evidence
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-typed-manual-review-required"></a>
### `readme-evidence.typed.manual_review_required`

- **Title:** README claim `typed` is manual review required
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-typed-partially-supported"></a>
### `readme-evidence.typed.partially_supported`

- **Title:** README claim `typed` is partially supported
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-typed-unsupported"></a>
### `readme-evidence.typed.unsupported`

- **Title:** README claim `typed` is unsupported
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-typed-weak-evidence"></a>
### `readme-evidence.typed.weak_evidence`

- **Title:** README claim `typed` is weak evidence
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-zero-dependencies-manual-review-required"></a>
### `readme-evidence.zero-dependencies.manual_review_required`

- **Title:** README claim `zero-dependencies` is manual review required
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-zero-dependencies-partially-supported"></a>
### `readme-evidence.zero-dependencies.partially_supported`

- **Title:** README claim `zero-dependencies` is partially supported
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-zero-dependencies-unsupported"></a>
### `readme-evidence.zero-dependencies.unsupported`

- **Title:** README claim `zero-dependencies` is unsupported
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `medium`
- **Can fail CI?** `true`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-zero-dependencies-weak-evidence"></a>
### `readme-evidence.zero-dependencies.weak_evidence`

- **Title:** README claim `zero-dependencies` is weak evidence
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** README claims should be backed by local repository evidence.
- **How to fix:** Update README wording, add the missing evidence, or mark the capability as planned/unavailable.

<a id="readme-evidence-claim-waived"></a>
### `readme-evidence.claim-waived`

- **Title:** README claim is explicitly waived
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `medium`
- **Can fail CI?** `false`
- **What it checks:** A detected README claim was accepted through explicit repository policy without complete supporting evidence.
- **How to fix:** Add the missing evidence, narrow the wording, or remove the waiver after review.
- **Evidence checked:** README claim text and `readme_audit.waive_claims` policy.
- **Bad example:** A high-trust claim is silently removed from reports through an ignore list.
- **Good example:** The claim remains visible as `waived`, includes the missing evidence, and reduces the audit score.
- **Waiver behavior:** This rule represents the waiver itself and is intentionally non-blocking unless a stricter external policy rejects waivers.
- **False-positive notes:** Documentation examples should use exclusion blocks rather than claim waivers.

<a id="readme-partial-claims"></a>
### `readme-partial-claims`

- **Title:** README contains partially supported claims
- **Category:** `readme_evidence`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="readme-unsupported-claims"></a>
### `readme-unsupported-claims`

- **Title:** README contains unsupported claims
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="readme-command-unsupported"></a>
### `README_COMMAND_UNSUPPORTED`

- **Title:** README command lacks repository evidence
- **Category:** `readme_evidence`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** A documented command should map to package scripts, manifests, CI, or ecosystem evidence.
- **How to fix:** Update the command, add the missing script/config, or mark the command as unavailable.
- **Legacy status:** This uppercase ID is retained for v0.1.x output compatibility. Prefer the canonical ID shown in the alias table for new integrations when available.

<a id="readme-docker-unsupported"></a>
### `README_DOCKER_UNSUPPORTED`

- **Title:** README Docker claim lacks Docker evidence
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Docker support claims require a Dockerfile or Compose file.
- **How to fix:** Remove or soften the claim, or add Dockerfile/Compose evidence.
- **Legacy status:** This uppercase ID is retained for v0.1.x output compatibility. Prefer the canonical ID shown in the alias table for new integrations when available.

<a id="readme-tests-unsupported"></a>
### `README_TESTS_UNSUPPORTED`

- **Title:** README test claim lacks test evidence
- **Category:** `readme_evidence`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Test claims require tests, config, dependencies, or CI evidence.
- **How to fix:** Add tests/configuration or document that tests are not available yet.
- **Legacy status:** This uppercase ID is retained for v0.1.x output compatibility. Prefer the canonical ID shown in the alias table for new integrations when available.

<a id="active-profiles"></a>
### `active-profiles`

- **Title:** Active repository profiles detected
- **Category:** `repository`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Lightweight governance audit finding.
- **How to fix:** Review the repository workflow and add explicit validation or review notes where needed.

<a id="database-runtime-unclear"></a>
### `database-runtime-unclear`

- **Title:** Database runtime or migration path is unclear
- **Category:** `repository`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="database-without-migrations"></a>
### `database-without-migrations`

- **Title:** Database detected without migration evidence
- **Category:** `repository`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Lightweight governance audit finding.
- **How to fix:** Review the repository workflow and add explicit validation or review notes where needed.

<a id="dev-tools-undetected"></a>
### `dev-tools-undetected`

- **Title:** No developer tools classified
- **Category:** `repository`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="language-undetected"></a>
### `language-undetected`

- **Title:** No primary language detected
- **Category:** `repository`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="missing-migration-marker"></a>
### `missing-migration-marker`

- **Title:** Database lacks migration evidence
- **Category:** `repository`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="ml-tools-undetected"></a>
### `ml-tools-undetected`

- **Title:** ML project lacks classified ML/data tools
- **Category:** `repository`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="risk-flag"></a>
### `risk-flag`

- **Title:** Risk-sensitive repository flag
- **Category:** `repository`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Lightweight governance audit finding.
- **How to fix:** Review the repository workflow and add explicit validation or review notes where needed.

<a id="risk-flags-detected"></a>
### `risk-flags-detected`

- **Title:** Risk-sensitive files or folders detected
- **Category:** `repository`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="scanner-warning"></a>
### `scanner-warning`

- **Title:** Scanner warning
- **Category:** `repository`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Lightweight governance audit finding.
- **How to fix:** Review the repository workflow and add explicit validation or review notes where needed.

<a id="backend-security-scan-missing"></a>
### `backend-security-scan-missing`

- **Title:** Backend security scan tool missing
- **Category:** `safety`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Lightweight governance audit finding.
- **How to fix:** Review the repository workflow and add explicit validation or review notes where needed.

<a id="command-safety-discovery-truncated"></a>
### `command-safety.discovery-truncated`

- **Title:** Command safety discovery was truncated
- **Category:** `safety`
- **Severity:** `high`
- **Confidence:** `high`
- **CI behavior:** Fails strict safety gates because the result is unsafe or incomplete.
- **Remediation:** Remove the unsafe value or make the complete file and traversal scope available for inspection.

<a id="command-safety-scan-truncated"></a>
### `command-safety.scan-truncated`

- **Title:** Command safety scan was truncated
- **Category:** `safety`
- **Severity:** `high`
- **Confidence:** `high`
- **CI behavior:** Fails strict safety gates because the result is unsafe or incomplete.
- **Remediation:** Remove the unsafe value or make the complete file and traversal scope available for inspection.

<a id="dangerous-command-cat-env"></a>
### `dangerous-command.cat-env`

- **Title:** Command reads local .env file
- **Category:** `safety`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Commands that destroy data, read secrets, or exfiltrate environment data are unsafe for agent-facing context.
- **How to fix:** Remove the command or rewrite it as defensive guidance with a safe alternative.

<a id="dangerous-command-chmod-777"></a>
### `dangerous-command.chmod-777`

- **Title:** Unsafe recursive chmod detected
- **Category:** `safety`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Commands that destroy data, read secrets, or exfiltrate environment data are unsafe for agent-facing context.
- **How to fix:** Remove the command or rewrite it as defensive guidance with a safe alternative.

<a id="dangerous-command-curl-pipe-shell"></a>
### `dangerous-command.curl-pipe-shell`

- **Title:** Remote script piped into shell detected
- **Category:** `safety`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Commands that destroy data, read secrets, or exfiltrate environment data are unsafe for agent-facing context.
- **How to fix:** Remove the command or rewrite it as defensive guidance with a safe alternative.

<a id="dangerous-command-docker-prune"></a>
### `dangerous-command.docker-prune`

- **Title:** Forceful Docker prune command detected
- **Category:** `safety`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Commands that destroy data, read secrets, or exfiltrate environment data are unsafe for agent-facing context.
- **How to fix:** Remove the command or rewrite it as defensive guidance with a safe alternative.

<a id="dangerous-command-embedded-credential"></a>
### `dangerous-command.embedded-credential`

- **Title:** Command contains a literal credential
- **Category:** `safety`
- **Severity:** `high`
- **Confidence:** `high`
- **CI behavior:** Fails strict safety gates because the result is unsafe or incomplete.
- **Remediation:** Remove the unsafe value or make the complete file and traversal scope available for inspection.

<a id="dangerous-command-env-exfiltration"></a>
### `dangerous-command.env-exfiltration`

- **Title:** Environment exfiltration pattern detected
- **Category:** `safety`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Commands that destroy data, read secrets, or exfiltrate environment data are unsafe for agent-facing context.
- **How to fix:** Remove the command or rewrite it as defensive guidance with a safe alternative.

<a id="dangerous-command-local-script"></a>
### `dangerous-command.local-script`

- **Title:** Local validation script contains dangerous shell behavior
- **Category:** `safety`
- **Severity:** `high`
- **Confidence:** `high`
- **CI behavior:** Fails strict safety gates before the script can be published to agent-facing context.
- **Remediation:** Remove the destructive or credential-exposing operation from the referenced local shell script.

<a id="dangerous-command-obfuscated-execution"></a>
### `dangerous-command.obfuscated-execution`

- **Title:** Opaque or encoded shell execution detected
- **Category:** `safety`
- **Severity:** `high`
- **Confidence:** `high`
- **CI behavior:** Fails agent-context generation because encoded commands cannot be reviewed reliably.
- **Remediation:** Replace encoded execution with a transparent, bounded project command that can be inspected.

<a id="dangerous-command-package-script"></a>
### `dangerous-command.package-script`

- **Title:** Task recipe expands to dangerous shell behavior
- **Category:** `safety`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Commands that destroy data, read secrets, or exfiltrate environment data are unsafe for agent-facing context.
- **How to fix:** Remove the command or rewrite it as defensive guidance with a safe alternative.

<a id="dangerous-command-print-env"></a>
### `dangerous-command.print-env`

- **Title:** Command prints full environment
- **Category:** `safety`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Commands that destroy data, read secrets, or exfiltrate environment data are unsafe for agent-facing context.
- **How to fix:** Remove the command or rewrite it as defensive guidance with a safe alternative.

<a id="dangerous-command-rm-root"></a>
### `dangerous-command.rm-root`

- **Title:** Destructive recursive delete command detected
- **Category:** `safety`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Commands that destroy data, read secrets, or exfiltrate environment data are unsafe for agent-facing context.
- **How to fix:** Remove the command or rewrite it as defensive guidance with a safe alternative.

<a id="dangerous-command-ssh-key"></a>
### `dangerous-command.ssh-key`

- **Title:** Command reads SSH key or config
- **Category:** `safety`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Commands that destroy data, read secrets, or exfiltrate environment data are unsafe for agent-facing context.
- **How to fix:** Remove the command or rewrite it as defensive guidance with a safe alternative.

<a id="dangerous-command-rm-rf-root"></a>
### `DANGEROUS_COMMAND_RM_RF_ROOT`

- **Title:** Destructive rm command detected
- **Category:** `safety`
- **Severity:** `critical`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Commands such as `rm -rf /` or `rm -rf $HOME` can destroy user data.
- **How to fix:** Remove the command or keep it only in clearly defensive documentation.
- **Legacy status:** This uppercase ID is retained for v0.1.x output compatibility. Prefer the canonical ID shown in the alias table for new integrations when available.

<a id="env-file-present"></a>
### `env-file-present`

- **Title:** Local .env file detected
- **Category:** `safety`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Doctor readiness finding produced from local repository evidence.
- **How to fix:** Review the finding and update repository evidence, docs, or Evagix config intentionally.

<a id="local-env-present"></a>
### `local-env-present`

- **Title:** Local .env-style file present
- **Category:** `safety`
- **Severity:** `medium`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Lightweight governance audit finding.
- **How to fix:** Review the repository workflow and add explicit validation or review notes where needed.

<a id="python-supply-chain-audit-missing"></a>
### `python-supply-chain-audit-missing`

- **Title:** Python supply-chain audit tool missing
- **Category:** `safety`
- **Severity:** `info`
- **Confidence:** `high`
- **Can fail CI?** `false`
- **What it checks:** Lightweight governance audit finding.
- **How to fix:** Review the repository workflow and add explicit validation or review notes where needed.

<a id="text-invalid-utf8"></a>
### `text.invalid-utf8`

- **Title:** Text file is not valid UTF-8
- **Category:** `safety`
- **Severity:** `high`
- **Confidence:** `high`
- **Can fail CI?** `true`
- **What it checks:** Safety- and evidence-sensitive text must decode completely before command, credential, or context-poisoning analysis is considered complete.
- **How to fix:** Convert the file to valid UTF-8 and rerun the relevant Evagix command.
- **Evidence checked:** Strict UTF-8 decoding of the bounded file content selected for safety analysis.
- **Bad example:** Invalid bytes are silently ignored and hidden content is omitted from analysis.
- **Good example:** Evagix fails closed with a path-only diagnostic and does not expose undecodable bytes.
- **Waiver behavior:** Treat this as incomplete safety evidence rather than a cosmetic encoding warning.
- **False-positive notes:** Binary files outside the supported text scope are not selected by this rule.
