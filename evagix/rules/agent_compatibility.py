from __future__ import annotations

from evagix.rules.context import context_rule_ids, iter_context_rules
from evagix.rules.models import RuleDefinition


def iter_agent_compatibility_rules() -> tuple[RuleDefinition, ...]:
    return iter_context_rules()


def agent_compatibility_rule_ids() -> tuple[str, ...]:
    return context_rule_ids()
