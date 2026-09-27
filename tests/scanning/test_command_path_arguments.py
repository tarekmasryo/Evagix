from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path

import pytest

from evagix.cli import main
from evagix.command_analysis import analyze_command
from evagix.commands.generation_safety import unsafe_generated_command_findings
from evagix.scanner import scan_repo


@pytest.fixture(autouse=True)
def forbid_command_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Repository-derived commands must never execute")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "system", forbidden)


def _write_manifest(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "services:\n  db:\n    image: postgres:16\n" if path.suffix == ".yml" else "pytest\nruff\n"
    path.write_text(content, encoding="utf-8")
    (root / "evagix.toml").write_text(
        "[targets]\nagents=true\nuniversal_md=true\nuniversal_json=true\n", encoding="utf-8"
    )


@pytest.mark.parametrize(
    ("relative", "name", "expected"),
    [
        ("compose.yml", "run", "docker compose -f compose.yml up --build"),
        ("services/api/compose.yml", "run", "docker compose -f services/api/compose.yml up --build"),
        ("services/my api/compose.yml", "run", 'docker compose -f "services/my api/compose.yml" up --build'),
        (
            "services/api's config/compose.yml",
            "run",
            'docker compose -f "services/api\'s config/compose.yml" up --build',
        ),
        ("requirements.txt", "install", "python -m pip install -r requirements.txt"),
        ("requirements dev.txt", "install", 'python -m pip install -r "requirements dev.txt"'),
    ],
)
def test_repository_paths_remain_single_literal_arguments_through_publication(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], relative: str, name: str, expected: str
) -> None:
    _write_manifest(tmp_path, relative)
    facts = scan_repo(tmp_path)
    command = facts.commands[name]
    assert command == expected
    tokens = shlex.split(command)
    assert tokens[tokens.index("-f" if name == "run" else "-r") + 1] == relative
    assert analyze_command(command) == []
    assert unsafe_generated_command_findings(tmp_path, facts) == []
    if name == "run":
        assert "docker-compose" in facts.container_platforms
        assert "postgres" in facts.databases
        assert relative in facts.config_files
    else:
        assert "python" in facts.languages
        assert "pip" in facts.package_managers
        assert "pytest" in facts.dev_tools

    assert main(["scan", str(tmp_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["commands"][name] == expected
    assert main(["compile", str(tmp_path)]) == 0
    payload = json.loads((tmp_path / ".evagix/context.json").read_text(encoding="utf-8"))
    assert payload["commands"][name] == expected
    assert expected in (tmp_path / ".evagix/context.md").read_text(encoding="utf-8")
    assert expected in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert main(["check", str(tmp_path)]) == 0


@pytest.mark.parametrize("verb", ["scan", "compile"])
@pytest.mark.parametrize(
    "relative",
    [
        "services/a;echo OWNED/compose.yml",
        "requirements;echo OWNED.txt",
        "services/api&echo OWNED/compose.yml",
        "requirements&echo OWNED.txt",
        "services/$PATH/compose.yml",
        "requirements$PATH.txt",
        "services/%PATH%/compose.yml",
        "requirements%PATH%.txt",
        "services/!PATH!/compose.yml",
        "requirements!PATH!.txt",
        "services/`echo OWNED`/compose.yml",
        "requirements`echo OWNED`.txt",
    ],
)
def test_unsupported_repository_path_is_diagnosed_before_command_publication(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], verb: str, relative: str
) -> None:
    _write_manifest(tmp_path, relative)
    before = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}

    args = [verb, str(tmp_path)] + (["--json"] if verb == "scan" else [])
    assert main(args) == 1
    captured = capsys.readouterr()
    assert "ERROR:" in captured.err
    assert "Unsupported command path" in captured.err
    assert relative in captured.err
    assert "shell-specific escaping" in captured.err
    assert "Traceback" not in captured.err
    assert not captured.out
    assert {path.relative_to(tmp_path) for path in tmp_path.rglob("*")} == before
