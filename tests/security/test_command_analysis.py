from __future__ import annotations

import pytest

from evagix.command_analysis import analyze_command


@pytest.mark.parametrize("command", ["env", "sudo env", "command env", "/usr/bin/env"])
def test_bare_env_variants_are_flagged(command: str) -> None:
    assert {item.rule_id for item in analyze_command(command)} == {"dangerous-command.print-env"}


@pytest.mark.parametrize(
    "command",
    ["env VAR=value pytest", "/usr/bin/env python -m pytest", "env --help", "env -i python -m pytest"],
)
def test_env_wrapper_variants_are_not_flagged(command: str) -> None:
    assert "dangerous-command.print-env" not in {item.rule_id for item in analyze_command(command)}


@pytest.mark.parametrize(
    "command",
    [
        "cat .env",
        "cat ./.env",
        "cat -- .env",
        "cat -n README.md .env",
        "cat .env.production",
        "cat config/.env.production.local",
        'cat "config with spaces/.env"',
        r"type .\.env",
        r"type README.md config\.env.production",
        "Get-Content .env",
        "Get-Content -LiteralPath .env",
        r"Get-Content -LiteralPath '.\.env'",
        "Get-Content -Path:.env",
        "Get-Content -LiteralPath:.env",
        "gc -Raw .env",
    ],
)
def test_environment_file_read_variants_are_flagged(command: str) -> None:
    assert "dangerous-command.cat-env" in {item.rule_id for item in analyze_command(command)}


@pytest.mark.parametrize("reader", ["cat --", "type", "Get-Content -LiteralPath"])
@pytest.mark.parametrize("suffix", ["example", "sample", "template", "dist"])
def test_environment_templates_are_not_flagged(reader: str, suffix: str) -> None:
    assert analyze_command(f"{reader} ./.env.{suffix}") == []


@pytest.mark.parametrize("command", ["cat README.md", "Get-Content -Raw README.md", "type config.txt"])
def test_ordinary_file_reads_are_not_flagged(command: str) -> None:
    assert analyze_command(command) == []
