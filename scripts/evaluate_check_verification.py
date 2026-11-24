"""Evaluate the preview contract against frozen synthetic cases, without CI access."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from evagix.security.redaction import redact_for_output
from evagix.verification import ContractError, SourceAssessment, evaluate_check, parse_batch, parse_request

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "tests" / "fixtures" / "check-verification" / "manifest.json"
CONDITIONS = {"supported", "contradicted", "unverified", "invalid_input"}
MODES = {"verified", "unverified", "missing", "mismatched_digest"}


class DatasetError(ValueError):
    """Invalid evaluation input; messages contain no supplied values."""


def _read(path: Path, limit: int) -> bytes:
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise DatasetError("Evaluation input exceeds size limit")
    return data


def _object(value: object, fields: set[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != fields:
        raise DatasetError("Invalid evaluation object fields")
    return value


def _label(value: object) -> None:
    if type(value) is not str or not 1 <= len(value) <= 128 or not value.isprintable():
        raise DatasetError("Invalid evaluation label")


def load_cases(manifest_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = _object(
        json.loads(_read(manifest_path, 64_000)),
        {
            "dataset_version",
            "file",
            "sha256",
            "case_count",
            "provenance",
            "limitations",
        },
    )
    if manifest["dataset_version"] != "1.0":
        raise DatasetError("Unsupported dataset version")
    filename = manifest["file"]
    if type(filename) is not str or not re.fullmatch(r"[a-zA-Z0-9_-]+\.json", filename):
        raise DatasetError("Invalid dataset filename")
    path = (manifest_path.resolve().parent / filename).resolve()
    if path.parent != manifest_path.resolve().parent:
        raise DatasetError("Dataset must remain beside its manifest")
    data = _read(path, 16_000_000)
    if hashlib.sha256(data).hexdigest() != manifest["sha256"]:
        raise DatasetError("Dataset digest mismatch")
    payload = _object(json.loads(data), {"dataset_version", "cases"})
    cases = payload["cases"]
    if (
        payload["dataset_version"] != manifest["dataset_version"]
        or type(manifest["case_count"]) is not int
        or type(cases) is not list
        or not 1 <= len(cases) <= 2000
        or len(cases) != manifest["case_count"]
    ):
        raise DatasetError("Invalid dataset inventory")
    identifiers = set()
    for case in cases:
        _object(case, {"id", "segment", "request", "batch", "assessment", "expected"})
        _label(case["id"])
        _label(case["segment"])
        if case["id"] in identifiers:
            raise DatasetError("Duplicate evaluation case ID")
        identifiers.add(case["id"])
        if type(case["assessment"]) is not str or case["assessment"] not in MODES:
            raise DatasetError("Invalid fixture assessment mode")
        expected = _object(case["expected"], {"condition", "reason"})
        if type(expected["condition"]) is not str or expected["condition"] not in CONDITIONS:
            raise DatasetError("Invalid expected condition")
        if expected["condition"] == "invalid_input":
            if expected["reason"] is not None:
                raise DatasetError("Invalid expected input error")
        else:
            _label(expected["reason"])
    return manifest, cases


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    try:
        check_request, batch = parse_request(case["request"]), parse_batch(case["batch"])
        mode = case["assessment"]
        assessment = None
        if mode != "missing":
            digest = batch.digest()
            if mode == "mismatched_digest":
                digest = ("1" if digest[0] == "0" else "0") + digest[1:]
            # Fixture-only assessment: this is not a source authentication adapter.
            assessment = SourceAssessment(
                digest, "unverified" if mode == "unverified" else "verified", "synthetic-fixture"
            )
    except ContractError:
        return {"condition": "invalid_input", "reason": None}
    # A failure evaluating valid parsed inputs is a runner error, not an input-error match.
    result = evaluate_check(check_request, batch, assessment=assessment)
    return {"condition": result.condition, "reason": result.reason}


def implementation_digest() -> str:
    paths = [
        *sorted((ROOT / "evagix" / "verification").glob("*.py")),
        *sorted((ROOT / "evagix" / "security").glob("*.py")),
        ROOT / "evagix" / "schemas" / "check-verification.schema.json",
        Path(__file__).resolve(),
    ]
    hashes = {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    return hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def evaluate_corpus(manifest_path: Path) -> dict[str, Any]:
    manifest, cases = load_cases(manifest_path)
    rows = []
    segments: dict[str, dict[str, int]] = {}
    confusion: Counter[str] = Counter()
    for case in cases:
        actual = evaluate_case(case)
        expected = case["expected"]
        matches = actual == expected
        false_support = actual["condition"] == "supported" and expected["condition"] != "supported"
        rows.append(
            {"id": case["id"], "segment": case["segment"], "expected": expected, "actual": actual, "matches": matches}
        )
        counts = segments.setdefault(case["segment"], {"cases": 0, "disagreements": 0, "false_support": 0})
        counts["cases"] += 1
        counts["disagreements"] += int(not matches)
        counts["false_support"] += int(false_support)
        confusion[f"{expected['condition']} -> {actual['condition']}"] += 1
    disagreements = sum(counts["disagreements"] for counts in segments.values())
    false_support = sum(counts["false_support"] for counts in segments.values())
    report = {
        "dataset_version": manifest["dataset_version"],
        "dataset_sha256": manifest["sha256"],
        "implementation_sha256": implementation_digest(),
        "cases": len(cases),
        "disagreements": disagreements,
        "false_support": false_support,
        "passed": disagreements == 0 and false_support == 0,
        "segments": segments,
        "confusion_counts": dict(sorted(confusion.items())),
        "results": rows,
        "scope": "Synthetic contract evaluation; assessments are simulated. No production accuracy or CI authentication claim.",
    }
    return dict(redact_for_output(report))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, help="Create a new report; existing files are never overwritten")
    args = parser.parse_args(argv)
    try:
        report = evaluate_corpus(args.manifest)
        output = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
        if args.output is None:
            print(output, end="")
        else:
            with args.output.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(output)
    except (OSError, UnicodeError, ValueError, RecursionError):
        print("Evaluation could not complete; check the dataset contract and output location.", file=sys.stderr)
        return 2
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
