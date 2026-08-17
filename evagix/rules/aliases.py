from __future__ import annotations

from collections.abc import Iterable

from evagix.rules.models import RuleAlias

LEGACY_RULE_ALIASES: dict[str, RuleAlias] = {
    "README_COMMAND_UNSUPPORTED": RuleAlias("README_COMMAND_UNSUPPORTED", "readme-evidence.command.unsupported"),
    "README_DOCKER_UNSUPPORTED": RuleAlias("README_DOCKER_UNSUPPORTED", "readme-evidence.dockerized.unsupported"),
    "README_TESTS_UNSUPPORTED": RuleAlias("README_TESTS_UNSUPPORTED", "readme-evidence.tested.unsupported"),
    "AGENT_CONTEXT_DANGEROUS_COMMAND": RuleAlias("AGENT_CONTEXT_DANGEROUS_COMMAND", "agent-context.dangerous-command"),
    "PROMPT_INJECTION_RISK": RuleAlias("PROMPT_INJECTION_RISK", "context-poisoning.ignore-instructions"),
    "GENERATED_CONTEXT_DRIFT": RuleAlias("GENERATED_CONTEXT_DRIFT", "generated-context-drift"),
    "DANGEROUS_COMMAND_RM_RF_ROOT": RuleAlias("DANGEROUS_COMMAND_RM_RF_ROOT", "dangerous-command.rm-root"),
    "EVAGIX_GENERATED_TARGET_TAMPERED": RuleAlias("EVAGIX_GENERATED_TARGET_TAMPERED", "generated-context-tampered"),
    "MISSING_OPTIONAL_AGENT_FILE": RuleAlias("MISSING_OPTIONAL_AGENT_FILE", "missing-target"),
}


def get_rule_alias(rule_id: str) -> RuleAlias | None:
    return LEGACY_RULE_ALIASES.get(rule_id)


def iter_rule_aliases() -> Iterable[RuleAlias]:
    return tuple(LEGACY_RULE_ALIASES.values())


def canonical_rule_id(rule_id: str) -> str:
    alias = get_rule_alias(rule_id)
    return alias.new_id if alias else rule_id
