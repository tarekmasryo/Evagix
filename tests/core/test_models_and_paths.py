from __future__ import annotations

from pathlib import Path

from evagix.core.models import (
    CommandEvidence,
    ScoreBreakdown,
)
from evagix.core.paths import repo_relative
from evagix.evidence import Finding


def test_core_model_serialization_is_stable() -> None:
    command = CommandEvidence(
        name="test", command="pytest", source_file="README.md", source_line=12, confidence="high", ecosystem="python"
    )
    breakdown = ScoreBreakdown(overall=95, categories={"readme": 95}, blocking=False)

    assert command.to_dict()["command"] == "pytest"
    assert breakdown.to_dict()["categories"] == {"readme": 95}


def test_finding_is_deeply_immutable_and_hashable() -> None:
    finding = Finding(
        id="immutable",
        title="Immutable",
        severity="medium",
        status="fail",
        category="safety",
        evidence=["one"],
        missing=["two"],
        metadata={"nested": ["three"]},
    )

    assert finding.evidence == ("one",)
    assert finding.missing == ("two",)
    assert finding.metadata["nested"] == ("three",)
    assert isinstance(hash(finding), int)
    assert finding.to_dict()["metadata"] == {"nested": ["three"]}


def test_repo_relative_handles_inside_and_outside_paths(tmp_path: Path) -> None:
    inside = tmp_path / "README.md"
    outside = tmp_path.parent / "outside.txt"

    assert repo_relative(tmp_path, inside) == "README.md"
    assert repo_relative(tmp_path, outside).endswith("outside.txt")
