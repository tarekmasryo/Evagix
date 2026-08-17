from __future__ import annotations

from collections.abc import Iterable

from evagix.rules.models import RuleDefinition
from evagix.rules.registry import iter_rules


def rules_by_category(*categories: str) -> tuple[RuleDefinition, ...]:
    wanted = set(categories)
    return tuple(rule for rule in iter_rules() if rule.category in wanted)


def rules_by_id_prefix(*prefixes: str) -> tuple[RuleDefinition, ...]:
    return tuple(rule for rule in iter_rules() if any(rule.id.startswith(prefix) for prefix in prefixes))


def rule_ids(rules: Iterable[RuleDefinition]) -> tuple[str, ...]:
    return tuple(rule.id for rule in rules)
