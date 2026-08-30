from __future__ import annotations

import argparse
import json
import subprocess
import sys
from io import BytesIO, StringIO, TextIOWrapper
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from evagix.changes import ChangedFileRisk, ChangedReport
from evagix.cli import main
from evagix.commands import git_cmds
from evagix.commands import inspect as inspect_commands
from evagix.commands.registry import build_parser
from evagix.commands.report_doctor import _print_doctor_text
from evagix.model import RepoFacts
from evagix.report_models import DoctorReport
from evagix.security.redaction import REDACTION_MARKER
from evagix.terminal import TerminalStyle

ANSI_ESCAPE = "\x1b["
SCHEMA_DIR = Path("evagix/schemas")


class TtyStringIO(StringIO):
    def isatty(self) -> bool:
        return True


class TtyTextIOWrapper(TextIOWrapper):
    def isatty(self) -> bool:
        return True


def _make_repo(root: Path) -> None:
    (root / "README.md").write_text("# Demo\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = []\n',
        encoding="utf-8",
    )


def _tty_stdout(monkeypatch: pytest.MonkeyPatch) -> TtyStringIO:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    stream = TtyStringIO()
    monkeypatch.setattr(sys, "stdout", stream)
    return stream


def test_every_subcommand_accepts_no_color_after_the_command() -> None:
    parser = build_parser()
    subparsers_action = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))

    missing = [
        name
        for name, command_parser in subparsers_action.choices.items()
        if "--no-color" not in command_parser._option_string_actions
    ]

    assert missing == []


@pytest.mark.parametrize(
    ("args", "expected_heading"),
    [
        (["scan"], "Evagix Scan"),
        (["doctor"], "Evagix Doctor"),
        (["audit"], "Evagix Audit"),
    ],
)
def test_interactive_tty_enables_human_styling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
    expected_heading: str,
) -> None:
    _make_repo(tmp_path)
    stdout = _tty_stdout(monkeypatch)

    main([args[0], str(tmp_path), *args[1:]])

    output = stdout.getvalue()
    assert ANSI_ESCAPE in output
    assert expected_heading in output


@pytest.mark.parametrize(
    ("command", "expected_heading"),
    [
        ("readme-audit", "README Claim Audit"),
        ("drift", "Evagix Drift Report"),
        ("eval-context", "Evagix Quality Evaluation"),
        ("decide", "Repo Decision Plan"),
    ],
)
def test_readiness_text_commands_use_shared_tty_styling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    expected_heading: str,
) -> None:
    _make_repo(tmp_path)
    stdout = _tty_stdout(monkeypatch)

    main([command, str(tmp_path)])

    output = stdout.getvalue()
    assert ANSI_ESCAPE in output
    assert expected_heading in output


def test_readiness_machine_and_file_outputs_remain_unstyled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_repo(tmp_path)
    stdout = _tty_stdout(monkeypatch)

    assert main(["evidence", str(tmp_path)]) == 0
    evidence = stdout.getvalue()
    assert ANSI_ESCAPE not in evidence
    assert json.loads(evidence)["schema_version"] == "1.0"

    stdout.seek(0)
    stdout.truncate(0)
    assert main(["drift", str(tmp_path), "--format", "markdown", "--output", "drift.md"]) in {0, 1}
    assert ANSI_ESCAPE not in stdout.getvalue()
    assert ANSI_ESCAPE not in (tmp_path / "drift.md").read_text(encoding="utf-8")

    stdout.seek(0)
    stdout.truncate(0)
    assert main(["report", str(tmp_path), "--format", "json", "--output", "report.json"]) == 0
    assert ANSI_ESCAPE not in stdout.getvalue()
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["schema_version"] == "1.0"


def test_changed_text_styles_risk_labels_but_json_stays_plain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = ChangedReport(
        base="main",
        files=[ChangedFileRisk(path="pyproject.toml", risk="HIGH", reason="package metadata")],
        required_gates=["evagix check"],
    )
    monkeypatch.setattr(git_cmds, "_facts", lambda *args, **kwargs: (RepoFacts(root_name="demo"), object()))
    monkeypatch.setattr(git_cmds, "build_changed_report", lambda *args, **kwargs: report)

    assert (
        git_cmds._cmd_changed(
            tmp_path,
            base="main",
            head="HEAD",
            output_format="text",
            style=TerminalStyle(enabled=True),
        )
        == 1
    )
    text_output = capsys.readouterr().out
    assert "\x1b[31mHIGH\x1b[0m" in text_output

    assert (
        git_cmds._cmd_changed(
            tmp_path,
            base="main",
            head="HEAD",
            output_format="json",
            style=TerminalStyle(enabled=True),
        )
        == 1
    )
    json_output = capsys.readouterr().out
    assert ANSI_ESCAPE not in json_output
    assert json.loads(json_output)["has_high_risk"] is True


@pytest.mark.parametrize(
    ("args", "expected_text"),
    [
        (["compile", "--dry-run"], "Planned writes:"),
        (["sync", "--plan"], "Evagix sync plan"),
        (["onboard", "--dry-run"], "Planned onboarding writes:"),
        (["prepare", "--plan"], "Evagix Prepare Plan"),
    ],
)
def test_generation_commands_style_only_the_tty_presentation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
    expected_text: str,
) -> None:
    _make_repo(tmp_path)
    stdout = _tty_stdout(monkeypatch)

    main([args[0], str(tmp_path), *args[1:]])

    output = stdout.getvalue()
    assert ANSI_ESCAPE in output
    assert expected_text in output


def test_subcommand_no_color_and_generated_config_remain_plain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_repo(tmp_path)
    stdout = _tty_stdout(monkeypatch)

    assert main(["prepare", str(tmp_path), "--plan", "--no-color"]) == 0
    assert ANSI_ESCAPE not in stdout.getvalue()

    stdout.seek(0)
    stdout.truncate(0)
    assert main(["init", str(tmp_path)]) == 0
    assert ANSI_ESCAPE in stdout.getvalue()
    assert ANSI_ESCAPE not in (tmp_path / "evagix.toml").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("args", "expected_text"),
    [
        (["suggest"], "Suggested next actions:"),
        (["profiles"], "Available profiles:"),
        (["targets"], "Available targets:"),
        (["policy"], "Evagix Policy"),
        (["classify"], "Evagix Project Classification"),
        (["explain", "missing-ci"], "missing-ci"),
        (["agents"], "Evagix Agent Context Discovery"),
        (["mcp"], "Evagix MCP Config Detection"),
        (["fix", "missing-ci"], "Fix plan for"),
    ],
)
def test_informational_and_fix_commands_use_tty_styling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
    expected_text: str,
) -> None:
    _make_repo(tmp_path)
    stdout = _tty_stdout(monkeypatch)
    command = args[0]
    command_args = (
        [command, *args[1:]] if command in {"profiles", "targets", "explain"} else [command, *args[1:], str(tmp_path)]
    )

    assert main(command_args) in {0, 1}

    output = stdout.getvalue()
    assert ANSI_ESCAPE in output
    assert expected_text in output


@pytest.mark.parametrize("command", ["policy", "classify", "agents", "mcp"])
def test_informational_json_remains_plain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    _make_repo(tmp_path)
    stdout = _tty_stdout(monkeypatch)
    flag = "--json" if command in {"policy", "classify"} else "--format"
    args = [command, str(tmp_path), flag]
    if flag == "--format":
        args.append("json")

    assert main(args) in {0, 1}

    output = stdout.getvalue()
    assert ANSI_ESCAPE not in output
    json.loads(output)


def test_context_pack_stays_unstyled_in_tty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_repo(tmp_path)
    stdout = _tty_stdout(monkeypatch)

    assert main(["context-pack", str(tmp_path)]) == 0

    output = stdout.getvalue()
    assert ANSI_ESCAPE not in output
    assert output.startswith("# Evagix Context Pack")


def test_doctor_human_output_preserves_actual_maturity_level(capsys: pytest.CaptureFixture[str]) -> None:
    report = DoctorReport(score=60, findings=[], maturity_level="limited")

    _print_doctor_text(
        report,
        threshold=0,
        strict=False,
        threshold_failed=False,
        style=TerminalStyle(enabled=True),
    )

    output = capsys.readouterr().out
    assert "Static evidence tier: \x1b[33mlimited\x1b[0m" in output
    assert "Static evidence tier: WARN" not in output


@pytest.mark.parametrize("disable", ["flag", "global-flag", "environment", "ci"])
def test_color_controls_disable_styling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    disable: str,
) -> None:
    _make_repo(tmp_path)
    stdout = _tty_stdout(monkeypatch)
    args = ["scan", str(tmp_path)]
    if disable == "flag":
        args.append("--no-color")
    elif disable == "global-flag":
        args = ["--no-color", *args]
    elif disable == "environment":
        monkeypatch.setenv("NO_COLOR", "1")
    else:
        monkeypatch.setenv("CI", "true")

    assert main(args) == 0

    assert ANSI_ESCAPE not in stdout.getvalue()


def test_non_tty_and_redirected_output_have_no_ansi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_repo(tmp_path)
    redirected_path = tmp_path / "scan.txt"
    with redirected_path.open("w", encoding="utf-8") as stream:
        monkeypatch.setattr(sys, "stdout", stream)
        assert main(["scan", str(tmp_path)]) == 0

    output = redirected_path.read_text(encoding="utf-8")
    assert ANSI_ESCAPE not in output
    assert "Repository: demo" in output


def test_piped_subprocess_output_has_no_ansi(tmp_path: Path) -> None:
    _make_repo(tmp_path)

    completed = subprocess.run(
        [sys.executable, "-m", "evagix", "scan", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert ANSI_ESCAPE not in completed.stdout
    assert "Repository: demo" in completed.stdout


@pytest.mark.parametrize(
    ("command", "schema_name"),
    [
        ("scan", "scan-facts.schema.json"),
        ("doctor", "doctor-report.schema.json"),
        ("audit", "audit-report.schema.json"),
    ],
)
def test_json_output_has_no_ansi_and_preserves_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    schema_name: str,
) -> None:
    _make_repo(tmp_path)
    stdout = _tty_stdout(monkeypatch)

    main([command, str(tmp_path), "--format", "json"])

    output = stdout.getvalue()
    assert ANSI_ESCAPE not in output
    payload = json.loads(output)
    schema = json.loads((SCHEMA_DIR / schema_name).read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(payload)


def test_sarif_and_github_annotations_have_no_ansi_in_tty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_repo(tmp_path)
    stdout = _tty_stdout(monkeypatch)

    main(["doctor", str(tmp_path), "--format", "sarif"])
    sarif_output = stdout.getvalue()
    assert ANSI_ESCAPE not in sarif_output
    sarif = json.loads(sarif_output)
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["tool"]["driver"]["name"] == "evagix"

    stdout.seek(0)
    stdout.truncate(0)
    main(["doctor", str(tmp_path), "--format", "github-annotations"])
    annotations = stdout.getvalue()
    assert ANSI_ESCAPE not in annotations
    assert annotations.startswith("::")


def test_tty_styling_preserves_central_secret_redaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "terminal-output-secret"
    facts = RepoFacts(root_name="demo", warnings=[f"DB_PASSWORD={secret}"])
    monkeypatch.setattr(inspect_commands, "_facts", lambda *args, **kwargs: (facts, object()))
    stdout = _tty_stdout(monkeypatch)

    assert main(["scan", str(tmp_path), "--verbose"]) == 0

    output = stdout.getvalue()
    assert ANSI_ESCAPE in output
    assert secret not in output
    assert REDACTION_MARKER in output


def test_tty_styling_remains_cp1252_safe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    facts = RepoFacts(root_name="demo-🙂")
    monkeypatch.setattr(inspect_commands, "_facts", lambda *args, **kwargs: (facts, object()))
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    raw = BytesIO()
    stream = TtyTextIOWrapper(raw, encoding="cp1252", newline="")
    monkeypatch.setattr(sys, "stdout", stream)

    assert main(["scan", str(tmp_path)]) == 0

    output = raw.getvalue().decode("cp1252")
    assert ANSI_ESCAPE in output
    assert r"\U0001f642" in output


@pytest.mark.parametrize(
    ("args", "expected_exit_code"),
    [
        (["scan"], 0),
        (["doctor", "--fail-under", "100"], 1),
        (["audit"], 1),
    ],
)
def test_styling_preserves_command_exit_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
    expected_exit_code: int,
) -> None:
    _make_repo(tmp_path)
    stdout = _tty_stdout(monkeypatch)

    exit_code = main([args[0], str(tmp_path), *args[1:]])

    assert exit_code == expected_exit_code
    assert ANSI_ESCAPE in stdout.getvalue()
