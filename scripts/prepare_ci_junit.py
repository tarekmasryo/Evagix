"""Prepare a JUnit artifact without original free text for the advisory CI job."""

from __future__ import annotations

import argparse
from pathlib import Path
from xml.etree import ElementTree

from evagix.verification.junit import MAX_REPORT_BYTES, read_junit_report


def prepare_report(source: Path, destination: Path) -> int:
    """Export complete reports only; never copy identities, messages or metadata."""
    report = read_junit_report(source)
    if report.collection_status != "complete":
        return 1 if report.collection_status == "incomplete" else 2

    root = ElementTree.Element("testsuites")
    for suite_number, suite in enumerate(report.suites, 1):
        attributes = {"name": f"suite-{suite_number}"}
        attributes.update({key: str(value) for key, value in suite.declared.items() if value is not None})
        element = ElementTree.SubElement(root, "testsuite", attributes)
        for case_number, case in enumerate(suite.cases, 1):
            row = ElementTree.SubElement(element, "testcase", {"name": f"case-{case_number}"})
            for marker in case.markers:
                ElementTree.SubElement(row, marker)

    contents = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
    if len(contents) > MAX_REPORT_BYTES:
        return 2
    try:
        # Exclusive creation prevents an old artifact or a symlink from being overwritten.
        with destination.open("xb") as handle:
            handle.write(contents)
    except (OSError, ValueError):
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    status = prepare_report(args.source, args.destination)
    if status:
        print(
            "JUnit transfer unavailable: incomplete input."
            if status == 1
            else "JUnit transfer unavailable: input or output error."
        )
    return status


if __name__ == "__main__":
    raise SystemExit(main())
