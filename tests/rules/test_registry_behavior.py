from __future__ import annotations

from pathlib import Path

from evagix.explain import explain_finding
from evagix.fixes import plan_fix
from evagix.rules.aliases import canonical_rule_id, get_rule_alias, iter_rule_aliases
from evagix.rules.registry import get_rule, iter_rules

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_rule_registry_exposes_stable_metadata() -> None:
    rule = get_rule("README_COMMAND_UNSUPPORTED")
    assert rule is not None
    assert rule.category == "readme_evidence"
    assert rule.remediation
    assert {item.id for item in iter_rules()} >= {
        "README_COMMAND_UNSUPPORTED",
        "AGENT_CONTEXT_DANGEROUS_COMMAND",
        "PROMPT_INJECTION_RISK",
    }


def test_rule_alias_helpers_cover_known_unknown_and_iteration() -> None:
    alias = get_rule_alias("README_COMMAND_UNSUPPORTED")
    assert alias is not None
    assert alias.new_id == "readme-evidence.command.unsupported"
    assert alias.to_dict()["deprecated"] is True
    assert canonical_rule_id("PROMPT_INJECTION_RISK") == "context-poisoning.ignore-instructions"
    assert canonical_rule_id("already-modern") == "already-modern"
    aliases = tuple(iter_rule_aliases())
    assert aliases
    assert {item.old_id for item in aliases} >= {"GENERATED_CONTEXT_DRIFT", "MISSING_OPTIONAL_AGENT_FILE"}


def test_explain_and_fix_registry_are_available():
    assert explain_finding("missing-ci").recommended_fix
    plan = plan_fix(FIXTURES / "polyglot_monorepo", "missing-ci")
    assert ".github/workflows/evagix.yml" in plan.files
