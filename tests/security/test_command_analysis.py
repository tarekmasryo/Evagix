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
