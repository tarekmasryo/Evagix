"""Rule metadata and registry for evidence-first checks."""

from evagix.rules.aliases import LEGACY_RULE_ALIASES, canonical_rule_id, get_rule_alias, iter_rule_aliases
from evagix.rules.models import RuleAlias, RuleDefinition
from evagix.rules.registry import DEFAULT_RULES, get_rule, iter_rules, register_rule

__all__ = [
    "DEFAULT_RULES",
    "LEGACY_RULE_ALIASES",
    "RuleAlias",
    "RuleDefinition",
    "canonical_rule_id",
    "get_rule",
    "get_rule_alias",
    "iter_rule_aliases",
    "iter_rules",
    "register_rule",
]
