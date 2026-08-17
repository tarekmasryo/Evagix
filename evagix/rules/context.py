from __future__ import annotations

from evagix.rules._shared import rule_ids, rules_by_category, rules_by_id_prefix
from evagix.rules.models import RuleDefinition


def iter_context_rules() -> tuple[RuleDefinition, ...]:
    return (*rules_by_category("agent_context", "drift"), *rules_by_id_prefix("AGENT_", "GENERATED_CONTEXT"))


def context_rule_ids() -> tuple[str, ...]:
    return rule_ids(iter_context_rules())
