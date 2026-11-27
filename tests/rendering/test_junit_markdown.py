from __future__ import annotations

from pathlib import Path

import pytest

from evagix.reports.junit import render_junit_report_markdown
from evagix.verification.junit import JUnitCase, JUnitReport, JUnitSuite, read_junit_report


def test_repeated_case_rows_and_multiple_markers_are_preserved() -> None:
    suite = JUnitSuite(
        "pytest",
        {"tests": 2, "failures": 1, "errors": 2, "skipped": 1},
        [JUnitCase("same", "module", ("failure",)), JUnitCase("same", "module", ("skipped", "error", "error"))],
    )
    output = render_junit_report_markdown(JUnitReport("complete", (suite,)))
    assert "cases=2, passed=0, failed=1, error=1, skipped=0" in output
    assert output.count("module::same") == 2
    assert "skipped, error, error" in output
    assert "**Reported outcome:** failed" in output
    assert "revision binding: `unknown`" in output


def test_incomplete_counters_and_shortened_names_remain_visible() -> None:
    suite = JUnitSuite(
        "s" * 2049,
        {"tests": None, "failures": 0, "errors": 2, "skipped": 0},
        [JUnitCase("t" * 2049, "", ("error",))],
    )
    output = render_junit_report_markdown(JUnitReport("incomplete", (suite,), ("count_mismatch",)))
    assert "**Collection:** incomplete" in output and "count_mismatch" in output
    assert "Declared suite counters: tests=unknown, failures=0, errors=2, skipped=0" in output
    assert "Observed suite counters: tests=1, failures=0, errors=1, skipped=0" in output
    assert output.count("display identity shortened") == 2
    assert "s" * 2049 not in output and "t" * 2049 not in output


def test_only_passed_rows_are_hidden() -> None:
    suite = JUnitSuite(
        "pytest",
        {"tests": 2, "failures": 0, "errors": 0, "skipped": 1},
        [JUnitCase("hidden_pass", "", ()), JUnitCase("visible_skip", "", ("skipped",))],
    )
    output = render_junit_report_markdown(JUnitReport("complete", (suite,)))
    assert "hidden_pass" not in output and "visible_skip" in output
    assert "Passed rows hidden: 1" in output
    assert "cases=2, passed=1, failed=0, error=0, skipped=1" in output


@pytest.mark.parametrize("xml", ["<testsuites/>", '<testsuite name="unsupported"><other/></testsuite>'])
def test_incomplete_report_without_observations_is_not_a_clean_result(tmp_path: Path, xml: str) -> None:
    path = tmp_path / "report.xml"
    path.write_text(xml, encoding="utf-8")
    output = render_junit_report_markdown(read_junit_report(path))
    assert "**Collection:** incomplete" in output
    assert "**Reported outcome:** unknown" in output
    assert "Incomplete report: do not infer a clean result" in output
