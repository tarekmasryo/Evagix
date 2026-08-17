from __future__ import annotations

from pathlib import Path

import pytest
from pytest import CaptureFixture

from evagix.cli import main
from evagix.config import load_config


def _minimal_repo(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["pytest", "ruff"]\n',
        encoding="utf-8",
    )
    (root / "tests").mkdir()


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ('[commands]\nempty = ""\n', "commands.empty must be a non-empty string"),
        ('[commands]\nempty = "   "\n', "commands.empty must be a non-empty string"),
        ("[commands]\nempty = 123\n", "commands.empty must be a non-empty string"),
    ],
)
def test_invalid_custom_commands_are_rejected(tmp_path: Path, body: str, expected: str) -> None:
    (tmp_path / "evagix.toml").write_text(body, encoding="utf-8")

    config = load_config(tmp_path)

    assert config.parse_error
    assert expected in config.parse_error


def test_valid_custom_command_is_accepted(tmp_path: Path) -> None:
    (tmp_path / "evagix.toml").write_text('[commands]\ntest = "python -m pytest"\n', encoding="utf-8")

    config = load_config(tmp_path)

    assert not config.parse_error
    assert config.custom_validation_commands["test"] == "python -m pytest"


def test_custom_target_path_escape_is_rejected_cleanly(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    _minimal_repo(tmp_path)
    (tmp_path / "evagix.toml").write_text(
        """
[[targets.custom]]
name = "escape"
path = "../escape.md"
format = "markdown"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc:
        main(["compile", str(tmp_path), "--dry-run"])

    captured = capsys.readouterr()
    assert exc.value.code == 1
    assert "Invalid Evagix config" in captured.err
    assert "targets.custom[0].path must stay inside repository root" in captured.err
    assert "Traceback" not in captured.err


def test_invalid_evagix_toml_is_reported(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    (tmp_path / "evagix.toml").write_text("[targets\nagents = true\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        main(["compile", str(tmp_path), "--dry-run"])
    assert exc.value.code == 1
    assert "Invalid Evagix config" in capsys.readouterr().err


def test_invalid_utf8_evagix_toml_is_rejected(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    (tmp_path / "evagix.toml").write_bytes(b"[policy]\nfail_\xffunder = 81\n")

    config = load_config(tmp_path)
    assert config.parse_error.startswith("UnicodeDecodeError:")
    assert config.fail_under == 80

    with pytest.raises(SystemExit) as exc:
        main(["compile", str(tmp_path), "--dry-run"])
    assert exc.value.code == 1
    assert "Invalid Evagix config" in capsys.readouterr().err


def test_invalid_config_unknown_keys_and_types_are_rejected(tmp_path: Path) -> None:
    (tmp_path / "evagix.toml").write_text(
        "\n".join(
            [
                "[policy]",
                'fail_under = "eighty"',
                "unknown_policy_key = true",
                "",
                "[unknown_section]",
                'foo = "bar"',
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(tmp_path)
    assert config.parse_error
    assert "unknown root key: unknown_section" in config.parse_error
    assert "unknown policy key: unknown_policy_key" in config.parse_error
    assert "policy.fail_under must be an integer from 0 to 100" in config.parse_error
