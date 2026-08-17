from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from evagix.core.io import UnsafePathError, safe_read_text
from evagix.evidence import write_evidence_json


def test_safe_read_text_uses_bounded_read_when_max_chars_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "large.txt"
    target.write_text("abcdef", encoding="utf-8")
    original_open = Path.open
    read_sizes: list[int | None] = []

    class RecordingHandle:
        def __enter__(self) -> RecordingHandle:
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def read(self, size: int | None = None) -> str:
            read_sizes.append(size)
            return "abcdef"[: size if size is not None else None]

    def fake_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self == target:
            return RecordingHandle()
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fake_open)

    assert safe_read_text(target, max_chars=3) == "abc"
    assert read_sizes == [3]


def test_safe_read_text_reads_full_file_when_no_limit_is_set(tmp_path: Path) -> None:
    target = tmp_path / "small.txt"
    target.write_text("abcdef", encoding="utf-8")

    assert safe_read_text(target) == "abcdef"


def test_safe_read_text_respects_encoding_error_policy(tmp_path: Path) -> None:
    target = tmp_path / "invalid.txt"
    target.write_bytes(b"\xffabc")

    assert safe_read_text(target, errors="ignore") == "abc"


def test_safe_read_text_rejects_symlinks_inside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-evagix-secret.txt"
    outside.write_text("secret", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks are not available on this platform")

    with pytest.raises(UnsafePathError):
        safe_read_text(link, root=tmp_path)


def test_safe_read_text_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        safe_read_text(tmp_path / "missing.txt")


def test_write_evidence_json_rejects_output_path_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-evidence.json"

    with pytest.raises(ValueError, match="inside repository root"):
        write_evidence_json(tmp_path, "demo", [], "../outside-evidence.json")

    assert not outside.exists()


def test_write_evidence_json_writes_inside_repository_root(tmp_path: Path) -> None:
    output = write_evidence_json(tmp_path, "demo", [], ".evagix/evidence.json")

    assert output == tmp_path.resolve() / ".evagix" / "evidence.json"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["tool"] == "evagix"
    assert payload["repository"] == "demo"
