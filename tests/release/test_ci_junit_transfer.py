from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

import pytest

from evagix.verification import junit
from scripts.prepare_ci_junit import main, prepare_report


def _suite(rows: str, tests: int = 1, failures: int = 0, errors: int = 0, skipped: int = 0) -> str:
    return (
        f'<testsuite name="private-suite" tests="{tests}" failures="{failures}" '
        f'errors="{errors}" skipped="{skipped}">{rows}</testsuite>'
    )


def test_transfer_omits_all_free_text_and_preserves_rows_and_markers(tmp_path: Path) -> None:
    source = tmp_path / "raw.xml"
    destination = tmp_path / "minimized.xml"
    secret = "private-canary-never-transfer"
    source.write_text(
        "<testsuites>"
        + _suite(
            f'<properties><property name="owner" value="{secret}"/></properties>'
            f'<testcase name="{secret}" classname="{secret}" file="{secret}" line="7" time="1.2">'
            f'<failure message="{secret}" type="{secret}">{secret}</failure>'
            f"<system-out>{secret}</system-out><system-err>{secret}</system-err></testcase>"
            f'<testcase name="{secret}"><skipped message="{secret}">{secret}</skipped>'
            f'<error message="{secret}">{secret}</error><error>{secret}</error></testcase>'
            f'<testcase name="{secret}"/>',
            tests=3,
            failures=1,
            errors=2,
            skipped=1,
        ).replace('name="private-suite"', f'name="{secret}" hostname="{secret}" timestamp="{secret}"')
        + _suite("", tests=0)
        + "</testsuites>",
        encoding="utf-8",
    )
    assert prepare_report(source, destination) == 0
    content = destination.read_text(encoding="utf-8")
    assert secret not in content and "private-suite" not in content
    root = ElementTree.fromstring(content)
    assert root.tag == "testsuites" and not root.attrib
    for suite_number, suite in enumerate(root, 1):
        assert set(suite.attrib) == {"name", "tests", "failures", "errors", "skipped"}
        assert suite.attrib["name"] == f"suite-{suite_number}"
        for case_number, case in enumerate(suite, 1):
            assert case.tag == "testcase" and case.attrib == {"name": f"case-{case_number}"}
            for marker in case:
                assert marker.tag in {"failure", "error", "skipped"}
                assert not marker.attrib and marker.text is None and not list(marker)
    original = junit.read_junit_report(source).to_dict()
    transferred = junit.read_junit_report(destination).to_dict()
    assert original["collection_status"] == transferred["collection_status"] == "complete"
    assert original["counts"] == transferred["counts"]
    for before, after in zip(original["suites"], transferred["suites"], strict=True):
        assert before["declared"] == after["declared"]
        assert before["observed"] == after["observed"]
        assert [row["markers"] for row in before["cases"]] == [row["markers"] for row in after["cases"]]
    assert transferred["source_verification"] == "unverified"
    assert transferred["revision_binding"] == transferred["run_completion"] == "unknown"
    other = tmp_path / "repeat.xml"
    assert prepare_report(source, other) == 0
    assert destination.read_bytes() == other.read_bytes()


@pytest.mark.parametrize(
    "xml,outcome",
    [
        (_suite('<testcase name="test_pass"/>'), "passed"),
        (_suite('<testcase name="test_fail"><failure/></testcase>', failures=1), "failed"),
        (_suite('<testcase name="test_error"><error/></testcase>', errors=1), "failed"),
        (_suite('<testcase name="test_skip"><skipped/></testcase>', skipped=1), "skipped_only"),
        (_suite("", tests=0), "empty"),
    ],
)
def test_transfer_preserves_reported_outcomes(tmp_path: Path, xml: str, outcome: str) -> None:
    source = tmp_path / "source.xml"
    target = tmp_path / "target.xml"
    source.write_text(xml, encoding="utf-8")
    assert main([str(source), str(target)]) == 0
    assert junit.read_junit_report(target).to_dict()["reported_outcome"] == outcome


@pytest.mark.parametrize(
    "xml,status",
    [
        (_suite('<testcase name="test"/>', tests=2), 1),
        ('<testsuite tests="1"><testcase name="test"/></testsuite>', 1),
        (_suite("<testcase/>"), 1),
        ("<testsuites/>", 1),
        ("<other/>", 1),
        ("<testsuite", 2),
        ('<!DOCTYPE testsuites [<!ENTITY private "secret">]><testsuites/>', 2),
    ],
)
def test_incomplete_or_invalid_input_never_becomes_an_artifact(tmp_path: Path, xml: str, status: int) -> None:
    source = tmp_path / "source.xml"
    target = tmp_path / "target.xml"
    source.write_text(xml, encoding="utf-8")
    assert prepare_report(source, target) == status
    assert not target.exists()


def test_missing_input_and_existing_output_are_not_hidden_or_overwritten(tmp_path: Path) -> None:
    source = tmp_path / "source.xml"
    target = tmp_path / "target.xml"
    assert prepare_report(source, target) == 2
    assert not target.exists()
    source.write_text(_suite('<testcase name="test"/>'), encoding="utf-8")
    target.write_bytes(b"existing user content")
    assert prepare_report(source, target) == 2
    assert target.read_bytes() == b"existing user content"
    assert prepare_report(source, tmp_path / "absent" / "target.xml") == 2


def test_input_limits_do_not_publish_a_partial_transfer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.xml"
    target = tmp_path / "target.xml"
    source.write_text(_suite('<testcase name="test"/>'), encoding="utf-8")
    monkeypatch.setattr(junit, "MAX_REPORT_BYTES", 32)
    assert prepare_report(source, target) == 1
    assert not target.exists()


def test_real_failed_pytest_run_remains_failed_and_private_text_stays_local(tmp_path: Path) -> None:
    raw = tmp_path / "raw.xml"
    transferred = tmp_path / "transferred.xml"
    test = tmp_path / "test_transfer.py"
    test.write_text(
        "import pytest\n"
        "def test_pass(): pass\n"
        'def test_fail(): assert False, "private-body-canary"\n'
        'def test_skip(): pytest.skip("private-skip-canary")\n',
        encoding="utf-8",
    )
    config = tmp_path / "pytest.ini"
    config.write_text("[pytest]\n", encoding="utf-8")
    environment = os.environ.copy()
    for key in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_DEBUG"):
        environment.pop(key, None)
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "pytest",
            "--noconftest",
            "-p",
            "no:cacheprovider",
            "-c",
            str(config),
            "--junitxml",
            str(raw),
            str(test),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 1
    assert "private-body-canary" in raw.read_text(encoding="utf-8")
    assert prepare_report(raw, transferred) == 0
    report = junit.read_junit_report(transferred).to_dict()
    assert report["reported_outcome"] == "failed"
    assert report["counts"] == {"cases": 3, "passed": 1, "failed": 1, "error": 0, "skipped": 1}
    assert "private-" not in transferred.read_text(encoding="utf-8")
