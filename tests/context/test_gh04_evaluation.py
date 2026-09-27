from __future__ import annotations

import json
from pathlib import Path

import pytest

from evagix.cli import main
from evagix.commands.common import _facts, _targets
from evagix.context_eval import evaluate_context
from evagix.generated_integrity import CONTENT_DIGEST_RE, INTEGRITY_MANIFEST_PATH, attach_content_digest
from evagix.validators import check_repo


def _compile_repo(root: Path, kind: str) -> Path:
    (root / "README.md").write_text("# Demo\n", encoding="utf-8")
    config = (
        '[commands]\ninstall="python -m pip install -e ."\ntest="python -m pytest"\n'
        'lint="python -m ruff check ."\ntypecheck="python -m mypy ."\n'
    )
    if kind == "builtin":
        target = root / ".evagix" / "context.md"
    else:
        # The parent exists before generation so this does not exercise GH-11.
        (root / "exports").mkdir()
        suffix = "json" if kind == "custom_json" else "md"
        target = root / "exports" / f"context.{suffix}"
        config += (
            "[targets]\nuniversal_md=false\nuniversal_json=false\n"
            '[[targets.custom]]\nname="local"\n'
            f'path="exports/context.{suffix}"\nformat="{"json" if suffix == "json" else "markdown"}"\n'
        )
    (root / "evagix.toml").write_text(config, encoding="utf-8")
    assert main(["compile", str(root)]) == 0
    assert main(["check", str(root)]) == 0
    return target


@pytest.mark.parametrize("kind", ["builtin", "custom_markdown", "custom_json"])
@pytest.mark.parametrize(
    "damage",
    ["missing_manifest", "malformed_manifest", "missing_digest", "tampered", "missing", "unmanaged", "invalid_utf8"],
)
def test_gh04_check_failures_reach_evaluation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str, damage: str
) -> None:
    target = _compile_repo(tmp_path, kind)
    manifest = tmp_path / INTEGRITY_MANIFEST_PATH
    if damage == "missing_manifest":
        manifest.unlink()
    elif damage == "malformed_manifest":
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["targets"] = []
        manifest.write_text(attach_content_digest(json.dumps(payload)), encoding="utf-8")
    elif damage == "missing_digest":
        content = target.read_text(encoding="utf-8")
        if target.suffix == ".json":
            payload = json.loads(content)
            del payload["_evagix_content_digest"]
            content = json.dumps(payload)
        else:
            content = CONTENT_DIGEST_RE.sub("", content)
        target.write_text(content, encoding="utf-8")
    elif damage == "tampered":
        content = target.read_text(encoding="utf-8")
        if target.suffix == ".json":
            payload = json.loads(content)
            payload["manual_note"] = "Unreviewed addition"
            content = json.dumps(payload)
        else:
            content += "\nUnreviewed addition.\n"
        target.write_text(content, encoding="utf-8")
    elif damage == "missing":
        target.unlink()
        if kind == "builtin":
            # Explicitly request this target, as check intentionally permits absent defaults.
            config = tmp_path / "evagix.toml"
            config.write_text(config.read_text(encoding="utf-8") + "[targets]\nuniversal_md=true\n", encoding="utf-8")
    elif damage == "unmanaged":
        target.write_text("User-owned context\n", encoding="utf-8")
        if kind == "builtin":
            config = tmp_path / "evagix.toml"
            config.write_text(config.read_text(encoding="utf-8") + "[targets]\nuniversal_md=true\n", encoding="utf-8")
    else:
        target.write_bytes(b"\xff")

    capsys.readouterr()
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    facts, config = _facts(tmp_path)
    check = check_repo(tmp_path, facts, target_keys=_targets(config, None), custom_targets=config.custom_targets)
    assert not check.ok
    assert check.errors
    if damage == "missing_manifest":
        assert not check.stale_targets
        assert not check.tampered_targets
        assert INTEGRITY_MANIFEST_PATH in check.errors[0]
    assert main(["check", str(tmp_path)]) == 1
    capsys.readouterr()

    evaluation = evaluate_context(
        tmp_path, facts, target_keys=_targets(config, None), custom_targets=config.custom_targets
    )
    assert evaluation.management == "evagix"
    assert evaluation.score is not None
    assert not evaluation.ok
    expected_rule = {
        "missing": "generated-context-missing",
        "unmanaged": "generated-context-unmanaged",
        "invalid_utf8": "generated-context-invalid-encoding",
    }.get(damage, "generated-context-tampered")
    expected_severity = "medium" if damage == "missing" else "high"
    expected_status = "warn" if damage == "missing" else "fail"
    finding = next(item for item in evaluation.findings or [] if item["id"] == expected_rule)
    assert finding["severity"] == expected_severity
    affected = INTEGRITY_MANIFEST_PATH if damage.endswith("manifest") else target.relative_to(tmp_path).as_posix()
    assert affected in finding["metadata"]["affected_targets"]
    assert any(item.name == expected_rule and item.status == expected_status for item in evaluation.checks)
    assert main(["eval-context", str(tmp_path), "--strict", "--fail-on", expected_severity, "--format", "json"]) == 1
    payload = json.loads(capsys.readouterr().out)["evaluation"]
    assert payload["ok"] is False
    assert payload["management"] == "evagix"
    assert any(item["name"] == expected_rule and item["status"] == expected_status for item in payload["checks"])
    after = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before


@pytest.mark.parametrize("kind", ["custom_markdown", "custom_json"])
def test_gh04_custom_targets_are_enumerated_without_disabled_defaults(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str
) -> None:
    target = _compile_repo(tmp_path, kind)
    capsys.readouterr()
    assert main(["eval-context", str(tmp_path), "--format", "json"]) == 0
    evaluation = json.loads(capsys.readouterr().out)["evaluation"]
    assert evaluation["management"] == "evagix"
    assert evaluation["score"] is not None
    assert evaluation["target_count"] == 1
    assert evaluation["present_targets"] == [target.relative_to(tmp_path).as_posix()]
    assert evaluation["missing_targets"] == []
    assert not any(item["status"] == "fail" for item in evaluation["checks"])
    assert evaluation["findings"] == []


@pytest.mark.parametrize("disabled_targets", [False, True])
@pytest.mark.parametrize("external", [False, True])
def test_gh04_unconfigured_context_remains_unscored(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], disabled_targets: bool, external: bool
) -> None:
    if external:
        (tmp_path / "AGENTS.md").write_text("# Project instructions\nKeep changes focused.\n", encoding="utf-8")
    if disabled_targets:
        (tmp_path / "evagix.toml").write_text("[targets]\nuniversal_md=false\nuniversal_json=false\n", encoding="utf-8")
    assert main(["check", str(tmp_path)]) == 0
    capsys.readouterr()
    assert main(["eval-context", str(tmp_path), "--format", "json"]) == 0
    evaluation = json.loads(capsys.readouterr().out)["evaluation"]
    assert evaluation["score"] is None
    assert evaluation["score_type"] == ("unscored_external_context" if external else "unscored_missing_context")
    assert evaluation["management"] == ("external" if external else "missing")
    assert evaluation["findings"] == []
    assert evaluation["missing_targets"] == []


@pytest.mark.parametrize("kind", ["builtin", "custom_markdown", "custom_json"])
@pytest.mark.parametrize("threshold", ["high", "medium", "low"])
def test_gh04_review_missing_manifest_preserves_high_severity(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str, threshold: str
) -> None:
    _compile_repo(tmp_path, kind)
    (tmp_path / INTEGRITY_MANIFEST_PATH).unlink()
    assert main(["check", str(tmp_path)]) == 1
    capsys.readouterr()
    assert main(["eval-context", str(tmp_path), "--strict", "--fail-on", threshold, "--format", "json"]) == 1
    evaluation = json.loads(capsys.readouterr().out)["evaluation"]
    assert any(
        finding["severity"] == "high" and INTEGRITY_MANIFEST_PATH in str(finding) for finding in evaluation["findings"]
    )
    assert evaluation["ok"] is False


@pytest.mark.parametrize("threshold", ["high", "medium", "low"])
def test_gh04_review_missing_export_keeps_medium_severity(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], threshold: str
) -> None:
    _compile_repo(tmp_path, "builtin")
    config = tmp_path / "evagix.toml"
    config.write_text(
        config.read_text(encoding="utf-8") + "[targets]\nuniversal_md=true\nuniversal_json=true\nagents=true\n",
        encoding="utf-8",
    )
    assert main(["compile", str(tmp_path)]) == 0
    assert main(["check", str(tmp_path)]) == 0
    (tmp_path / "AGENTS.md").unlink()
    capsys.readouterr()
    expected_exit = 0 if threshold == "high" else 1
    assert (
        main(["eval-context", str(tmp_path), "--strict", "--fail-on", threshold, "--format", "json"]) == expected_exit
    )
    evaluation = json.loads(capsys.readouterr().out)["evaluation"]
    assert [(f["id"], f["severity"]) for f in evaluation["findings"]] == [("generated-context-missing", "medium")]
    assert not any(check["status"] == "fail" for check in evaluation["checks"])


@pytest.mark.parametrize("kind", ["custom_markdown", "custom_json"])
def test_gh04_review_valid_custom_context_passes_strict_low(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str
) -> None:
    target = _compile_repo(tmp_path, kind)
    capsys.readouterr()
    assert main(["eval-context", str(tmp_path), "--strict", "--fail-on", "low", "--format", "json"]) == 0
    evaluation = json.loads(capsys.readouterr().out)["evaluation"]
    assert evaluation["present_targets"] == [target.relative_to(tmp_path).as_posix()]
    assert evaluation["management"] == "evagix"
    assert evaluation["score"] is not None
    assert evaluation["findings"] == []


@pytest.mark.parametrize("threshold", ["high", "medium", "low"])
@pytest.mark.parametrize("external", [False, True])
def test_gh04_review_unconfigured_context_keeps_head_threshold_behavior(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], threshold: str, external: bool
) -> None:
    if external:
        commands = {"install": "python -m pip install -e .", "test": "python -m pytest"}
        (tmp_path / "evagix.toml").write_text(
            "[commands]\n" + "\n".join(f'{key}="{value}"' for key, value in commands.items()), encoding="utf-8"
        )
        (tmp_path / "AGENTS.md").write_text(
            "# Instructions\n" + "\n".join(f"- `{value}`" for value in commands.values()), encoding="utf-8"
        )
    assert main(["eval-context", str(tmp_path), "--strict", "--fail-on", threshold, "--format", "json"]) == 0
    evaluation = json.loads(capsys.readouterr().out)["evaluation"]
    assert evaluation["score"] is None
    assert evaluation["management"] == ("external" if external else "missing")
    assert evaluation["findings"] == []


@pytest.mark.parametrize("threshold", ["high", "medium", "low"])
def test_gh04_missing_manifest_remains_high_with_a_missing_export(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], threshold: str
) -> None:
    _compile_repo(tmp_path, "builtin")
    config = tmp_path / "evagix.toml"
    config.write_text(
        config.read_text(encoding="utf-8") + "[targets]\nuniversal_md=true\nuniversal_json=true\nagents=true\n",
        encoding="utf-8",
    )
    assert main(["compile", str(tmp_path)]) == 0
    assert main(["check", str(tmp_path)]) == 0
    (tmp_path / "AGENTS.md").unlink()
    (tmp_path / INTEGRITY_MANIFEST_PATH).unlink()
    capsys.readouterr()
    assert main(["eval-context", str(tmp_path), "--strict", "--fail-on", threshold, "--format", "json"]) == 1
    findings = json.loads(capsys.readouterr().out)["evaluation"]["findings"]
    assert {(f["id"], f["severity"]) for f in findings} == {
        ("generated-context-tampered", "high"),
        ("generated-context-missing", "medium"),
    }


def test_gh04_custom_context_is_actually_inspected_by_quality_checks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _compile_repo(tmp_path, "custom_json")
    config = tmp_path / "evagix.toml"
    config.write_text(config.read_text(encoding="utf-8") + 'include=["risks"]\n', encoding="utf-8")
    assert main(["compile", str(tmp_path)]) == 0
    assert main(["check", str(tmp_path)]) == 0
    capsys.readouterr()
    assert main(["eval-context", str(tmp_path), "--strict", "--fail-on", "high", "--format", "json"]) == 1
    findings = json.loads(capsys.readouterr().out)["evaluation"]["findings"]
    assert any(f["id"] == "agent-context.missing-test" and f["severity"] == "high" for f in findings)
    assert all(f["id"] != "agent-context.not-configured" for f in findings)
