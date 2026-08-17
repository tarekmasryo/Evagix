from __future__ import annotations

from evagix.rules._shared import rule_ids, rules_by_category
from evagix.rules.models import RuleDefinition


def iter_mcp_rules() -> tuple[RuleDefinition, ...]:
    return rules_by_category("mcp")


def mcp_rule_ids() -> tuple[str, ...]:
    return rule_ids(iter_mcp_rules())
