from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from evagix.cli import main
from evagix.config import load_config
from evagix.core.io import DEFAULT_MAX_TEXT_CHARS


def _pad_config(body: str, size: int, fill: str = "x") -> str:
    return body + "#" + fill * (size - len(body) - 2) + "\n"


def _oversized_config() -> str:
    prefix = _pad_config('[commands]\ntest = "python -m pytest"\n', DEFAULT_MAX_TEXT_CHARS)
    assert tomllib.loads(prefix) == {"commands": {"test": "python -m pytest"}}
    return prefix + "[policy]\nfail_under = 100\n"


@pytest.mark.parametrize("filename", ["evagix.toml", ".evagix.toml"])
def test_truncated_config_is_not_accepted_as_a_complete_valid_prefix(tmp_path: Path, filename: str) -> None:
    text = _oversized_config()
    assert tomllib.loads(text)["policy"]["fail_under"] == 100
    path = tmp_path / filename
    path.write_text(text, encoding="utf-8", newline="\n")

    config = load_config(tmp_path)

    assert not config.valid
    assert config.path == path
    assert "incomplete" in config.parse_error.lower()
    assert "truncated" in config.parse_error.lower()
    assert str(DEFAULT_MAX_TEXT_CHARS) in config.parse_error
    assert not config.custom_validation_commands


@pytest.mark.parametrize("extra", [-1, 0, 1], ids=["below-limit", "exact-limit", "over-limit"])
@pytest.mark.parametrize("fill", ["x", "é"], ids=["ascii", "multibyte"])
def test_config_limit_is_character_based_and_exact_limit_is_allowed(tmp_path: Path, extra: int, fill: str) -> None:
    text = _pad_config("[policy]\nfail_under = 100\n", DEFAULT_MAX_TEXT_CHARS + extra, fill)
    (tmp_path / "evagix.toml").write_text(text, encoding="utf-8", newline="\n")

    config = load_config(tmp_path)

    if extra > 0:
        assert not config.valid
        assert "truncated" in config.parse_error.lower()
    else:
        assert config.valid
        assert config.parse_error == ""
        assert config.fail_under == 100


def test_malformed_config_keeps_its_toml_parse_diagnostic(tmp_path: Path) -> None:
    (tmp_path / "evagix.toml").write_text("[policy\nfail_under = 100\n", encoding="utf-8")

    config = load_config(tmp_path)

    assert not config.valid
    assert config.parse_error.startswith("TOMLDecodeError:")


@pytest.mark.parametrize("verb", ["scan", "compile"])
def test_cli_rejects_truncated_config_before_publishing_defaults(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], verb: str
) -> None:
    (tmp_path / "evagix.toml").write_text(_oversized_config(), encoding="utf-8", newline="\n")

    with pytest.raises(SystemExit) as exc:
        main([verb, str(tmp_path)])

    captured = capsys.readouterr()
    assert exc.value.code == 1
    assert "Invalid Evagix config" in captured.err
    assert "evagix.toml" in captured.err
    assert "incomplete" in captured.err.lower()
    assert "truncated" in captured.err.lower()
    assert "Traceback" not in captured.err
    assert not captured.out
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / ".evagix" / "context.md").exists()
