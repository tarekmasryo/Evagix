from __future__ import annotations

from evagix.rules._shared import rule_ids, rules_by_category, rules_by_id_prefix
from evagix.rules.models import RuleDefinition


def iter_safety_rules() -> tuple[RuleDefinition, ...]:
    return (*rules_by_category("safety"), *rules_by_id_prefix("DANGEROUS_", "PROMPT_INJECTION"))


def safety_rule_ids() -> tuple[str, ...]:
    return rule_ids(iter_safety_rules())
