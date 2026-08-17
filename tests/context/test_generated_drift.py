from __future__ import annotations

from pathlib import Path

from evagix.cli import main
from evagix.commands.common import _facts, _targets
from evagix.drift import build_drift_report, drift_report_from_check, render_drift_json, render_drift_markdown
from evagix.validators import check_repo


def _managed_repo(root: Path) -> None:
    (root / "README.md").write_text("# Demo\n\nRun `python -m pytest`.\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["pytest", "ruff"]\n',
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    (root / "evagix.toml").write_text(
        "\n".join(
            [
                "[commands]",
                'test = "python -m pytest"',
                "",
                "[targets]",
                "universal_md = true",
                "universal_json = true",
                "agents = true",
            ]
        ),
        encoding="utf-8",
    )


def _facts_and_targets(root: Path):
    facts, config = _facts(root)
    return facts, _targets(config, None)


def test_drift_report_detects_fresh_and_stale_generated_context(tmp_path: Path, capsys) -> None:
    _managed_repo(tmp_path)
    assert main(["compile", str(tmp_path)]) == 0
    capsys.readouterr()
    facts, targets = _facts_and_targets(tmp_path)

    fresh = build_drift_report(tmp_path, facts, target_keys=targets)
    assert fresh.ok is True
    assert fresh.status == "in-sync"
    assert fresh.stale_targets == []

    config = tmp_path / "evagix.toml"
    config.write_text(
        config.read_text(encoding="utf-8").replace("python -m pytest", "python -m pytest -q"), encoding="utf-8"
    )
    facts, targets = _facts_and_targets(tmp_path)
    stale = build_drift_report(tmp_path, facts, target_keys=targets)
    assert stale.ok is False
    assert stale.status == "drift-detected"
    assert ".evagix/context.md" in stale.stale_targets
    assert "evagix sync" in stale.recommended_fix


def test_drift_report_detects_missing_and_corrupt_fingerprints(tmp_path: Path, capsys) -> None:
    _managed_repo(tmp_path)
    assert main(["compile", str(tmp_path)]) == 0
    capsys.readouterr()
    context = tmp_path / ".evagix" / "context.md"
    original = context.read_text(encoding="utf-8")

    context.write_text(original.replace("evagix:fingerprint=", "evagix:fingerprint-corrupt="), encoding="utf-8")
    facts, targets = _facts_and_targets(tmp_path)
    missing = build_drift_report(tmp_path, facts, target_keys=targets)
    assert missing.ok is False
    assert ".evagix/context.md" in missing.stale_targets

    context.write_text(original.replace("evagix:fingerprint=", "evagix:fingerprint=deadbeef"), encoding="utf-8")
    corrupt = build_drift_report(tmp_path, facts, target_keys=targets)
    assert corrupt.ok is False
    assert ".evagix/context.md" in corrupt.stale_targets


def test_drift_renderers_include_grouped_status_and_lists(tmp_path: Path, capsys) -> None:
    _managed_repo(tmp_path)
    assert main(["compile", str(tmp_path)]) == 0
    capsys.readouterr()
    context = tmp_path / ".evagix" / "context.md"
    context.write_text(
        context.read_text(encoding="utf-8").replace("evagix:fingerprint=", "evagix:fingerprint=deadbeef"),
        encoding="utf-8",
    )
    facts, targets = _facts_and_targets(tmp_path)
    result = check_repo(tmp_path, facts, target_keys=targets)
    report = drift_report_from_check(facts, result)

    markdown = render_drift_markdown(report)
    json_text = render_drift_json(report)
    assert "Status: `drift-detected`" in markdown
    assert "## Stale targets" in markdown
    assert '"status": "drift-detected"' in json_text
    assert '"stale_targets"' in json_text
