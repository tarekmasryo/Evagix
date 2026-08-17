from __future__ import annotations

import re
from pathlib import Path

from evagix.command_analysis import CommandRisk, analyze_command, normalize_command
from evagix.command_recipes import (
    scan_package_script_dangers,
    scan_referenced_script_dangers,
    scan_task_recipe_dangers,
)
from evagix.command_shell import basename as _basename
from evagix.command_shell import executable_index as _executable_index
from evagix.command_shell import tokenize as _tokenize
from evagix.core.io import safe_read_text_result
from evagix.core.paths import repo_relative as _safe_relative
from evagix.evidence import Finding
from evagix.scanner_utils import TraversalDiagnostics, _iter_repo_files, is_sensitive_file_name
from evagix.text_diagnostics import invalid_utf8_finding

TEXT_SUFFIXES = {".md", ".txt", ".toml", ".yml", ".yaml", ".json", ".sh", ".ps1", ".cmd", ".bat"}
MAX_TEXT_FILES = 350
MAX_COMMAND_TEXT_CHARS = 200_000

__all__ = [
    "CommandRisk",
    "DANGEROUS_PATTERNS",
    "MAX_COMMAND_TEXT_CHARS",
    "MAX_TEXT_FILES",
    "TEXT_SUFFIXES",
    "analyze_command",
    "normalize_command",
    "scan_command_values",
    "scan_dangerous_commands",
    "scan_package_script_dangers",
    "scan_referenced_script_dangers",
    "scan_task_recipe_dangers",
]

DANGEROUS_PATTERNS: tuple[tuple[str, str, str], ...] = (
    (
        "dangerous-command.rm-root",
        r"\b(?:sudo\s+)?rm\b[^\r\n]*(?:\s|^)(?:/|~|\.?/?\*?|[\"']?\$(?:\{)?(?:HOME|PWD)(?:\})?[\"']?)(?=\s|$|[;&|`])",
        "Destructive recursive delete can wipe a machine, repository, or home directory.",
    ),
    (
        "dangerous-command.curl-pipe-shell",
        r"\b(?:curl|wget|iwr|irm|invoke-webrequest|invoke-restmethod)\b[^\r\n|;]*\|\s*"
        r"(?:bash|sh|zsh|python|node|pwsh|powershell|cmd|iex|invoke-expression)\b",
        "Piping remote content into an interpreter can execute untrusted code.",
    ),
    (
        "dangerous-command.chmod-777",
        r"\bchmod\s+-R\s+777\b",
        "Recursive world-writable permissions weaken repository and runtime safety.",
    ),
    (
        "dangerous-command.cat-env",
        r"\b(cat|type)\s+\.env(?!\.(?:example|sample|template|dist)\b)(?:\.[A-Za-z0-9_-]+)?\b",
        "Reading local .env files can expose secrets.",
    ),
    (
        "dangerous-command.ssh-key",
        r"\b(cat|type)\s+~?/?\.ssh/(id_rsa|id_ed25519|config)\b",
        "Reading SSH keys or SSH config can expose credentials.",
    ),
    (
        "dangerous-command.print-env",
        r"(?<![\w.])(?:printenv|env)(?![\w.])(?:\s*(?:$|[|;&`]))",
        "Printing full environment variables can expose secrets in logs or agent output.",
    ),
    (
        "dangerous-command.env-exfiltration",
        r"(?<![\w.])(?:env|printenv)(?![\w.])[^\r\n|;]*\|[^\r\n]*(?:curl|wget|nc|netcat)\b",
        "Piping environment data to a network tool can exfiltrate secrets.",
    ),
    (
        "dangerous-command.docker-prune",
        r"\bdocker\s+system\s+prune\b[^\r\n]*(?:-f|--force)",
        "Forcing Docker prune can delete shared local images, caches, and volumes.",
    ),
)


def scan_command_values(
    commands: dict[str, str],
    *,
    sources: dict[str, str] | None = None,
    default_source: str = "detected command",
) -> list[Finding]:
    """Validate concrete commands before they are surfaced to coding agents."""

    findings: list[Finding] = []
    source_map = sources or {}
    for name, command in sorted(commands.items()):
        source = source_map.get(name, default_source)
        for risk in analyze_command(command):
            findings.append(
                Finding(
                    id=risk.rule_id,
                    title="Unsafe generated validation command",
                    category="command_safety",
                    severity=risk.severity,
                    status=risk.status,
                    source=source,
                    source_file=source,
                    evidence=[f"{name}: {command}"[:220]],
                    evidence_files=[source],
                    missing=[],
                    confidence="high",
                    root_cause=f"generated-command:{source}:{name}:{risk.rule_id}",
                    risk=f"The `{name}` command would be published to agent-facing context. {risk.risk}",
                    recommendation=(
                        "Replace the command with a bounded, project-specific validation command before generating context."
                    ),
                    metadata={"command_name": name, "matched_rule": risk.rule_id},
                )
            )
    return findings


def scan_dangerous_commands(root: Path, *, paths: list[Path] | None = None) -> list[Finding]:
    findings: list[Finding] = []
    diagnostics: TraversalDiagnostics | None = None
    if paths is None:
        candidates, diagnostics = _iter_text_files_with_diagnostics(root)
    else:
        candidates = paths
    for path in candidates:
        try:
            read_result = safe_read_text_result(
                path,
                root=root,
                max_chars=MAX_COMMAND_TEXT_CHARS,
            )
        except UnicodeError:
            findings.append(
                invalid_utf8_finding(
                    root,
                    path,
                    scanner="Command safety scan",
                    category="command_safety",
                )
            )
            continue
        except OSError:
            findings.append(_scan_read_error_finding(_safe_relative(root, path)))
            continue
        relative = _safe_relative(root, path)
        if read_result.truncated:
            findings.append(_scan_truncated_finding(relative, MAX_COMMAND_TEXT_CHARS))
        text = read_result.text
        for line_index, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            for command, match_start in _command_candidates_from_line(line):
                risks = analyze_command(command)
                if not risks:
                    continue
                if _is_protective_command_context(line, match_start=match_start):
                    continue
                for risk in risks:
                    if risk.rule_id == "dangerous-command.print-env" and _is_print_env_prose(command):
                        continue
                    findings.append(
                        Finding(
                            id=risk.rule_id,
                            title="Dangerous command detected",
                            category="command_safety",
                            severity=risk.severity,
                            status=risk.status,
                            source=relative,
                            source_file=relative,
                            source_line=line_index,
                            evidence=[line.strip()[:220]],
                            evidence_files=[relative],
                            missing=[],
                            confidence="high",
                            risk=risk.risk,
                            recommendation=(
                                "Remove the command from agent-facing documentation or replace it with a safe, "
                                "project-specific validation command."
                            ),
                        )
                    )
    if diagnostics is not None and diagnostics.incomplete:
        findings.append(_traversal_truncated_finding(diagnostics))
    return findings


def _command_candidates_from_line(line: str) -> list[tuple[str, int]]:
    """Extract executable-looking inline code while preserving prose context."""

    candidates: list[tuple[str, int]] = []
    for match in re.finditer(r"`([^`]+)`", line):
        command = match.group(1).strip()
        if command:
            candidates.append((command, match.start()))
    stripped = line.strip()
    if not candidates and _looks_like_command_line(stripped):
        candidates.append((stripped, max(0, line.find(stripped))))
    return candidates


def _looks_like_command_line(line: str) -> bool:
    if not line:
        return False
    cleaned = re.sub(r"^(?:[-*]\s+|[$>]\s*)", "", line).strip()
    tokens = _tokenize(cleaned)
    executable_index = _executable_index(tokens)
    first = _basename(tokens[executable_index]) if executable_index is not None else ""
    return first in {
        "rm",
        "sudo",
        "curl",
        "wget",
        "iwr",
        "irm",
        "invoke-webrequest",
        "invoke-restmethod",
        "remove-item",
        "del",
        "erase",
        "rmdir",
        "rd",
        "git",
        "find",
        "dd",
        "chmod",
        "docker",
        "env",
        "printenv",
        "cat",
        "type",
        "bash",
        "sh",
        "zsh",
        "python",
        "python3",
        "node",
        "pwsh",
        "powershell",
        "cmd",
        "iex",
        "invoke-expression",
        "mysql",
        "psql",
        "aws",
    }


def _scan_truncated_finding(relative: str, limit: int) -> Finding:
    return Finding(
        id="command-safety.scan-truncated",
        title="Command safety scan was truncated",
        category="command_safety",
        severity="high",
        status="incomplete",
        source=relative,
        source_file=relative,
        evidence=[f"read limit: {limit} characters"],
        risk="Content beyond the read limit was not inspected for dangerous commands.",
        recommendation="Reduce or split the file before relying on the command-safety result.",
        confidence="high",
        root_cause=f"command-safety-truncated:{relative}",
    )


def _scan_read_error_finding(relative: str) -> Finding:
    return Finding(
        id="command-safety.scan-truncated",
        title="Command safety scan was incomplete",
        category="command_safety",
        severity="high",
        status="incomplete",
        source=relative,
        source_file=relative,
        evidence=["file could not be read"],
        risk="The file could not be inspected for dangerous commands.",
        recommendation="Restore read access before relying on the command-safety result.",
        confidence="high",
        root_cause=f"command-safety-read-error:{relative}",
    )


def _traversal_truncated_finding(diagnostics: TraversalDiagnostics) -> Finding:
    return Finding(
        id="command-safety.discovery-truncated",
        title="Command safety discovery was truncated",
        category="command_safety",
        severity="high",
        status="incomplete",
        source="repository text files",
        evidence=[diagnostics.warning("Command safety discovery")],
        risk="Some repository files may not have been inspected for dangerous commands.",
        recommendation="Reduce the scan scope or increase the traversal budget before relying on the result.",
        confidence="high",
        root_cause="command-safety-discovery-truncated",
    )


def _is_protective_command_context(line: str, *, match_start: int) -> bool:
    lower = " ".join(line.lower().split())
    prefix = " ".join(line[: max(0, match_start)].lower().split()).strip(" `:-.;,[]()")
    protective_line_starts = (
        "unsafe example:",
        "bad example:",
        "dangerous example:",
        "security warning:",
        "security note:",
        "for security, avoid",
        "for safety, avoid",
    )
    if lower.startswith(protective_line_starts):
        return True
    protective_prefixes = (
        "do not run",
        "don't run",
        "never run",
        "avoid",
        "avoid running",
        "must not run",
        "should not run",
        "do not execute",
        "don't execute",
        "never execute",
        "avoid executing",
        "do not use",
        "don't use",
        "never use",
        "avoid using",
        "do not pipe",
        "don't pipe",
        "never pipe",
        "avoid piping",
        "do not pipe curl into bash",
        "do not pipe curl into sh",
        "do not pipe wget into bash",
        "do not pipe wget into sh",
        "never pipe curl into bash",
        "never pipe wget into bash",
        "unsafe example",
        "bad example",
        "dangerous example",
        "security warning",
        "security note",
    )
    return any(prefix.endswith(item) for item in protective_prefixes)


def _is_print_env_prose(line: str) -> bool:
    lower = " ".join(line.lower().split())
    if re.search(r"`\s*(?:printenv|env)(?:\s+[^`]*)?\s*`", lower):
        return False
    if re.match(r"^(?:[-*]\s*)?(?:[$>]\s*)?(?:printenv|env)(?:\s|$|[|;&`])", lower):
        return False
    return not re.search(r"\b(?:run|execute|call|use)\s+(?:the\s+)?(?:command\s+)?(?:printenv|env)\b", lower)


def _iter_text_files_with_diagnostics(root: Path) -> tuple[list[Path], TraversalDiagnostics]:
    diagnostics = TraversalDiagnostics()
    files: list[Path] = []
    for path in _iter_repo_files(root, diagnostics=diagnostics):
        if is_sensitive_file_name(path.name):
            continue
        try:
            if path.suffix.lower() in TEXT_SUFFIXES and path.stat().st_size <= 500_000:
                if len(files) >= MAX_TEXT_FILES:
                    diagnostics.result_limit_reached = True
                    break
                files.append(path)
        except OSError:
            diagnostics.read_errors += 1
            continue
    return files, diagnostics


def _iter_text_files(root: Path) -> list[Path]:
    files, _diagnostics = _iter_text_files_with_diagnostics(root)
    return files
