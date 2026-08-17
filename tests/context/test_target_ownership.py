from __future__ import annotations

import json
from pathlib import Path

from pytest import CaptureFixture

from evagix.cli import main
from evagix.commands.common import _facts
from evagix.validation.doctor import doctor_repo


def _write_custom_target_repo(root: Path) -> Path:
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["pytest", "ruff"]\n',
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    (root / "evagix.toml").write_text(
        """
[targets]
universal_md = false
universal_json = false
agents = false
claude = false
gemini = false
cursor = false
copilot = false
windsurf = false

[[targets.custom]]
name = "local_agent"
path = ".evagix/local-agent.json"
format = "json"
include = ["facts", "commands", "risks"]
""".strip(),
        encoding="utf-8",
    )
    return root / ".evagix" / "local-agent.json"


def test_filtered_custom_json_is_managed_and_idempotent(tmp_path: Path) -> None:
    target = _write_custom_target_repo(tmp_path)

    assert main(["compile", str(tmp_path)]) == 0
    first = target.read_bytes()
    assert main(["compile", str(tmp_path)]) == 0
    second = target.read_bytes()
    assert main(["compile", str(tmp_path)]) == 0
    third = target.read_bytes()
    assert main(["check", str(tmp_path)]) == 0

    assert first == second == third
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["_evagix_generated"] == "evagix:generated"
    assert payload["_evagix_fingerprint"].startswith("evagix:fingerprint=")
    assert len(payload["_evagix_content_digest"]) == 64
    assert payload["custom_target"]["name"] == "local_agent"


def test_configured_unmanaged_target_fails_check(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    target = _write_custom_target_repo(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_text('{"owner": "user"}\n', encoding="utf-8")

    assert main(["check", str(tmp_path)]) == 1
    output = capsys.readouterr()
    combined = output.out + output.err
    assert "not Evagix-managed" in combined
    assert "Evagix check passed" not in combined

    facts, config = _facts(tmp_path)
    report = doctor_repo(
        tmp_path,
        facts,
        custom_targets=config.custom_targets,
        fail_on_stale=config.fail_on_stale,
        strict=True,
        require_onboarding_pack=config.require_onboarding_pack,
    )
    assert any(item.code == "generated-context-unmanaged" for item in report.findings)
