from __future__ import annotations

import json
from pathlib import Path

import pytest

from evagix.cli import main


def test_public_release_omits_root_generated_context() -> None:
    for generated_path in [
        ".evagix/context.md",
        ".evagix/context.json",
        ".evagix/integrity.json",
    ]:
        assert not Path(generated_path).exists()
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    assert "evagix:generated" not in agents


def test_public_release_without_generated_context_passes_gate(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["doctor", ".", "--strict", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["score"] >= 80
    codes = {item["code"] for item in payload["findings"]}
    assert "missing-onboarding-pack" not in codes
    assert "readme-evidence.tested.manual_review_required" not in codes
    assert "readme-evidence.package-installable.manual_review_required" not in codes
