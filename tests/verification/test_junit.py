from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from evagix.verification import junit


def report(tmp_path: Path, xml: str | bytes) -> dict:
    path = tmp_path / "results.xml"
    path.write_bytes(xml.encode("utf-8") if isinstance(xml, str) else xml)
    return junit.read_junit_report(path).to_dict()


def suite(body: str = '<testcase name="test_ok"/>', **counts: object) -> str:
    attrs = {"tests": 1, "errors": 0, "failures": 0, "skipped": 0, **counts}
    encoded = " ".join(f'{key}="{value}"' for key, value in attrs.items() if value is not None)
    return f'<testsuite name="pytest" {encoded}>{body}</testsuite>'


@pytest.mark.parametrize(
    "body,counts,outcome,observed",
    [
        ('<testcase name="ok"/>', {}, "passed", {"passed": 1}),
        ('<testcase name="bad"><failure/></testcase>', {"failures": 1}, "failed", {"failed": 1}),
        ('<testcase name="err"><error/></testcase>', {"errors": 1}, "failed", {"error": 1}),
        ('<testcase name="skip"><skipped/></testcase>', {"skipped": 1}, "skipped_only", {"skipped": 1}),
        (
            '<testcase name="xfail"><skipped type="pytest.xfail"/></testcase>',
            {"skipped": 1},
            "skipped_only",
            {"skipped": 1},
        ),
        ("", {"tests": 0}, "empty", {}),
        (
            '<testcase name="ok"/><testcase name="skip"><skipped/></testcase>',
            {"tests": 2, "skipped": 1},
            "passed",
            {"passed": 1, "skipped": 1},
        ),
        ('<testcase name="both"><error/><error/></testcase>', {"errors": 2}, "failed", {"error": 1}),
        ('<testcase name="both"><skipped/><error/></testcase>', {"errors": 1, "skipped": 1}, "failed", {"error": 1}),
        (
            '<testcase name="same"><failure/></testcase><testcase name="same"><error/></testcase>',
            {"tests": 2, "failures": 1, "errors": 1},
            "failed",
            {"failed": 1, "error": 1},
        ),
    ],
)
def test_outcomes_preserve_rows_and_marker_counts(
    tmp_path: Path, body: str, counts: dict, outcome: str, observed: dict
) -> None:
    payload = report(tmp_path, suite(body, **counts))
    assert payload["collection_status"] == "complete"
    assert payload["reported_outcome"] == outcome
    assert payload["counts"] == {
        "cases": sum(observed.values()),
        **dict.fromkeys(("passed", "failed", "error", "skipped"), 0),
        **observed,
    }
    assert payload["suites"][0]["declared"] == payload["suites"][0]["observed"]
    assert payload["source_verification"] == "unverified"
    assert payload["run_completion"] == payload["revision_binding"] == "unknown"
    assert payload["policy_decision"] == "not_evaluated"


def test_multiple_suites_keep_repeated_identities(tmp_path: Path) -> None:
    payload = report(tmp_path, "<testsuites>" + suite() * 2 + "</testsuites>")
    assert payload["collection_status"] == "complete"
    assert payload["counts"]["cases"] == 2
    assert len(payload["suites"]) == 2


@pytest.mark.parametrize("value", [None, "", "-1", "1.0", "1e0", "true", "9999999999", "١"])
def test_missing_or_invalid_counters_cannot_produce_clean_result(tmp_path: Path, value: object) -> None:
    payload = report(tmp_path, suite(tests=value))
    assert payload["collection_status"] == "incomplete"
    assert payload["reported_outcome"] == "unknown"
    assert payload["issues"] == ["missing_or_invalid_counts"]


@pytest.mark.parametrize("counts", [{"tests": 2}, {"tests": 0}, {"failures": 1}, {"errors": 1}, {"skipped": 1}])
def test_counter_mismatch_keeps_observations_without_clean_result(tmp_path: Path, counts: dict) -> None:
    payload = report(tmp_path, suite(**counts))
    assert payload["collection_status"] == "incomplete"
    assert payload["reported_outcome"] == "unknown"
    assert payload["counts"]["passed"] == 1
    assert payload["issues"] == ["count_mismatch"]


def test_incomplete_report_retains_observed_failure(tmp_path: Path) -> None:
    payload = report(tmp_path, suite('<testcase name="bad"><failure/></testcase>', tests=2, failures=1))
    assert payload["collection_status"] == "incomplete"
    assert payload["reported_outcome"] == "failed"
    assert payload["counts"]["failed"] == 1


@pytest.mark.parametrize(
    "xml,issue",
    [
        ("<testsuites/>", "missing_suite"),
        (suite("<testcase/>"), "missing_case_name"),
        ("<testsuites tests='0'/>", "unsupported_structure"),
        ("<report/>", "unsupported_structure"),
        ("<testsuites><testsuite><testsuite/></testsuite></testsuites>", "unsupported_structure"),
        (suite('<testcase name="test"><rerunFailure/></testcase>'), "unsupported_structure"),
        (suite('<testcase name="test"><passed/></testcase>'), "unsupported_structure"),
        (suite('<testcase name="test">not a pytest case</testcase>'), "unsupported_structure"),
        ('<testsuite xmlns="urn:other"/>', "unsupported_structure"),
        (
            suite('<xi:include xmlns:xi="http://www.w3.org/2001/XInclude" href="https://invalid.example/report"/>'),
            "unsupported_structure",
        ),
    ],
)
def test_unsupported_or_missing_structure_is_explicit(tmp_path: Path, xml: str, issue: str) -> None:
    payload = report(tmp_path, xml)
    assert payload["collection_status"] == "incomplete"
    assert payload["reported_outcome"] == "unknown"
    assert issue in payload["issues"]


@pytest.mark.parametrize(
    "xml",
    [
        b"",
        b"\xff",
        b"<testsuite",
        b"<testsuites>" + suite().encode(),
        b"<testsuite tests='1' tests='2'/>",
        b"<testsuite>&undefined;</testsuite>",
        b"\x1b[2J",
    ],
)
def test_invalid_xml_is_an_error_without_partial_success(tmp_path: Path, xml: bytes) -> None:
    payload = report(tmp_path, xml)
    assert payload["collection_status"] == "error"
    assert payload["reported_outcome"] == "unknown"
    assert payload["suites"] == []
    assert payload["issues"] == ["invalid_xml"]


@pytest.mark.parametrize(
    "prefix",
    [
        '<!DOCTYPE testsuite SYSTEM "file:///private-not-read">',
        '<!DOCTYPE testsuite [<!ENTITY x "expansion">]>',
        '<!DOCTYPE testsuite [<!ENTITY % x SYSTEM "https://invalid.example/entity">%x;]>',
        '<?xml-stylesheet href="https://invalid.example/stylesheet"?>',
    ],
)
def test_xml_declarations_cannot_expand_or_load_resources(
    tmp_path: Path, prefix: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import socket
    import subprocess

    def unexpected(*args: object, **kwargs: object) -> None:
        pytest.fail("XML inspection must not contact services or execute commands")

    monkeypatch.setattr(socket, "socket", unexpected)
    monkeypatch.setattr(subprocess, "Popen", unexpected)
    payload = report(tmp_path, prefix + suite())
    assert payload["collection_status"] == "error"
    assert payload["issues"] == ["unsafe_xml"]


@pytest.mark.parametrize("declaration", ['<?xml version="1.0" encoding="iso-8859-1"?>', '<?xml version="1.1"?>'])
def test_non_pytest_encoding_declarations_are_rejected(tmp_path: Path, declaration: str) -> None:
    assert report(tmp_path, declaration + suite())["issues"] == ["unsupported_encoding"]


def test_utf8_bom_and_entity_escaping_are_supported(tmp_path: Path) -> None:
    payload = report(
        tmp_path,
        b"\xef\xbb\xbf"
        + ('<?xml version="1.0" encoding="utf-8"?>' + suite('<testcase name="اختبار &amp; &#x41;"/>')).encode(),
    )
    assert payload["collection_status"] == "complete"
    assert payload["suites"][0]["cases"][0]["name"] == "اختبار & A"


def test_utf16_without_declaration_is_not_treated_as_utf8(tmp_path: Path) -> None:
    assert report(tmp_path, suite().encode("utf-16-le"))["issues"] == ["invalid_xml"]


@pytest.mark.parametrize(
    "limit,value,xml,issue",
    [
        ("MAX_REPORT_BYTES", 10, suite(), "file_limit_exceeded"),
        ("MAX_CASES", 1, suite('<testcase name="a"/>' * 2, tests=2), "case_limit_exceeded"),
        ("MAX_SUITES", 1, "<testsuites>" + suite() * 2 + "</testsuites>", "suite_limit_exceeded"),
        ("MAX_ELEMENTS", 1, suite(), "xml_limit_exceeded"),
        ("MAX_DEPTH", 1, suite(), "xml_limit_exceeded"),
    ],
)
def test_resource_limits_never_return_partial_clean_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit: str, value: int, xml: str, issue: str
) -> None:
    monkeypatch.setattr(junit, limit, value)
    payload = report(tmp_path, xml)
    assert payload["collection_status"] == "incomplete"
    assert payload["reported_outcome"] == "unknown"
    assert payload["suites"] == []
    assert payload["issues"] == [issue]


def test_exact_file_size_limit_is_not_truncation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    xml = suite()
    monkeypatch.setattr(junit, "MAX_REPORT_BYTES", len(xml.encode()))
    assert report(tmp_path, xml)["collection_status"] == "complete"


def test_long_pytest_identities_are_display_limits_not_lost_results(tmp_path: Path) -> None:
    prefix = "p" * 4096
    body = f'<testcase name="{prefix}one" classname="{prefix}"/><testcase name="{prefix}two"><failure/></testcase>'
    xml = suite(body, tests=2, failures=1).replace('name="pytest"', f'name="{prefix}"', 1)
    payload = report(tmp_path, xml)
    assert payload["collection_status"] == "complete"
    assert payload["counts"] == {"cases": 2, "passed": 1, "failed": 1, "error": 0, "skipped": 0}
    selected = payload["suites"][0]
    assert selected["identity_truncated"] is True
    assert selected["name"] == "p" * junit.MAX_LABEL_CHARS + "..."
    assert all(case["identity_truncated"] for case in selected["cases"])
    assert len(selected["cases"]) == 2  # Shortened identities must not deduplicate rows.
    assert selected["cases"][0]["classname"] == selected["name"]


def test_long_credentials_are_redacted_before_shortening(tmp_path: Path) -> None:
    secret = "synthetic-private-value" * 300
    payload = report(tmp_path, suite(f'<testcase name="token={secret}"/>'))
    case = payload["suites"][0]["cases"][0]
    assert case["name"] == "token=[REDACTED]"
    assert case["identity_truncated"] is False
    assert "synthetic-private-value" not in json.dumps(payload)


def test_arbitrary_logs_properties_paths_and_tracebacks_are_omitted(tmp_path: Path) -> None:
    xml = suite(
        '<properties><property name="token" value="never-emit-property"/></properties>'
        "<system-out>never-emit-stdout</system-out><system-err>never-emit-stderr</system-err>"
        '<testcase name="test" file="never-emit-path" line="0">'
        '<failure message="never-emit-message">never-emit-traceback</failure></testcase>',
        failures=1,
    )
    payload = report(tmp_path, xml)
    assert payload["collection_status"] == "complete"
    assert "never-emit" not in json.dumps(payload)


def test_display_artifact_redacts_identities(tmp_path: Path) -> None:
    payload = report(
        tmp_path,
        suite(
            '<testcase name="test[token=example-secret]" classname="https://user:example-password@invalid.example/test"/>'
        ),
    )
    encoded = json.dumps(payload)
    assert "example-secret" not in encoded
    assert "example-password" not in encoded
    assert "[REDACTED]" in encoded


def test_file_errors_are_generic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert junit.read_junit_report(tmp_path / "missing.xml").issues == ("read_error",)
    assert junit.read_junit_report(tmp_path).issues == ("not_regular_file",)
    path = tmp_path / "report.xml"
    path.write_text(suite(), encoding="utf-8")

    def denied(*args: object, **kwargs: object) -> None:
        raise PermissionError("private error text")

    monkeypatch.setattr(os, "open", denied)
    payload = junit.read_junit_report(path).to_dict()
    assert payload["collection_status"] == "error"
    assert "private error text" not in json.dumps(payload)


def test_symlink_report_is_not_followed(tmp_path: Path) -> None:
    target = tmp_path / "target.xml"
    target.write_text(suite(), encoding="utf-8")
    link = tmp_path / "link.xml"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Symlink creation unavailable")
    assert junit.read_junit_report(link).issues == ("not_regular_file",)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO only")
def test_fifo_is_rejected_without_opening(tmp_path: Path) -> None:
    path = tmp_path / "report.xml"
    os.mkfifo(path)
    assert junit.read_junit_report(path).issues == ("not_regular_file",)
