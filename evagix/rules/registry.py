from __future__ import annotations

from collections.abc import Iterable

from evagix.rules.models import Confidence, RuleDefinition, Severity
from evagix.rules.readme_source import README_SOURCE_RULES
from evagix.rules.static_rules import STATIC_RULE_SPECS

DEFAULT_RULES: dict[str, RuleDefinition] = {}


def _anchor(rule_id: str) -> str:
    return rule_id.lower().replace("_", "-").replace(".", "-").replace("/", "-")


def register_rule(rule: RuleDefinition) -> RuleDefinition:
    if rule.id in DEFAULT_RULES:
        raise ValueError(f"Duplicate Evagix rule id: {rule.id}")
    return DEFAULT_RULES.setdefault(rule.id, rule)


def get_rule(rule_id: str) -> RuleDefinition | None:
    return DEFAULT_RULES.get(rule_id)


def iter_rules() -> Iterable[RuleDefinition]:
    return tuple(DEFAULT_RULES.values())


def _rule(
    rule_id: str,
    title: str,
    category: str,
    severity: Severity,
    description: str,
    remediation: str,
    *,
    confidence: Confidence = "high",
    can_fail_ci: bool = True,
    docs_anchor: str | None = None,
) -> RuleDefinition:
    return RuleDefinition(
        id=rule_id,
        title=title,
        category=category,
        severity=severity,
        confidence=confidence,
        description=description,
        remediation=remediation,
        can_fail_ci=can_fail_ci,
        docs_anchor=docs_anchor or _anchor(rule_id),
    )


def _seed_static_rules() -> None:
    for rule_id, title, category, severity, description, remediation in STATIC_RULE_SPECS:
        confidence: Confidence = "medium" if rule_id == "PROMPT_INJECTION_RISK" else "high"
        register_rule(
            _rule(
                rule_id,
                title,
                category,
                severity,
                description,
                remediation,
                confidence=confidence,
            )
        )


def _seed_generated_context_rules() -> None:
    generated_rules: list[tuple[str, str, Severity, str]] = [
        (
            "generated-context-drift",
            "Generated context is stale",
            "high",
            "Regenerate Evagix-managed context with `evagix sync . --plan` or `evagix compile .`.",
        ),
        (
            "generated-context-tampered",
            "Generated context was manually modified",
            "high",
            "Regenerate the file or deliberately convert it to user-owned context.",
        ),
        (
            "EVAGIX_GENERATED_TARGET_TAMPERED",
            "Generated context target was manually modified",
            "high",
            "Regenerate the target or convert it deliberately to user-owned context.",
        ),
        (
            "generated-context-missing",
            "Configured generated context target is missing",
            "medium",
            "Run `evagix compile .` for the configured targets.",
        ),
        (
            "generated-context-unmanaged",
            "Configured context target is not Evagix-managed",
            "high",
            "Move the user-owned file, choose a different target path, or review and regenerate it explicitly.",
        ),
        (
            "generated-context-truncated",
            "Generated context verification was truncated",
            "high",
            "Reduce or split oversized generated targets so Evagix can verify their complete content.",
        ),
        (
            "generated-context-invalid-encoding",
            "Generated context is not valid UTF-8",
            "high",
            "Convert the generated target to valid UTF-8, review it, and rerun Evagix verification.",
        ),
        (
            "missing-target",
            "Optional generated context target is missing",
            "info",
            "Generate the optional target only if that workflow is intentionally adopted.",
        ),
        (
            "MISSING_OPTIONAL_AGENT_FILE",
            "Optional agent-context file is missing",
            "info",
            "Add the optional vendor-specific file only if that workflow is intentionally adopted.",
        ),
        (
            "tampered-target",
            "Generated context target was manually modified",
            "high",
            "Regenerate the target or remove the generated marker if the file is intentionally user-owned.",
        ),
    ]
    for rule_id, title, severity, remediation in generated_rules:
        register_rule(
            _rule(
                rule_id,
                title,
                "generated_context",
                severity,
                "Evagix-managed context exports must stay fresh and trustworthy.",
                remediation,
                can_fail_ci=severity != "info",
            )
        )


def _seed_doctor_rules() -> None:
    doctor_rules: list[tuple[str, str, str, Severity, bool]] = [
        ("language-undetected", "No primary language detected", "repository", "medium", True),
        ("missing-install", "No install command detected", "commands", "medium", True),
        ("missing-test", "No test command detected", "commands", "high", True),
        ("inferred-install-command", "Install command is inferred", "commands", "medium", True),
        ("inferred-test-command", "Test command is inferred", "commands", "medium", True),
        ("missing-lint", "No lint command detected", "commands", "info", False),
        ("formatter-only-lint", "Lint command appears formatter-only", "commands", "info", False),
        ("missing-typecheck", "No typecheck command detected", "commands", "info", False),
        ("missing-ci", "No CI workflow detected", "ci", "medium", True),
        ("missing-readme", "No README detected", "documentation", "medium", True),
        ("ml-tools-undetected", "ML project lacks classified ML/data tools", "repository", "medium", True),
        ("missing-tests-folder", "No tests folder detected", "commands", "info", False),
        ("missing-backend-tests", "Backend project lacks tests", "commands", "medium", True),
        ("missing-migration-marker", "Database lacks migration evidence", "repository", "info", False),
        ("missing-app-run", "Dashboard project lacks run/dev command", "commands", "medium", True),
        ("missing-frontend-build", "Frontend project lacks build command", "commands", "medium", True),
        ("missing-frontend-typecheck", "TypeScript frontend lacks typecheck command", "commands", "info", False),
        ("frontend-install-not-deterministic", "Frontend install is not deterministic", "commands", "info", False),
        ("missing-llm-eval", "AI/Retrieval project lacks eval/smoke command", "commands", "info", False),
        ("readme-command-gap", "README does not document detected commands", "documentation", "info", False),
        (
            "readme-possible-stale-node-command",
            "README mentions Node command without Node evidence",
            "documentation",
            "info",
            False,
        ),
        ("readme-unsupported-claims", "README contains unsupported claims", "readme_evidence", "medium", True),
        ("readme-partial-claims", "README contains partially supported claims", "readme_evidence", "info", False),
        ("missing-onboarding-pack", "Evagix onboarding pack is incomplete", "generated_context", "info", False),
        ("risk-flags-detected", "Risk-sensitive files or folders detected", "repository", "info", False),
        ("database-runtime-unclear", "Database runtime or migration path is unclear", "repository", "info", False),
        ("env-file-present", "Local .env file detected", "safety", "medium", True),
        ("dev-tools-undetected", "No developer tools classified", "repository", "info", False),
    ]
    for rule_id, title, category, severity, can_fail_ci in doctor_rules:
        register_rule(
            _rule(
                rule_id,
                title,
                category,
                severity,
                "Doctor readiness finding produced from local repository evidence.",
                "Review the finding and update repository evidence, docs, or Evagix config intentionally.",
                can_fail_ci=can_fail_ci,
            )
        )


def _seed_audit_rules() -> None:
    audit_rules: list[tuple[str, str, str, Severity]] = [
        ("active-profiles", "Active repository profiles detected", "repository", "info"),
        ("scanner-warning", "Scanner warning", "repository", "medium"),
        ("risk-flag", "Risk-sensitive repository flag", "repository", "medium"),
        ("database-without-migrations", "Database detected without migration evidence", "repository", "medium"),
        ("llm-eval-gap", "AI/Retrieval project lacks eval/smoke command", "commands", "info"),
        ("nondeterministic-node-install", "Node install command is not deterministic", "commands", "info"),
        ("local-env-present", "Local .env-style file present", "safety", "medium"),
        ("python-supply-chain-audit-missing", "Python supply-chain audit tool missing", "safety", "info"),
        ("backend-security-scan-missing", "Backend security scan tool missing", "safety", "info"),
        ("terraform-runtime", "Terraform runtime-impacting files detected", "infrastructure", "medium"),
        ("kubernetes-runtime", "Kubernetes runtime-impacting files detected", "infrastructure", "medium"),
    ]
    for rule_id, title, category, severity in audit_rules:
        register_rule(
            _rule(
                rule_id,
                title,
                category,
                severity,
                "Lightweight governance audit finding.",
                "Review the repository workflow and add explicit validation or review notes where needed.",
                can_fail_ci=severity == "medium",
            )
        )


def _seed_agent_context_rules() -> None:
    agent_context_rules: list[tuple[str, str, Severity, bool]] = [
        ("agent-context.not-configured", "No agent context files found", "low", False),
        ("agent-context.unsafe-symlink", "Agent context path is a symlink", "high", True),
        ("agent-context.missing-fingerprint", "Generated context is missing fingerprint", "medium", True),
        ("agent-context.duplicated-instructions", "Repeated instruction text in agent files", "low", False),
        ("agent-context.overlong", "Agent context is unusually large", "medium", True),
        ("agent-context.scan-truncated", "Agent context safety scan was truncated", "high", True),
        ("agent-context.discovery-truncated", "Agent context discovery was truncated", "high", True),
    ]
    for rule_id, title, severity, can_fail_ci in agent_context_rules:
        register_rule(
            _rule(
                rule_id,
                title,
                "agent_context",
                severity,
                "Agent-facing context quality finding.",
                "Keep agent context focused, safe, generated when appropriate, and aligned with repository evidence.",
                can_fail_ci=can_fail_ci,
            )
        )
    for key in ["install", "test", "lint", "typecheck", "build"]:
        command_severity: Severity = "high" if key == "test" else "medium"
        register_rule(
            _rule(
                f"agent-context.missing-{key}",
                f"Agent context does not document {key} command",
                "agent_context",
                command_severity,
                "Agent context should document canonical validation commands when the repository supports or requires them.",
                "Document the canonical command or adjust repository policy so agents do not guess.",
                can_fail_ci=key == "test",
            )
        )
        register_rule(
            _rule(
                f"agent-context.conflicting-{key}-commands",
                f"Conflicting {key} commands found in agent context",
                "agent_context",
                command_severity,
                "Agent context files should not disagree about canonical validation commands.",
                "Keep one canonical command and remove stale alternatives.",
                can_fail_ci=True,
            )
        )


def _seed_safety_rules() -> None:
    dangerous = {
        "dangerous-command.rm-root": "Destructive recursive delete command detected",
        "dangerous-command.curl-pipe-shell": "Remote script piped into shell detected",
        "dangerous-command.chmod-777": "Unsafe recursive chmod detected",
        "dangerous-command.cat-env": "Command reads local .env file",
        "dangerous-command.ssh-key": "Command reads SSH key or config",
        "dangerous-command.print-env": "Command prints full environment",
        "dangerous-command.env-exfiltration": "Environment exfiltration pattern detected",
        "dangerous-command.docker-prune": "Forceful Docker prune command detected",
        "dangerous-command.package-script": "Task recipe expands to dangerous shell behavior",
        "dangerous-command.embedded-credential": "Command contains a literal credential",
        "dangerous-command.local-script": "Local validation script contains dangerous shell behavior",
        "dangerous-command.obfuscated-execution": "Opaque or encoded shell execution detected",
        "command-safety.scan-truncated": "Command safety scan was truncated",
        "command-safety.discovery-truncated": "Command safety discovery was truncated",
        "text.invalid-utf8": "Text file is not valid UTF-8",
    }
    for rule_id, title in dangerous.items():
        register_rule(
            _rule(
                rule_id,
                title,
                "safety",
                "high",
                "Commands that destroy data, read secrets, or exfiltrate environment data are unsafe for agent-facing context.",
                "Remove the command or rewrite it as defensive guidance with a safe alternative.",
                can_fail_ci=True,
            )
        )
    poisoning = {
        "context-poisoning.ignore-instructions": "Instruction asks agent to ignore previous instructions",
        "context-poisoning.reveal-secrets": "Instruction asks agent to reveal secrets",
        "context-poisoning.system-prompt": "Context references system or hidden prompts",
        "context-poisoning.exfiltrate": "Instruction may encourage exfiltration",
        "context-poisoning.bypass-safety": "Instruction asks agent to bypass safety controls",
        "context-poisoning.scan-truncated": "Context-poisoning scan was truncated",
        "context-poisoning.discovery-truncated": "Context-poisoning discovery was truncated",
    }
    for rule_id, title in poisoning.items():
        register_rule(
            _rule(
                rule_id,
                title,
                "agent_context",
                "high",
                "Agent-facing text should not attempt to override safety or reveal confidential data.",
                "Remove hostile instructions and keep negative safety guidance explicit.",
                confidence="medium",
                can_fail_ci=True,
            )
        )


def _seed_readme_claim_rules() -> None:
    for rule_id, title, severity, can_fail_ci in README_SOURCE_RULES:
        register_rule(
            _rule(
                rule_id,
                title,
                "readme_evidence",
                severity,
                "README conclusions are trustworthy only when the selected file can be read completely.",
                "Restore a complete UTF-8 README read, then rerun the audit.",
                can_fail_ci=can_fail_ci,
            )
        )
    claims = [
        "tested",
        "dockerized",
        "ci-cd",
        "fastapi",
        "ai-llm",
        "monitoring",
        "secure",
        "production-ready",
        "deployable",
        "agent-instructions",
        "cli-tool",
        "package-installable",
        "examples",
        "typed",
        "zero-dependencies",
        "repo-readiness",
    ]
    verdicts = ["unsupported", "weak_evidence", "manual_review_required", "partially_supported"]
    for claim in claims:
        for verdict in verdicts:
            readme_severity: Severity = "high" if verdict in {"unsupported", "manual_review_required"} else "medium"
            register_rule(
                _rule(
                    f"readme-evidence.{claim}.{verdict}",
                    f"README claim `{claim}` is {verdict.replace('_', ' ')}",
                    "readme_evidence",
                    readme_severity,
                    "README claims should be backed by local repository evidence.",
                    "Update README wording, add the missing evidence, or mark the capability as planned/unavailable.",
                    confidence="medium",
                    can_fail_ci=verdict in {"unsupported", "manual_review_required"},
                )
            )
    register_rule(
        _rule(
            "readme-evidence.claim-waived",
            "README claim is explicitly waived",
            "readme_evidence",
            "medium",
            "The claim remains visible but was accepted through repository policy without complete evidence.",
            "Add the missing evidence, narrow the wording, or remove the waiver after review.",
            confidence="medium",
            can_fail_ci=False,
        )
    )


def _seed() -> None:
    _seed_static_rules()
    _seed_generated_context_rules()
    _seed_doctor_rules()
    _seed_audit_rules()
    _seed_agent_context_rules()
    _seed_safety_rules()
    _seed_readme_claim_rules()


_seed()
