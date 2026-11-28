"""Advisory comparison of committed literal CI coverage thresholds."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path, PurePosixPath

from evagix.scanning.coverage_thresholds import ThresholdExtraction, extract_coverage_thresholds
from evagix.scanning.git_snapshot import GitSnapshot, TreeEntry

_SOURCE_LIMIT = 500_000
_FILE_LIMIT = 40
_FINDING_LIMIT = 200


@dataclass(frozen=True)
class CoverageDriftFinding:
    path: str
    job: str
    step_kind: str
    step: str
    previous_value: str
    value: str
    previous_line: int
    previous_column: int
    line: int
    column: int
    code: str = "ci.coverage-threshold-lowered"
    revision: str = "head"
    severity: str = "advisory"


@dataclass(frozen=True)
class CoverageDriftReport:
    base: str
    head: str
    merge_base: str
    inspected_files: list[str]
    compared_thresholds: int
    limitations: list[str]
    findings: list[CoverageDriftFinding]

    @property
    def complete(self) -> bool:
        return not self.limitations


def _workflow_path(path: str) -> bool:
    item = PurePosixPath(path)
    return item.parent.as_posix() == ".github/workflows" and item.suffix in {".yml", ".yaml"}


def _extract(git: GitSnapshot, entry: TreeEntry | None) -> ThresholdExtraction:
    if entry is None or not entry.regular:
        return ThresholdExtraction({}, ["Workflow is missing or is not a regular tracked file."])
    try:
        return extract_coverage_thresholds(git.text(entry, limit=_SOURCE_LIMIT))
    except (RuntimeError, ValueError):
        return ThresholdExtraction({}, ["Workflow content is unavailable, oversized or not UTF-8."])


def build_coverage_drift_report(root: Path, *, base: str = "main", head: str = "HEAD") -> CoverageDriftReport:
    git = GitSnapshot(root)
    base_oid, head_oid = git.resolve(base), git.resolve(head)
    ancestor = git.merge_base(base_oid, head_oid)
    before, after = git.tree(ancestor), git.tree(head_oid)
    candidates = sorted(path for path in before if _workflow_path(path) and before[path] != after.get(path))
    inspected: list[str] = []
    limitations: list[str] = []
    findings: list[CoverageDriftFinding] = []
    compared = 0
    for index, path in enumerate(candidates):
        if index >= _FILE_LIMIT:
            limitations.append("Changed workflow-file limit reached; remaining files were not inspected.")
            break
        previous, current = _extract(git, before[path]), _extract(git, after.get(path))
        inspected.append(path)
        for revision, extraction in (("merge base", previous), ("head", current)):
            limitations.extend(f"{path} ({revision}): {item}" for item in extraction.limitations)
        for key, old in sorted(previous.thresholds.items()):
            new = current.thresholds.get(key)
            if new is None:
                limitations.append(
                    f"{path}:{old.line} (merge base): previous declaration has no comparable literal at head."
                )
                continue
            if old.signature != new.signature:
                limitations.append(
                    f"{path}:{new.line} (head): other command arguments changed; threshold comparison is unresolved."
                )
                continue
            compared += 1
            if Decimal(new.value) >= Decimal(old.value):
                continue
            if len(findings) >= _FINDING_LIMIT:
                limitations.append("Finding limit reached; remaining declarations were not compared.")
                return CoverageDriftReport(base_oid, head_oid, ancestor, inspected, compared, limitations, findings)
            findings.append(
                CoverageDriftFinding(
                    path,
                    new.job,
                    new.step_kind,
                    new.step,
                    old.value,
                    new.value,
                    old.line,
                    old.column,
                    new.line,
                    new.column,
                )
            )
    return CoverageDriftReport(base_oid, head_oid, ancestor, inspected, compared, limitations, findings)
