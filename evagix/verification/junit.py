"""Bounded inspection of local pytest JUnit XML; no execution attestation."""

from __future__ import annotations

import os
import re
import stat
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from xml.parsers import expat

from evagix.security.redaction import redact_for_output, redact_sensitive_text

MAX_REPORT_BYTES = 8_000_000
MAX_CASES = 10_000
MAX_ELEMENTS = 100_000
MAX_DEPTH = 16
MAX_SUITES = 100
MAX_LABEL_CHARS = 2048

Outcome = Literal["passed", "failed", "error", "skipped"]
CollectionStatus = Literal["complete", "incomplete", "error"]
_COUNTERS = ("tests", "failures", "errors", "skipped")
_MARKERS = {"failure": "failures", "error": "errors", "skipped": "skipped"}
_CHILDREN = {
    "": {"testsuites", "testsuite"},
    "testsuites": {"testsuite"},
    "testsuite": {"testcase", "properties", "system-out", "system-err"},
    "testcase": {"failure", "error", "skipped", "properties", "system-out", "system-err"},
    "properties": {"property"},
}


def _label(value: str) -> tuple[str, bool]:
    # Redact the full value before shortening: truncating a credential first
    # could remove the context needed by the central redaction patterns.
    redacted = redact_sensitive_text(value)
    shortened = len(redacted) > MAX_LABEL_CHARS
    return (redacted[:MAX_LABEL_CHARS] + "..." if shortened else redacted), shortened


@dataclass(frozen=True)
class JUnitCase:
    name: str
    classname: str
    markers: tuple[str, ...]

    @property
    def outcome(self) -> Outcome:
        if "error" in self.markers:
            return "error"
        if "failure" in self.markers:
            return "failed"
        return "skipped" if "skipped" in self.markers else "passed"

    def to_dict(self) -> dict[str, Any]:
        name, name_shortened = _label(self.name)
        classname, classname_shortened = _label(self.classname)
        return {
            "name": name,
            "classname": classname,
            "identity_truncated": name_shortened or classname_shortened,
            "outcome": self.outcome,
            "markers": list(self.markers),
        }


@dataclass
class JUnitSuite:
    name: str
    declared: dict[str, int | None]
    cases: list[JUnitCase] = field(default_factory=list)

    def observed(self) -> dict[str, int]:
        counts = {key: 0 for key in _COUNTERS}
        counts["tests"] = len(self.cases)
        for case in self.cases:
            for marker in case.markers:
                counts[_MARKERS[marker]] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        name, shortened = _label(self.name)
        return {
            "name": name,
            "identity_truncated": shortened,
            "declared": self.declared,
            "observed": self.observed(),
            "cases": [case.to_dict() for case in self.cases],
        }


@dataclass(frozen=True)
class JUnitReport:
    collection_status: CollectionStatus
    suites: tuple[JUnitSuite, ...] = ()
    issues: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a redacted display report, never authenticated run evidence."""
        counts: Counter[str] = Counter(case.outcome for suite in self.suites for case in suite.cases)
        outcome = "unknown"
        if counts["failed"] or counts["error"]:
            outcome = "failed"
        elif self.collection_status == "complete":
            outcome = "passed" if counts["passed"] else "skipped_only" if counts["skipped"] else "empty"
        return dict(
            redact_for_output(
                {
                    "schema_version": "1.0",
                    "kind": "local_pytest_junit",
                    "source_kind": "local_file",
                    "source_verification": "unverified",
                    "revision_binding": "unknown",
                    "run_completion": "unknown",
                    "policy_decision": "not_evaluated",
                    "collection_status": self.collection_status,
                    "reported_outcome": outcome,
                    "counts": {
                        "cases": sum(counts.values()),
                        **{key: counts[key] for key in ("passed", "failed", "error", "skipped")},
                    },
                    "issues": list(self.issues),
                    "suites": [suite.to_dict() for suite in self.suites],
                }
            )
        )


class _RejectedXML(Exception):
    def __init__(self, code: str, status: CollectionStatus = "incomplete") -> None:
        self.code = code
        self.status = status


class _Reader:
    def __init__(self) -> None:
        self.stack: list[str] = []
        self.suites: list[JUnitSuite] = []
        self.issues: set[str] = set()
        self.elements = 0
        self.case_count = 0
        self.case_attributes: dict[str, str] = {}
        self.markers: list[str] = []

    def start(self, name: str, attrs: dict[str, str]) -> None:
        self.elements += 1
        if self.elements > MAX_ELEMENTS or len(self.stack) >= MAX_DEPTH:
            raise _RejectedXML("xml_limit_exceeded")
        parent = self.stack[-1] if self.stack else ""
        if name not in _CHILDREN.get(parent, set()) or "xmlns" in attrs:
            raise _RejectedXML("unsupported_structure")
        self.stack.append(name)
        if name == "testsuites" and any(key in attrs for key in _COUNTERS):
            # Pytest's wrapper has no aggregate counters. Do not silently ignore
            # another producer's conflicting summary or nested-suite dialect.
            raise _RejectedXML("unsupported_structure")
        if name == "testsuite":
            if len(self.suites) >= MAX_SUITES:
                raise _RejectedXML("suite_limit_exceeded")
            declared: dict[str, int | None] = {}
            for key in _COUNTERS:
                raw = attrs.get(key, "")
                declared[key] = int(raw) if re.fullmatch(r"[0-9]{1,9}", raw) else None
            if any(value is None for value in declared.values()):
                self.issues.add("missing_or_invalid_counts")
            self.suites.append(JUnitSuite(attrs.get("name", ""), declared))
        elif name == "testcase":
            self.case_count += 1
            if self.case_count > MAX_CASES:
                raise _RejectedXML("case_limit_exceeded")
            self.case_attributes = attrs
            self.markers = []
            if not attrs.get("name"):
                self.issues.add("missing_case_name")
        elif name in _MARKERS:
            self.markers.append(name)

    def end(self, name: str) -> None:
        if name == "testcase":
            self.suites[-1].cases.append(
                JUnitCase(
                    self.case_attributes.get("name", ""),
                    self.case_attributes.get("classname", ""),
                    tuple(self.markers),
                )
            )
        self.stack.pop()

    def text(self, data: str) -> None:
        if self.stack and self.stack[-1] in _CHILDREN and data.strip():
            raise _RejectedXML("unsupported_structure")
        # Failure messages, tracebacks, properties and captured logs are never
        # retained. They can contain arbitrary secrets, paths or instructions.

    def finish(self) -> JUnitReport:
        if not self.suites:
            self.issues.add("missing_suite")
        for suite in self.suites:
            observed = suite.observed()
            if any(value is not None and value != observed[key] for key, value in suite.declared.items()):
                self.issues.add("count_mismatch")
        return JUnitReport("incomplete" if self.issues else "complete", tuple(self.suites), tuple(sorted(self.issues)))


def _reject_declaration(*args: object) -> None:
    raise _RejectedXML("unsafe_xml", "error")


def _xml_declaration(version: str, encoding: str | None, standalone: int) -> None:
    if version != "1.0" or encoding is not None and encoding.lower() not in {"utf-8", "utf8"}:
        raise _RejectedXML("unsupported_encoding", "error")


def _parse(contents: bytes) -> JUnitReport:
    reader = _Reader()
    parser = expat.ParserCreate()
    parser.StartElementHandler = reader.start
    parser.EndElementHandler = reader.end
    parser.CharacterDataHandler = reader.text
    parser.StartDoctypeDeclHandler = _reject_declaration
    parser.EntityDeclHandler = _reject_declaration
    parser.ProcessingInstructionHandler = _reject_declaration
    parser.XmlDeclHandler = _xml_declaration
    try:
        # One bounded parse avoids repeated parsing of large unfinished tokens.
        # Decode explicitly: pytest writes UTF-8, never compressed/remote input.
        text = contents.decode("utf-8-sig")
        if "\x00" in text:
            return JUnitReport("error", issues=("invalid_xml",))
        parser.Parse(text, True)
    except _RejectedXML as exc:
        return JUnitReport(exc.status, issues=(exc.code,))
    except (expat.ExpatError, UnicodeError, ValueError):
        return JUnitReport("error", issues=("invalid_xml",))
    return reader.finish()


def read_junit_report(path: Path) -> JUnitReport:
    """Inspect one explicitly selected regular local file, without following XML references."""
    try:
        if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
            return JUnitReport("error", issues=("not_regular_file",))
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(path, flags), "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                return JUnitReport("error", issues=("not_regular_file",))
            contents = handle.read(MAX_REPORT_BYTES + 1)
    except (OSError, ValueError):
        return JUnitReport("error", issues=("read_error",))
    if len(contents) > MAX_REPORT_BYTES:
        return JUnitReport("incomplete", issues=("file_limit_exceeded",))
    return _parse(contents)
