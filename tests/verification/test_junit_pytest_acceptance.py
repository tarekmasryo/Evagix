from __future__ import annotations

import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest

from evagix.verification.junit import read_junit_report


def _run_pytest_report(tmp_path: Path, family: str, source: str, expected_exit: int) -> dict[str, Any]:
    test_file = tmp_path / "test_synthetic.py"
    test_file.write_text(source, encoding="utf-8")
    config = tmp_path / "pytest.ini"
    config.write_text("[pytest]\njunit_logging = no\n", encoding="utf-8")
    report_path = tmp_path / "report.xml"
    environment = os.environ.copy()
    for key in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_DEBUG"):
        environment.pop(key, None)
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-m",
            "pytest",
            "--noconftest",
            "-q",
            "--tb=short",
            "-p",
            "no:cacheprovider",
            "-c",
            str(config),
            "-o",
            f"junit_family={family}",
            "--basetemp",
            str(tmp_path / "pytest-temp"),
            "--junitxml",
            str(report_path),
            str(test_file),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    assert result.returncode == expected_exit, result.stdout + result.stderr
    assert report_path.is_file()
    return read_junit_report(report_path).to_dict()


@pytest.mark.parametrize("family", ["xunit1", "xunit2"])
def test_real_pytest_outcomes_and_teardown_counts(tmp_path: Path, family: str) -> None:
    report = _run_pytest_report(
        tmp_path,
        family,
        """import pytest


@pytest.fixture
def teardown_error():
    yield
    raise RuntimeError("synthetic teardown failure")


@pytest.fixture
def setup_and_teardown_error(request):
    def finalizer():
        raise RuntimeError("synthetic finalizer failure")

    request.addfinalizer(finalizer)
    raise RuntimeError("synthetic setup failure")


def test_passed():
    pass


def test_failed():
    assert False, "synthetic assertion failure"


def test_skipped():
    pytest.skip("synthetic skip")


@pytest.mark.xfail(reason="synthetic expected failure")
def test_xfailed():
    assert False


@pytest.mark.xfail(reason="synthetic unexpected pass", strict=False)
def test_xpassed():
    pass


@pytest.mark.xfail(reason="synthetic strict unexpected pass", strict=True)
def test_strict_xpass():
    pass


def test_pass_then_teardown_error(teardown_error):
    pass


def test_fail_then_teardown_error(teardown_error):
    assert False, "synthetic call failure"


def test_setup_then_teardown_error(setup_and_teardown_error):
    pass


def test_skip_then_teardown_error(teardown_error):
    pytest.skip("synthetic skip before teardown")
""",
        expected_exit=1,
    )

    assert report["collection_status"] == "complete"
    assert report["issues"] == []
    assert report["reported_outcome"] == "failed"
    assert report["counts"] == {"cases": 11, "passed": 2, "failed": 3, "error": 4, "skipped": 2}
    assert report["source_verification"] == "unverified"
    assert report["revision_binding"] == "unknown"
    assert report["run_completion"] == "unknown"
    suite = report["suites"][0]
    assert len(report["suites"]) == 1
    assert suite["declared"] == suite["observed"] == {"tests": 11, "failures": 3, "errors": 5, "skipped": 3}

    cases: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in suite["cases"]:
        cases[case["name"]].append(case)

    expected = {
        "test_passed": [("passed", [])],
        "test_failed": [("failed", ["failure"])],
        "test_skipped": [("skipped", ["skipped"])],
        "test_xfailed": [("skipped", ["skipped"])],
        "test_xpassed": [("passed", [])],
        "test_strict_xpass": [("failed", ["failure"])],
        "test_pass_then_teardown_error": [("error", ["error"])],
        "test_fail_then_teardown_error": [("failed", ["failure"]), ("error", ["error"])],
        "test_setup_then_teardown_error": [("error", ["error", "error"])],
        "test_skip_then_teardown_error": [("error", ["skipped", "error"])],
    }
    assert {name: [(case["outcome"], case["markers"]) for case in rows] for name, rows in cases.items()} == expected

    xml_cases = ElementTree.parse(tmp_path / "report.xml").findall("./testsuite/testcase")
    assert all(("file" in case.attrib) == (family == "xunit1") for case in xml_cases)


@pytest.mark.parametrize("family", ["xunit1", "xunit2"])
def test_real_pytest_collection_error_is_reported_as_error(tmp_path: Path, family: str) -> None:
    report = _run_pytest_report(
        tmp_path,
        family,
        'raise RuntimeError("synthetic collection failure")\n',
        expected_exit=2,
    )

    assert report["collection_status"] == "complete"
    assert report["issues"] == []
    assert report["reported_outcome"] == "failed"
    assert report["counts"] == {"cases": 1, "passed": 0, "failed": 0, "error": 1, "skipped": 0}
    assert report["run_completion"] == "unknown"
    suite = report["suites"][0]
    assert suite["declared"] == suite["observed"] == {"tests": 1, "failures": 0, "errors": 1, "skipped": 0}
    assert suite["cases"][0]["markers"] == ["error"]


@pytest.mark.parametrize("family", ["xunit1", "xunit2"])
def test_real_pytest_no_tests_is_empty_not_success(tmp_path: Path, family: str) -> None:
    report = _run_pytest_report(tmp_path, family, "# No tests are defined.\n", expected_exit=5)

    assert report["collection_status"] == "complete"
    assert report["issues"] == []
    assert report["reported_outcome"] == "empty"
    assert report["counts"] == {"cases": 0, "passed": 0, "failed": 0, "error": 0, "skipped": 0}
    assert report["run_completion"] == "unknown"
    suite = report["suites"][0]
    assert suite["declared"] == suite["observed"] == {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    assert suite["cases"] == []
