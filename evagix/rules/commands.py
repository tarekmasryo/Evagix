from __future__ import annotations

from evagix.rules._shared import rule_ids, rules_by_id_prefix
from evagix.rules.models import RuleDefinition


def iter_command_rules() -> tuple[RuleDefinition, ...]:
    return rules_by_id_prefix("README_COMMAND", "COMMAND_", "DANGEROUS_COMMAND")


def command_rule_ids() -> tuple[str, ...]:
    return rule_ids(iter_command_rules())
