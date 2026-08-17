from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

from evagix.commands.registry import build_parser
from evagix.rules import iter_rule_aliases, iter_rules


def _section(text: str, heading: str) -> str:
    start = text.index(heading) + len(heading)
    end = text.find("\n## ", start)
    return text[start:] if end < 0 else text[start:end]


def test_rule_overview_counts_match_registry() -> None:
    rules = list(iter_rules())
    expected = Counter(rule.category for rule in rules)
    categories = _section(Path("docs/rules.md").read_text(encoding="utf-8"), "## Categories")
    documented = {
        category: int(count)
        for category, count in re.findall(r"^\| `([^`]+)` \| (\d+) \|", categories, flags=re.MULTILINE)
        if category != "Total"
    }
    total = re.search(r"^\| `Total` \| (\d+) \|", categories, flags=re.MULTILINE)

    assert documented == dict(sorted(expected.items()))
    assert total is not None
    assert int(total.group(1)) == len(rules) == len({rule.id for rule in rules})


def test_rule_reference_index_and_metadata_match_registry() -> None:
    rules = {rule.id: rule for rule in iter_rules()}
    text = Path("docs/rules-reference.md").read_text(encoding="utf-8")
    index = _section(text, "## Rule index")
    rows = re.findall(
        r"^\| \[`([^`]+)`\]\(#([^)]+)\) \| `([^`]+)` \| `([^`]+)` "
        r"\| `([^`]+)` \| `(true|false)` \|$",
        index,
        flags=re.MULTILINE,
    )
    index_counts = Counter(row[0] for row in rows)
    mismatches: list[str] = []

    assert index_counts == Counter(rules.keys())
    for rule_id, anchor, category, severity, confidence, can_fail_ci in rows:
        rule = rules[rule_id]
        actual = (anchor, category, severity, confidence, can_fail_ci)
        expected = (
            rule.docs_anchor,
            rule.category,
            rule.severity,
            rule.confidence,
            str(rule.can_fail_ci).lower(),
        )
        if actual != expected:
            mismatches.append(f"{rule_id}: {actual!r} != {expected!r}")
    assert mismatches == []


def test_rule_reference_sections_and_aliases_match_registry() -> None:
    rules = {rule.id: rule for rule in iter_rules()}
    text = Path("docs/rules-reference.md").read_text(encoding="utf-8")
    headings = list(re.finditer(r"^### `([^`]+)`$", text, flags=re.MULTILINE))
    heading_counts = Counter(match.group(1) for match in headings)
    sections = {
        match.group(1): text[match.end() : headings[index + 1].start() if index + 1 < len(headings) else None]
        for index, match in enumerate(headings)
    }
    mismatches: list[str] = []

    assert heading_counts == Counter(rules.keys())
    for rule_id, rule in rules.items():
        section = sections[rule_id]
        for label, expected in [
            ("Title", rule.title),
            ("Category", f"`{rule.category}`"),
            ("Severity", f"`{rule.severity}`"),
            ("Confidence", f"`{rule.confidence}`"),
        ]:
            match = re.search(rf"^- \*\*{label}:\*\* (.+)$", section, flags=re.MULTILINE)
            actual = match.group(1) if match else None
            if actual != expected:
                mismatches.append(f"{rule_id} {label}: {actual!r} != {expected!r}")
    assert mismatches == []

    aliases = _section(text, "## Legacy compatibility aliases")
    documented_aliases = {
        old_id: (new_id, deprecated == "true")
        for old_id, new_id, deprecated in re.findall(
            r"^\| `([^`]+)` \| `([^`]+)` \| `(true|false)` \|$",
            aliases,
            flags=re.MULTILINE,
        )
    }
    expected_aliases = {alias.old_id: (alias.new_id, alias.deprecated) for alias in iter_rule_aliases()}
    assert documented_aliases == expected_aliases


def test_rule_reference_anchors_are_unique_and_resolvable() -> None:
    rules = list(iter_rules())
    text = Path("docs/rules-reference.md").read_text(encoding="utf-8")
    anchors = re.findall(r'^<a id="([^"]+)"></a>$', text, flags=re.MULTILINE)
    index = _section(text, "## Rule index")
    index_links = re.findall(r"\]\(#([^)]+)\)", index)

    assert len(anchors) == len(set(anchors))
    assert all(rule.docs_anchor in anchors for rule in rules)
    assert set(index_links) <= set(anchors)


def test_command_guide_inventory_matches_cli_registry() -> None:
    parser = build_parser()
    subparsers = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))
    inventory = _section(Path("docs/commands.md").read_text(encoding="utf-8"), "## Command inventory")
    documented = re.findall(r"`evagix ([a-z][a-z-]+)`", inventory)

    assert Counter(documented) == Counter(subparsers.choices.keys())
