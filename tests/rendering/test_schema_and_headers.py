from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from evagix.cli import main
from evagix.model import Evidence
from evagix.scanner import scan_repo
from evagix.validators import doctor_repo, render_doctor_json


def _make_repo(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["pytest", "ruff"]\n',
        encoding="utf-8",
    )
    (root / "tests").mkdir()


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.mark.parametrize("label, expected", [("high", 0.9), ("medium", 0.65), ("low", 0.35)])
def test_evidence_confidence_label_and_score_are_consistent(label: str, expected: float) -> None:
    assert Evidence("fixture", "evidence", label).confidence_score == expected


def test_evidence_rejects_conflicting_explicit_confidence_score() -> None:
    with pytest.raises(ValueError, match="confidence_score"):
        Evidence("fixture", "evidence", "high", confidence_score=0.6)


def test_scan_schema_rejects_conflicting_confidence_payload() -> None:
    schema = json.loads(Path("evagix/schemas/scan-facts.schema.json").read_text(encoding="utf-8"))
    payload = {
        "schema_version": "1.0",
        "root_name": "demo",
        "languages": [],
        "runtimes": [],
        "package_managers": [],
        "frameworks": [],
        "commands": {"test": "pytest"},
        "command_sources": {
            "test": {
                "source": "fixture",
                "detail": "fixture",
                "confidence": "high",
                "confidence_score": 0.6,
                "status": "declared",
                "reason": "",
                "path": "",
                "line": None,
            }
        },
        "ci_platforms": [],
        "infrastructure_tools": [],
        "container_platforms": [],
    }

    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(payload)


def test_scan_schema_requires_version_runtimes_and_package_managers() -> None:
    schema = json.loads(Path("evagix/schemas/scan-facts.schema.json").read_text(encoding="utf-8"))

    assert {"schema_version", "runtimes", "package_managers"}.issubset(schema["required"])
    assert schema["properties"]["schema_version"] == {"const": "1.0"}
    assert schema["properties"]["runtimes"]["items"] == {"type": "string"}
    assert schema["properties"]["package_managers"]["items"] == {"type": "string"}


def test_generated_headers_are_date_free(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    assert main(["compile", str(tmp_path)]) == 0
    content = (tmp_path / ".evagix" / "context.md").read_text(encoding="utf-8")

    assert "evagix:generated" in content
    assert "evagix:fingerprint=" in content
    assert "generated_at=" not in content


def test_doctor_json_schema_fields_are_stable():
    facts = scan_repo(FIXTURES / "polyglot_monorepo")
    payload = json.loads(render_doctor_json(facts, doctor_repo(FIXTURES / "polyglot_monorepo", facts), fail_under=80))
    assert payload["schema_version"] == "1.0"
    assert payload["tool"] == "evagix"
    assert isinstance(payload["findings"], list)
