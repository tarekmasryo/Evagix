from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

from evagix.report_models import DoctorFinding
from evagix.reports.sarif import sarif_rule
from evagix.rules import get_rule, iter_rule_aliases, iter_rules

DYNAMIC_FINDING_CODES = {
    *(f"agent-context.missing-{name}" for name in ["install", "test", "lint", "typecheck", "build"]),
    *(f"agent-context.conflicting-{name}-commands" for name in ["install", "test", "lint", "typecheck", "build"]),
}
README_CLAIM_CODES = {
    f"readme-evidence.{claim}.{verdict}"
    for claim in [
        "tested",
        "dockerized",
        "ci-cd",
        "fastapi",
        "ai-llm",
        "monitoring",
        "secure",
        "production-ready",
        "deployable",
        "agent-instructions",
        "cli-tool",
        "package-installable",
        "examples",
        "typed",
        "zero-dependencies",
        "repo-readiness",
    ]
    for verdict in ["unsupported", "weak_evidence", "manual_review_required", "partially_supported"]
}


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _string_arg(call: ast.Call, index: int) -> str | None:
    if len(call.args) <= index:
        return None
    value = call.args[index]
    return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else None


def _string_keyword(call: ast.Call, name: str) -> str | None:
    for keyword in call.keywords:
        if keyword.arg == name and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
            return keyword.value.value
    return None


def _literal_emitted_codes() -> set[str]:
    codes: set[str] = set()
    files = [
        Path("evagix/command_safety.py"),
        Path("evagix/prompt_injection.py"),
        Path("evagix/context"),
        Path("evagix/validation"),
    ]
    for root in files:
        paths = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = _call_name(node.func)
                if name == "Finding":
                    code = _string_keyword(node, "id")
                    if code:
                        codes.add(code)
                if name in {"DoctorFinding", "AuditFinding"}:
                    code = _string_keyword(node, "code") or _string_arg(node, 1)
                    if code:
                        codes.add(code)
                if name == "add":
                    # Local add(severity, code, message, penalty?) helper used by doctor/audit checks.
                    code = _string_arg(node, 1)
                    if code and not code.startswith("{"):
                        codes.add(code)
    return codes


def test_every_known_emitted_finding_code_is_registered() -> None:
    emitted = _literal_emitted_codes() | DYNAMIC_FINDING_CODES | README_CLAIM_CODES
    unregistered = sorted(code for code in emitted if get_rule(code) is None)
    assert unregistered == []


def test_rule_ids_docs_anchors_and_sarif_ids_are_stable() -> None:
    rules = list(iter_rules())
    ids = [rule.id for rule in rules]
    assert len(ids) == len(set(ids))
    assert all(rule.docs_anchor for rule in rules)
    assert all(rule.docs_anchor == rule.docs_anchor.lower() for rule in rules)
    docs = Path("docs/rules-reference.md").read_text(encoding="utf-8")
    missing_docs = [rule.id for rule in rules if f'<a id="{rule.docs_anchor}"></a>' not in docs]
    assert missing_docs == []


def test_rule_reference_html_ids_are_unique_and_sarif_links_resolve() -> None:
    rules = list(iter_rules())
    docs = Path("docs/rules-reference.md").read_text(encoding="utf-8")
    html_ids = re.findall(r'<a id="([^"]+)"></a>', docs)
    counts = Counter(html_ids)

    assert len(rules) == 165
    assert [anchor for anchor, count in counts.items() if count > 1] == []
    assert counts["agent-context-dangerous-command"] == 1
    assert counts["generated-context-drift"] == 1
    assert all(f"### `{rule.id}`" in docs for rule in rules)

    for rule in rules:
        finding = DoctorFinding("warning", rule.id, rule.title, 0)
        help_uri = str(sarif_rule(finding)["helpUri"])
        assert help_uri.rsplit("#", maxsplit=1)[-1] in counts


def test_explain_falls_back_to_rule_registry() -> None:
    from evagix.explain import explain_finding

    explanation = explain_finding("agent-context.conflicting-test-commands")
    assert explanation.title == "Conflicting test commands found in agent context"
    assert "evidence-first rule registry" in explanation.why_it_matters


def test_legacy_rule_aliases_resolve_to_registered_rules() -> None:
    aliases = list(iter_rule_aliases())
    assert aliases
    assert all(get_rule(alias.old_id) is not None for alias in aliases)
    assert all(get_rule(alias.new_id) is not None for alias in aliases)
    assert all(alias.deprecated is True for alias in aliases)
