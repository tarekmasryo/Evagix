from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from evagix.cli import main
from evagix.decide import decide_repo
from evagix.readme_audit import audit_readme, read_readme_source
from evagix.scanner import scan_repo
from evagix.utils import has_readme

README_LIMIT = 150_000


def _audit(root: Path):
    return audit_readme(root, scan_repo(root), strict=True)


@pytest.mark.parametrize(
    ("length", "expected_status", "expected_complete"),
    [
        (README_LIMIT - 1, "complete", True),
        (README_LIMIT, "complete", True),
        (README_LIMIT + 1, "truncated", False),
    ],
)
def test_readme_character_limit_is_reported_exactly(
    tmp_path: Path, length: int, expected_status: str, expected_complete: bool
) -> None:
    (tmp_path / "README.md").write_text("x" * length, encoding="utf-8")

    report = _audit(tmp_path)

    assert report.status.value == expected_status
    assert report.complete is expected_complete
    assert report.chars_read == min(length, README_LIMIT)
    assert report.max_chars == README_LIMIT


def test_multibyte_unicode_near_limit_uses_character_boundary(tmp_path: Path) -> None:
    text = "x" * (README_LIMIT - 1) + "é"
    assert len(text) == README_LIMIT
    (tmp_path / "README.md").write_text(text, encoding="utf-8")

    report = _audit(tmp_path)

    assert report.status.value == "complete"
    assert report.complete is True
    assert report.chars_read == README_LIMIT


def test_claim_after_readme_limit_cannot_produce_false_clean(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("x" * (README_LIMIT + 1) + "\nDocker support\n", encoding="utf-8")

    report = _audit(tmp_path)

    assert report.status.value == "truncated"
    assert report.complete is False
    assert report.score == 0
    assert {item.id for item in report.findings} == {"readme.scan-truncated"}


def test_claim_before_readme_limit_is_still_audited_when_truncated(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n\nDocker support\n" + "x" * README_LIMIT,
        encoding="utf-8",
    )

    report = _audit(tmp_path)

    assert report.status.value == "truncated"
    assert any(item.claim == "dockerized" and item.verdict == "unsupported" for item in report.claims)
    assert any(item.id == "readme.scan-truncated" for item in report.findings)


def test_missing_and_empty_readmes_have_distinct_statuses(tmp_path: Path) -> None:
    missing = _audit(tmp_path)
    assert missing.status.value == "missing"
    assert missing.complete is True
    assert missing.readme_path == ""
    assert missing.score == 0

    (tmp_path / "README.md").write_text("", encoding="utf-8")
    empty = _audit(tmp_path)
    assert empty.status.value == "empty"
    assert empty.complete is True
    assert empty.readme_path == "README.md"
    assert empty.score == 0
    assert {item.id for item in empty.findings} == {"readme.empty"}


def test_invalid_utf8_is_a_high_incomplete_finding_without_byte_leak(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_bytes(b"SECRET_SENTINEL\xff\xfe")

    report = _audit(tmp_path)

    assert report.status.value == "invalid_utf8"
    assert report.complete is False
    assert report.score == 0
    assert {item.id for item in report.findings} == {"text.invalid-utf8"}
    assert report.findings[0].severity == "high"
    assert "SECRET_SENTINEL" not in json.dumps(report.findings[0].to_dict())


def test_read_error_is_reported_without_exposing_exception_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from evagix.readme import source as readme_source

    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")

    def deny_read(*args: object, **kwargs: object) -> object:
        raise PermissionError("PRIVATE_PATH_SENTINEL")

    monkeypatch.setattr(readme_source, "safe_read_text_result", deny_read)
    report = _audit(tmp_path)

    assert report.status.value == "read_error"
    assert report.complete is False
    assert report.score == 0
    assert {item.id for item in report.findings} == {"readme.read-error"}
    assert "PRIVATE_PATH_SENTINEL" not in json.dumps(report.findings[0].to_dict())


def test_dangling_readme_entry_is_not_treated_as_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from evagix.readme import source as readme_source

    monkeypatch.setattr(os.path, "lexists", lambda path: Path(path).name == "README.md")

    def missing_target(*args: object, **kwargs: object) -> object:
        raise FileNotFoundError("DANGLING_TARGET_SENTINEL")

    monkeypatch.setattr(readme_source, "safe_read_text_result", missing_target)
    source = read_readme_source(tmp_path)

    assert source.path == "README.md"
    assert source.status.value == "read_error"
    assert source.complete is False
    assert has_readme(tmp_path) is True


def test_real_dangling_readme_symlink_fails_strict_audit(tmp_path: Path, capsys) -> None:
    readme = tmp_path / "README.md"
    try:
        readme.symlink_to("does-not-exist.md")
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable in this environment: {exc}")

    assert main(["readme-audit", str(tmp_path), "--strict", "--format", "json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "read_error"
    assert payload["complete"] is False
    assert payload["score"] == 0
    assert {item["id"] for item in payload["findings"]} == {"readme.read-error"}
    assert "does-not-exist.md" not in json.dumps(payload)


def test_readme_audit_outputs_incomplete_state_and_strict_exit_code(tmp_path: Path, capsys) -> None:
    (tmp_path / "README.md").write_bytes(b"SECRET_SENTINEL\xff")

    assert main(["readme-audit", str(tmp_path), "--format", "json"]) == 0
    non_strict = json.loads(capsys.readouterr().out)
    assert non_strict["complete"] is False
    assert non_strict["status"] == "invalid_utf8"
    assert non_strict["score"] == 0
    assert {item["id"] for item in non_strict["findings"]} == {"text.invalid-utf8"}

    assert main(["readme-audit", str(tmp_path), "--strict", "--format", "json"]) == 1
    strict = json.loads(capsys.readouterr().out)
    assert strict["complete"] is False
    assert "SECRET_SENTINEL" not in json.dumps(strict)

    assert main(["readme-audit", str(tmp_path), "--strict", "--format", "github-annotations"]) == 1
    annotations = capsys.readouterr().out
    assert "text.invalid-utf8" in annotations
    assert "::error" in annotations


@pytest.mark.parametrize("output_format", ["json", "markdown", "sarif", "pr-comment", "github-annotations"])
def test_doctor_strict_propagates_incomplete_readme_to_every_output(tmp_path: Path, capsys, output_format: str) -> None:
    (tmp_path / "README.md").write_bytes(b"\xff")

    assert main(["doctor", str(tmp_path), "--strict", "--fail-under", "0", "--format", output_format]) == 1
    output = capsys.readouterr().out
    assert "text.invalid-utf8" in output
    if output_format == "json":
        payload = json.loads(output)
        assert payload["ok"] is False
        assert any(item["severity"] == "error" for item in payload["findings"])


def test_evidence_and_decide_consume_readme_incomplete_finding(tmp_path: Path, capsys) -> None:
    (tmp_path / "README.md").write_bytes(b"\xff")
    facts = scan_repo(tmp_path)

    assert main(["evidence", str(tmp_path), "--format", "json"]) == 0
    evidence = json.loads(capsys.readouterr().out)
    assert any(item["id"] == "text.invalid-utf8" for item in evidence["findings"])

    decision = decide_repo(tmp_path, facts)
    assert decision.readiness == "not-ready"
    assert any("README audit incomplete" in item for item in decision.rationale)
