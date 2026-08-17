from __future__ import annotations

import sys
from io import BytesIO, TextIOWrapper
from pathlib import Path

from pytest import MonkeyPatch

from evagix.cli import main
from evagix.security.output import execute_with_redacted_output
from evagix.security.redaction import REDACTION_MARKER


def _encoded_stream(encoding: str) -> tuple[BytesIO, TextIOWrapper]:
    raw = BytesIO()
    return raw, TextIOWrapper(raw, encoding=encoding, newline="")


def test_stdout_escapes_text_unsupported_by_stream_encoding(monkeypatch: MonkeyPatch) -> None:
    raw, stream = _encoded_stream("cp1252")
    monkeypatch.setattr(sys, "stdout", stream)

    execute_with_redacted_output(lambda: print("before 🙂 after"))

    assert raw.getvalue().decode("cp1252") == r"before \U0001f642 after" + "\n"


def test_stderr_escapes_text_unsupported_by_stream_encoding(monkeypatch: MonkeyPatch) -> None:
    raw, stream = _encoded_stream("cp1252")
    monkeypatch.setattr(sys, "stderr", stream)

    execute_with_redacted_output(lambda: print("error 🙂 context", file=sys.stderr))

    assert raw.getvalue().decode("cp1252") == r"error \U0001f642 context" + "\n"


def test_agents_cli_safely_emits_unicode_repository_path(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    rules = tmp_path / ".cursor" / "rules"
    rules.mkdir(parents=True)
    (rules / "🙂.md").write_text("# Safe rules\n", encoding="utf-8")
    raw, stream = _encoded_stream("cp1252")
    monkeypatch.setattr(sys, "stdout", stream)

    assert main(["agents", str(tmp_path)]) == 0

    output = raw.getvalue().decode("cp1252")
    assert r".cursor/rules/\U0001f642.md" in output
    assert "Detected agent context files:" in output


def test_utf8_stream_preserves_unicode_text(monkeypatch: MonkeyPatch) -> None:
    raw, stream = _encoded_stream("utf-8")
    monkeypatch.setattr(sys, "stdout", stream)

    execute_with_redacted_output(lambda: print("🙂"))

    assert raw.getvalue().decode("utf-8") == "🙂\n"


def test_redaction_precedes_encoding_fallback(monkeypatch: MonkeyPatch) -> None:
    secret = "unicode-output-secret"
    raw, stream = _encoded_stream("cp1252")
    monkeypatch.setattr(sys, "stdout", stream)

    execute_with_redacted_output(lambda: print(f"DB_PASSWORD={secret} 🙂"))

    output = raw.getvalue().decode("cp1252")
    assert secret not in output
    assert REDACTION_MARKER in output
    assert r"\U0001f642" in output


def test_ascii_output_is_byte_equivalent(monkeypatch: MonkeyPatch) -> None:
    raw, stream = _encoded_stream("cp1252")
    monkeypatch.setattr(sys, "stdout", stream)

    execute_with_redacted_output(lambda: print("plain ASCII output"))

    assert raw.getvalue() == b"plain ASCII output\n"
