from __future__ import annotations

from evagix.rules._shared import rule_ids, rules_by_category, rules_by_id_prefix
from evagix.rules.models import RuleDefinition


def iter_readme_rules() -> tuple[RuleDefinition, ...]:
    return (*rules_by_category("readme_evidence"), *rules_by_id_prefix("README_"))


def readme_rule_ids() -> tuple[str, ...]:
    return rule_ids(iter_readme_rules())
