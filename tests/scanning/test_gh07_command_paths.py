from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from evagix.cli import main
from evagix.command_analysis import analyze_command
from evagix.commands.generation_safety import unsafe_generated_command_findings
from evagix.ecosystems.commands import command_supported_by_ecosystem
from evagix.ecosystems.core import detect_ecosystems
from evagix.ecosystems.utils import _scope, _strip_cd
from evagix.model import RepoFacts
from evagix.safety import EvagixSafetyError
from evagix.scanner import scan_repo
from evagix.scanning.command_evidence import _scan_node_package


def _assert_scoped_command(command: str, relative: str, payload: str) -> None:
    if relative == ".":
        assert command == payload
    else:
        prefix, separator, rest = command.partition(" && ")
        assert separator
        assert shlex.split(prefix, posix=True) == ["cd", relative]
        assert rest == payload
        if " " in relative or "'" in relative:
            assert prefix == f'cd "{relative}"'
    assert _strip_cd(command) == payload


@pytest.mark.parametrize("relative", [".", "web", "web client", "packages/web client", "web  client", "web's client"])
def test_scope_preserves_a_directory_as_one_posix_argument(relative: str) -> None:
    command = _scope(relative, "python -m pytest")

    _assert_scoped_command(command, relative, "python -m pytest")
    assert analyze_command(command) == []
    if relative == "web":
        assert command == "cd web && python -m pytest"


@pytest.mark.parametrize("producer", ["scanner", "ecosystem"])
@pytest.mark.parametrize("relative", [".", "web", "web client", "packages/web client"])
@pytest.mark.parametrize(
    ("manager", "test_command", "install_command"),
    [
        ("npm", "npm run test", "npm install"),
        ("pnpm", "pnpm test", "pnpm install"),
        ("yarn", "yarn test", "yarn install"),
        ("bun", "bun run test", "bun install"),
    ],
)
def test_node_prefix_producers_preserve_directory_and_package_manager(
    tmp_path: Path, producer: str, relative: str, manager: str, test_command: str, install_command: str
) -> None:
    package = tmp_path / relative
    package.mkdir(parents=True, exist_ok=True)
    manifest = package / "package.json"
    manifest.write_text(
        json.dumps(
            {
                "packageManager": f"{manager}@1.0.0",
                "dependencies": {"react": "*"},
                "scripts": {"test": "node --version"},
            }
        ),
        encoding="utf-8",
    )

    if producer == "scanner":
        facts = RepoFacts(root_name="demo")
        _scan_node_package(tmp_path, manifest, facts)
        commands = facts.subprojects[0].commands
        assert facts.subprojects[0].package_manager == manager
        assert set(commands.values()) <= set(facts.commands.values())
    else:
        detection = detect_ecosystems(tmp_path)[0]
        commands = detection.commands
        assert detection.path == relative
        assert detection.package_manager == manager

    _assert_scoped_command(commands["test"], relative, test_command)
    _assert_scoped_command(commands["install"], relative, install_command)
    assert analyze_command(commands["test"]) == []
    if relative == "web":
        assert commands["test"] == f"cd web && {test_command}"


@pytest.mark.parametrize("relative", ["web", "web client"])
@pytest.mark.parametrize("dangerous", [False, True])
def test_scoped_commands_preserve_local_script_safety_and_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: str, dangerous: bool
) -> None:
    package = tmp_path / relative
    package.mkdir()
    (package / "package.json").write_text(json.dumps({"scripts": {"test": "sh check.sh"}}), encoding="utf-8")
    (package / "check.sh").write_text("rm -rf .\n" if dangerous else "echo safe\n", encoding="utf-8")
    (tmp_path / "check.sh").write_text("echo wrong_directory\n" if dangerous else "rm -rf .\n", encoding="utf-8")
    (tmp_path / "evagix.toml").write_text("[targets]\nagents=true\n", encoding="utf-8")

    def forbid_execution(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Discovered project commands must never execute")

    monkeypatch.setattr(subprocess, "run", forbid_execution)
    monkeypatch.setattr(subprocess, "Popen", forbid_execution)
    monkeypatch.setattr(os, "system", forbid_execution)
    facts = scan_repo(tmp_path)
    command = facts.commands[f"{relative}_test"]
    _assert_scoped_command(command, relative, "npm run test")
    facts.commands.clear()
    assert command_supported_by_ecosystem(command, facts)[0]
    assert command_supported_by_ecosystem("npm run test", facts)[0]
    facts = scan_repo(tmp_path)
    findings = unsafe_generated_command_findings(tmp_path, facts)

    if dangerous:
        assert any(
            item.id == "dangerous-command.local-script"
            and item.source_file == f"{relative}/check.sh"
            and item.metadata["matched_rule"] == "dangerous-command.rm-root"
            for item in findings
        )
        assert main(["compile", str(tmp_path)]) == 1
        assert not (tmp_path / "AGENTS.md").exists()
        assert not (tmp_path / ".evagix" / "context.md").exists()
    else:
        assert findings == []
        assert main(["compile", str(tmp_path)]) == 0
        assert command in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("payload", "rule", "status"),
    [
        ("echo ready\nrm -rf .", "command-safety.scan-truncated", "incomplete"),
        ('bash -lc "rm -rf ."', "dangerous-command.rm-root", "unsafe"),
        ("sudo -n rm -rf .", "dangerous-command.rm-root", "unsafe"),
    ],
)
def test_quoted_scope_keeps_gh02_rejection(payload: str, rule: str, status: str) -> None:
    command = _scope("web client", payload)
    _assert_scoped_command(command, "web client", payload)
    assert (rule, status) in [(risk.rule_id, risk.status) for risk in analyze_command(command)]


@pytest.mark.parametrize("wrapper", ["cmd /c", "powershell -Command"])
def test_quoted_scope_does_not_imply_other_shell_dialects_are_supported(wrapper: str) -> None:
    command = _scope("web client", "npm run test")
    _assert_scoped_command(command, "web client", "npm run test")
    findings = analyze_command(f'{wrapper} "{command}"')
    assert any(item.rule_id == "command-safety.scan-truncated" and item.status == "incomplete" for item in findings)


@pytest.mark.parametrize("relative", ["web", "web client", "packages/web client", "web  client", "web's client"])
@pytest.mark.parametrize("shell_kind", ["cmd", "posix"])
def test_scope_uses_compatible_directory_quoting_in_real_shells(tmp_path: Path, relative: str, shell_kind: str) -> None:
    (tmp_path / relative).mkdir(parents=True)
    # Exercise only synthetic cd/pwd builtins, never a discovered project command.
    if shell_kind == "cmd":
        if os.name != "nt":
            pytest.skip("CMD is available only on Windows")
        shell = os.environ["COMSPEC"]
        command = _scope(relative, "cd")
        invocation: str | list[str] = f'"{shell}" /d /s /c "{command}"'
    else:
        shell = shutil.which("sh") or shutil.which("bash") or ""
        if not shell:
            pytest.skip("No POSIX shell available")
        invocation = [shell, "-c", _scope(relative, "pwd -P")]
    result = subprocess.run(invocation, cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().replace("\\", "/").endswith(f"/{tmp_path.name}/{relative}")


@pytest.mark.parametrize(
    "relative",
    ['web "client"', "web $HOME", "web %CD%", "web !CD!", "web `client`", "web;client", "web && client", "web\nclient"],
)
def test_scope_rejects_paths_requiring_shell_specific_escaping(relative: str) -> None:
    with pytest.raises(EvagixSafetyError, match="command directory"):
        _scope(relative, "npm run test")


@pytest.mark.parametrize("verb", ["scan", "compile"])
@pytest.mark.parametrize("manifest", ["package.json", "go.mod"])
def test_unsupported_command_directory_fails_cleanly_before_publication(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], verb: str, manifest: str
) -> None:
    package = tmp_path / "web $GH07_DIR"
    package.mkdir()
    content = (
        json.dumps({"scripts": {"test": "node --version"}})
        if manifest == "package.json"
        else "module example.org/demo\n\ngo 1.21\n"
    )
    (package / manifest).write_text(content, encoding="utf-8")
    (tmp_path / "evagix.toml").write_text("[targets]\nagents=true\n", encoding="utf-8")

    assert main([verb, str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert "ERROR:" in captured.err
    assert "command directory" in captured.err
    assert "web $GH07_DIR" in captured.err
    assert "Traceback" not in captured.err
    assert not captured.out
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / ".evagix" / "context.md").exists()
