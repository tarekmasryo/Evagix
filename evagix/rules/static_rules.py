from __future__ import annotations

from evagix.rules.models import Severity

STATIC_RULE_SPECS: tuple[tuple[str, str, str, Severity, str, str], ...] = (
    (
        "README_COMMAND_UNSUPPORTED",
        "README command lacks repository evidence",
        "readme_evidence",
        "high",
        "A documented command should map to package scripts, manifests, CI, or ecosystem evidence.",
        "Update the command, add the missing script/config, or mark the command as unavailable.",
    ),
    (
        "readme-evidence.command.unsupported",
        "README command lacks repository evidence",
        "readme_evidence",
        "high",
        "A documented command should map to package scripts, manifests, CI, or ecosystem evidence.",
        "Update the command, add the missing script/config, or mark the command as unavailable.",
    ),
    (
        "agent-context.dangerous-command",
        "Agent context contains a dangerous command",
        "agent_context",
        "high",
        "Agent instruction files should not encourage destructive or exfiltration-prone commands.",
        "Remove the command or rewrite it as a defensive warning.",
    ),
    (
        "README_DOCKER_UNSUPPORTED",
        "README Docker claim lacks Docker evidence",
        "readme_evidence",
        "medium",
        "Docker support claims require a Dockerfile or Compose file.",
        "Remove or soften the claim, or add Dockerfile/Compose evidence.",
    ),
    (
        "README_TESTS_UNSUPPORTED",
        "README test claim lacks test evidence",
        "readme_evidence",
        "medium",
        "Test claims require tests, config, dependencies, or CI evidence.",
        "Add tests/configuration or document that tests are not available yet.",
    ),
    (
        "AGENT_CONTEXT_DANGEROUS_COMMAND",
        "Agent context contains a dangerous command",
        "agent_context",
        "high",
        "Agent instruction files should not encourage destructive or exfiltration-prone commands.",
        "Remove the command or rewrite it as a defensive warning.",
    ),
    (
        "PROMPT_INJECTION_RISK",
        "Prompt/context poisoning phrase detected",
        "agent_context",
        "high",
        "Repository text may attempt to override agent safety, reveal secrets, or exfiltrate data.",
        "Remove hostile instructions or clearly mark defensive guidance as a prohibition.",
    ),
    (
        "GENERATED_CONTEXT_DRIFT",
        "Generated agent context is stale",
        "generated_context",
        "high",
        "Generated Evagix targets should match current repository facts and configuration.",
        "Run `evagix sync . --plan`, review the diff, then regenerate context.",
    ),
    (
        "DANGEROUS_COMMAND_RM_RF_ROOT",
        "Destructive rm command detected",
        "safety",
        "critical",
        "Commands such as `rm -rf /` or `rm -rf $HOME` can destroy user data.",
        "Remove the command or keep it only in clearly defensive documentation.",
    ),
)
