from __future__ import annotations

import json
from pathlib import Path

from evagix.scanner import scan_repo

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
GOLDEN = ROOT / "golden"


def _assert_contains(actual: list[str], expected: list[str]) -> None:
    missing = sorted(set(expected) - set(actual))
    assert not missing, f"missing expected values: {missing} from {actual}"


def test_polyglot_golden_scan_contract():
    facts = scan_repo(FIXTURES / "polyglot_monorepo")
    expected = json.loads((GOLDEN / "polyglot_expected_scan_keys.json").read_text(encoding="utf-8"))
    _assert_contains(facts.languages, expected["languages_contains"])
    _assert_contains(facts.frameworks, expected["frameworks_contains"])
    _assert_contains(list(facts.commands), expected["commands_contains"])
    _assert_contains(facts.active_profiles, expected["profiles_contains"])


def test_ml_dashboard_golden_scan_contract():
    facts = scan_repo(FIXTURES / "ml_streamlit_dashboard")
    expected = json.loads((GOLDEN / "ml_dashboard_expected_scan_keys.json").read_text(encoding="utf-8"))
    _assert_contains(facts.languages, expected["languages_contains"])
    _assert_contains(facts.frameworks, expected["frameworks_contains"])
    _assert_contains(facts.ml_data_tools, expected["ml_data_tools_contains"])
    _assert_contains(list(facts.commands), expected["commands_contains"])
    _assert_contains(facts.active_profiles, expected["profiles_contains"])
