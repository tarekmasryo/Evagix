from __future__ import annotations

import json
from pathlib import Path

from evagix.cli import main
from evagix.evidence import Finding
from evagix.scanner import scan_repo
from evagix.scoring.engine import score_from_findings
from evagix.strict_scoring import doctor_findings_from_evidence
from evagix.validators import doctor_repo, render_doctor_json


def test_doctor_fail_under_controls_exit_code(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("pytest\nblack\n", encoding="utf-8")
    assert main(["compile", str(tmp_path)]) == 0
    assert main(["doctor", str(tmp_path), "--fail-under", "1"]) == 0
    assert main(["doctor", str(tmp_path), "--fail-under", "99"]) == 1


def test_doctor_report_includes_breakdown_and_maturity(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["pytest", "ruff"]\n',
        encoding="utf-8",
    )
    facts = scan_repo(tmp_path)
    report = doctor_repo(tmp_path, facts)
    assert report.maturity_level in {"clear", "ready", "limited", "early", "not-ready"}
    assert {"agent_context", "commands", "ci", "docs_onboarding", "safety", "project_specific"}.issubset(
        report.categories
    )
    payload = json.loads(render_doctor_json(facts, report))
    assert "categories" in payload
    assert "maturity_level" in payload


def test_doctor_does_not_emit_missing_agent_commands_when_agent_context_absent(tmp_path: Path, capsys) -> None:
    import json

    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname="demo"\nversion="0.1.0"\n', encoding="utf-8")
    main(["doctor", str(tmp_path), "--strict", "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    codes = {finding["code"] for finding in payload["findings"]}
    assert not any(code.startswith("agent-context.missing-") for code in codes)


def test_scoring_engine_penalizes_non_summary_findings_only() -> None:
    findings = [
        Finding(id="high", title="High", severity="high", status="fail", category="safety", source="AGENTS.md"),
        Finding(
            id="summary",
            title="Info",
            severity="high",
            status="warn",
            category="agent-context",
            source="CLAUDE.md",
            summary_only=True,
        ),
    ]

    score = score_from_findings(findings)
    assert score.overall == 88
    assert score.categories == {"safety": 88, "agent-context": 100}
    assert score.blocking is False


def test_shared_severity_penalties_preserve_engine_and_strict_behavior() -> None:
    for severity, penalty in {"critical": 25, "high": 12, "medium": 7, "low": 3}.items():
        finding = Finding(
            id=severity,
            title=severity,
            severity=severity,
            status="fail",
            category="safety",
            source="AGENTS.md",
        )
        assert score_from_findings([finding]).overall == 100 - penalty
        assert doctor_findings_from_evidence([finding])[0].penalty == penalty

    for severity, engine_penalty, strict_penalty in (("info", 0, 6), ("unknown", 3, 6)):
        finding = Finding(
            id=severity,
            title=severity,
            severity=severity,
            status="warn",
            category="safety",
            source="AGENTS.md",
        )
        assert score_from_findings([finding]).overall == 100 - engine_penalty
        assert doctor_findings_from_evidence([finding])[0].penalty == strict_penalty


def test_summary_calibration_and_root_cause_deduplication_are_unchanged() -> None:
    summary = Finding(
        id="summary",
        title="Summary",
        severity="critical",
        status="fail",
        category="safety",
        source="AGENTS.md",
        summary_only=True,
    )
    assert score_from_findings([summary]).overall == 100
    assert doctor_findings_from_evidence([summary])[0].penalty == 0

    calibrated = {
        "readme.read-error": 25,
        "agent-context.missing": 3,
        "agent-context.missing-test": 4,
        "agent-context.missing-install": 2,
        "agent-context.missing-build": 2,
        "agent-context.missing-other": 1,
    }
    findings = [
        Finding(
            id=code,
            title=code,
            severity="low",
            status="warn",
            category="safety",
            source=code,
        )
        for code in calibrated
    ]
    assert [item.penalty for item in doctor_findings_from_evidence(findings)] == list(calibrated.values())

    duplicate_root = [
        Finding(
            id=f"duplicate-{index}",
            title="Duplicate",
            severity="high",
            status="fail",
            category="safety",
            source=f"file-{index}",
            root_cause="shared-root",
        )
        for index in range(2)
    ]
    assert [item.penalty for item in doctor_findings_from_evidence(duplicate_root)] == [12, 2]
