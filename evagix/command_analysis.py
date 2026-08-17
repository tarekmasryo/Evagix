from __future__ import annotations

import re
from dataclasses import dataclass

from evagix.command_shell import (
    basename as _basename,
)
from evagix.command_shell import (
    contains_executable as _contains_executable,
)
from evagix.command_shell import (
    executable_index as _executable_index,
)
from evagix.command_shell import (
    flags_and_targets as _flags_and_targets,
)
from evagix.command_shell import (
    has_encoded_powershell,
    normalize_command,
    prints_environment,
    wrapper_payload,
)
from evagix.command_shell import (
    is_dangerous_target as _target_is_dangerous,
)
from evagix.command_shell import (
    split_pipeline as _split_pipeline,
)
from evagix.command_shell import (
    split_shell_segments as _split_shell_segments,
)
from evagix.command_shell import (
    tokenize as _tokenize,
)
from evagix.security.labels import is_secret_label
from evagix.security.redaction import REDACTION_MARKER


@dataclass(frozen=True)
class CommandRisk:
    rule_id: str
    risk: str
    severity: str = "high"
    status: str = "unsafe"


_DOWNLOADER_NAMES = {
    "curl",
    "wget",
    "iwr",
    "irm",
    "invoke-webrequest",
    "invoke-restmethod",
}
_INTERPRETER_NAMES = {
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
}
_DANGEROUS_TARGETS = {
    "/",
    "~",
    ".",
    "./",
    "*",
    "./*",
    "$home",
    "${home}",
    "$pwd",
    "${pwd}",
    "$env:userprofile",
    "$env:homedrive\\",
    "%userprofile%",
}


def analyze_command(command: str) -> list[CommandRisk]:
    """Return conservative risks for one concrete command value."""

    return _analyze_command(command, depth=0)


def _analyze_command(command: str, *, depth: int) -> list[CommandRisk]:
    normalized = normalize_command(command)
    if not normalized or depth > 3:
        return []
    risks: list[CommandRisk] = []
    risks.extend(_remote_execution_risks(normalized))
    risks.extend(_environment_pipeline_risks(normalized))
    risks.extend(_embedded_credential_risks(normalized))
    for segment in _split_shell_segments(normalized):
        tokens = _tokenize(segment)
        if not tokens:
            continue
        if has_encoded_powershell(tokens):
            risks.append(
                CommandRisk(
                    "dangerous-command.obfuscated-execution",
                    "Encoded PowerShell execution is opaque and cannot be safely published to agent context.",
                )
            )
        payload = wrapper_payload(tokens)
        if payload:
            risks.extend(_analyze_command(payload, depth=depth + 1))
        risks.extend(_destructive_command_risks(tokens, segment))
        risks.extend(_environment_risks(tokens, segment))
    return _dedupe_risks(risks)


def _remote_execution_risks(command: str) -> list[CommandRisk]:
    lower = command.casefold()
    risks: list[CommandRisk] = []
    segments = _split_pipeline(command)
    for left, right in zip(segments, segments[1:], strict=False):
        left_tokens = _tokenize(left)
        right_tokens = _tokenize(right)
        if _contains_executable(left_tokens, _DOWNLOADER_NAMES) and _contains_executable(
            right_tokens, _INTERPRETER_NAMES
        ):
            risks.append(
                CommandRisk(
                    "dangerous-command.curl-pipe-shell",
                    "Piping remote content into an interpreter can execute untrusted code.",
                )
            )
    if re.search(
        r"\b(?:iex|invoke-expression)\b[^\r\n]*(?:downloadstring|iwr\b|irm\b|invoke-webrequest|invoke-restmethod)",
        lower,
    ):
        risks.append(
            CommandRisk(
                "dangerous-command.curl-pipe-shell",
                "Executing remotely downloaded PowerShell content can run untrusted code.",
            )
        )
    if re.search(
        r"\b(?:bash|sh|zsh|python|python3|node|pwsh|powershell|cmd)\b[^\r\n]*(?:\$\(|`)[^\r\n]*(?:curl|wget|iwr|irm)\b",
        lower,
    ) or re.search(
        r"(?:\$\(|`)[^\r\n]*(?:curl|wget|iwr|irm)\b[^\r\n]*(?:\)|`)",
        lower,
    ):
        risks.append(
            CommandRisk(
                "dangerous-command.curl-pipe-shell",
                "Executing command-substituted remote content can run untrusted code.",
            )
        )
    return risks


def _environment_pipeline_risks(command: str) -> list[CommandRisk]:
    lower = command.casefold()
    if re.search(r"(?<![\w.])(?:env|printenv)(?![\w.])[^\r\n|;]*\|[^\r\n]*(?:curl|wget|nc|netcat)\b", lower):
        return [
            CommandRisk(
                "dangerous-command.env-exfiltration",
                "Piping environment data to a network tool can exfiltrate secrets.",
            )
        ]
    return []


def _embedded_credential_risks(command: str) -> list[CommandRisk]:
    if _literal_secret_flag(command) is None and _literal_secret_assignment(command) is None:
        return []
    return [
        CommandRisk(
            "dangerous-command.embedded-credential",
            "Literal credentials in command arguments can leak into generated context, logs, and shell history.",
        )
    ]


def _destructive_command_risks(tokens: list[str], segment: str) -> list[CommandRisk]:
    executable_index = _executable_index(tokens)
    if executable_index is None:
        return []
    executable = _basename(tokens[executable_index])
    args = tokens[executable_index + 1 :]
    lower_args = [item.casefold() for item in args]

    if executable == "rm":
        flags, targets = _flags_and_targets(args)
        recursive = "r" in flags or "R" in flags or "recursive" in flags or "recurse" in flags
        force = "f" in flags or "force" in flags
        if recursive and force and any(_is_dangerous_target(target) for target in targets):
            return [
                CommandRisk(
                    "dangerous-command.rm-root", "Destructive recursive delete can wipe a machine or repository."
                )
            ]

    if executable in {"remove-item", "ri"}:
        flags, targets = _flags_and_targets(args)
        if {"recurse", "force"}.issubset({flag.casefold() for flag in flags}) and any(
            _is_dangerous_target(target) for target in targets
        ):
            return [
                CommandRisk(
                    "dangerous-command.rm-root", "Recursive PowerShell deletion targets a broad filesystem scope."
                )
            ]

    if executable in {"del", "erase"}:
        flags, targets = _flags_and_targets(args, slash_flags=True)
        if "s" in flags and any(_is_dangerous_target(target) for target in targets):
            return [
                CommandRisk("dangerous-command.rm-root", "Recursive CMD deletion targets a broad filesystem scope.")
            ]

    if executable in {"rmdir", "rd"}:
        flags, targets = _flags_and_targets(args, slash_flags=True)
        if "s" in flags and any(_is_dangerous_target(target) for target in targets):
            return [
                CommandRisk(
                    "dangerous-command.rm-root", "Recursive directory removal targets a broad filesystem scope."
                )
            ]

    if executable == "git" and lower_args and lower_args[0] == "clean":
        flags, _targets = _flags_and_targets(args[1:])
        if "f" in flags and "d" in flags:
            return [
                CommandRisk("dangerous-command.rm-root", "Forced git clean can delete untracked files and directories.")
            ]

    if executable == "find" and "-delete" in lower_args and any(_is_dangerous_target(item) for item in args[:1]):
        return [CommandRisk("dangerous-command.rm-root", "Recursive find deletion can wipe a broad filesystem scope.")]

    if executable == "dd" and re.search(r"\bof=/dev/(?:sd|hd|nvme|vd)", segment, re.IGNORECASE):
        return [CommandRisk("dangerous-command.rm-root", "Raw disk writes can destroy filesystems and data.")]

    if executable.startswith("mkfs") and any(re.match(r"/dev/(?:sd|hd|nvme|vd)", item, re.IGNORECASE) for item in args):
        return [CommandRisk("dangerous-command.rm-root", "Formatting a block device destroys its filesystem.")]

    if executable == "chmod" and "777" in args and any(item in {"-R", "--recursive"} for item in args):
        return [CommandRisk("dangerous-command.chmod-777", "Recursive world-writable permissions weaken safety.")]

    if executable == "docker" and lower_args[:2] == ["system", "prune"]:
        flags, _targets = _flags_and_targets(args[2:])
        if "f" in flags or "force" in flags:
            return [CommandRisk("dangerous-command.docker-prune", "Forced Docker prune can delete shared local state.")]
    return []


def _environment_risks(tokens: list[str], segment: str) -> list[CommandRisk]:
    if prints_environment(tokens):
        return [CommandRisk("dangerous-command.print-env", "Printing the full environment can expose secrets.")]
    executable_index = _executable_index(tokens)
    if executable_index is None:
        return []
    executable = _basename(tokens[executable_index])
    args = tokens[executable_index + 1 :]
    lower = segment.casefold()
    if executable in {"cat", "type"} and args:
        candidate = args[0].casefold()
        if re.fullmatch(r"\.env(?:\.[a-z0-9_-]+)?", candidate) and not re.search(
            r"\.(?:example|sample|template|dist)$", candidate
        ):
            return [CommandRisk("dangerous-command.cat-env", "Reading local .env files can expose secrets.")]
        if re.search(r"(?:^|/)\.ssh/(?:id_rsa|id_ed25519|config)$", candidate):
            return [CommandRisk("dangerous-command.ssh-key", "Reading SSH keys or config can expose credentials.")]
    if executable == "printenv":
        if re.search(r"\|[^\r\n]*(?:curl|wget|nc|netcat)\b", lower):
            return [CommandRisk("dangerous-command.env-exfiltration", "Environment data is piped to a network tool.")]
        return [CommandRisk("dangerous-command.print-env", "Printing the full environment can expose secrets.")]
    return []


def _literal_secret_flag(command: str) -> str | None:
    long_flag = re.search(
        r"(?<![\w-])--(?P<name>password|passwd|pwd|token|api-key|apikey|client-secret|access-token|auth-token|secret|secret-key)"
        r"(?:\s*=\s*|\s+)(?P<quote>[\"']?)(?P<value>[^\s\"']+)(?P=quote)",
        command,
        re.IGNORECASE,
    )
    if long_flag and _is_literal_secret(long_flag.group("value")):
        return long_flag.group("name")
    docker_short = re.search(
        r"\bdocker\s+login\b[^\r\n]*(?:^|\s)-p(?:\s+|=)(?P<value>[^\s]+)",
        command,
        re.IGNORECASE,
    )
    if docker_short and _is_literal_secret(docker_short.group("value")):
        return "docker-password"
    mysql_short = re.search(
        r"\bmysql\b[^\r\n]*(?:^|\s)-p(?P<value>[^=\s-][^\s]*)",
        command,
        re.IGNORECASE,
    )
    if mysql_short and _is_literal_secret(mysql_short.group("value")):
        return "mysql-password"
    mysql_separated = re.search(
        r"\bmysql\b[^\r\n]*(?:^|\s)-p(?:\s+|=)(?P<value>(?!-)[^\s]+)",
        command,
        re.IGNORECASE,
    )
    if mysql_separated and _is_literal_secret(mysql_separated.group("value")):
        return "mysql-password"
    aws_secret = re.search(
        r"\baws\s+configure\s+set\s+(?:aws_secret_access_key|aws_session_token)\s+(?P<value>[^\s]+)",
        command,
        re.IGNORECASE,
    )
    if aws_secret and _is_literal_secret(aws_secret.group("value")):
        return "aws-secret"
    return None


def _literal_secret_assignment(command: str) -> str | None:
    """Return the first credential-bearing environment assignment with a literal value."""

    tokens = _tokenize(command)
    for index, token in enumerate(tokens):
        assignment = _split_assignment_token(token)
        if assignment is not None:
            label, value = assignment
            if is_secret_label(label) and _is_literal_secret(value):
                return label

        if token.casefold().startswith("$env:") and index + 2 < len(tokens) and tokens[index + 1] == "=":
            label = token[5:]
            value = tokens[index + 2]
            if is_secret_label(label) and _is_literal_secret(value):
                return label

        executable = _basename(token)
        if executable == "setx" and index + 2 < len(tokens):
            label = tokens[index + 1]
            value = tokens[index + 2]
            if is_secret_label(label) and _is_literal_secret(value):
                return label
    return None


def _split_assignment_token(token: str) -> tuple[str, str] | None:
    candidate = token.strip().strip("\"'")
    if "=" not in candidate:
        return None
    label, value = candidate.split("=", 1)
    if label.casefold().startswith("$env:"):
        label = label[5:]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", label):
        return None
    return label, value


def _is_literal_secret(value: str) -> bool:
    cleaned = value.strip().strip("\"'")
    if not cleaned or cleaned == REDACTION_MARKER:
        return False
    if cleaned.startswith(("$(", "`", "${{", "{{")):
        return False
    return not bool(
        re.fullmatch(
            r"(?:\$[A-Za-z_][A-Za-z0-9_]*|\$\{[^}]+\}|\$env:[A-Za-z_][A-Za-z0-9_]*|"
            r"%[A-Za-z_][A-Za-z0-9_]*%|\$\([^)]*\)|`[^`]*`|\$\{\{.*?\}\}|\{\{.*?\}\})",
            cleaned,
            re.IGNORECASE,
        )
    )


def _is_dangerous_target(target: str) -> bool:
    return _target_is_dangerous(target, _DANGEROUS_TARGETS)


def _dedupe_risks(risks: list[CommandRisk]) -> list[CommandRisk]:
    by_id: dict[str, CommandRisk] = {}
    for risk in risks:
        by_id.setdefault(risk.rule_id, risk)
    return [by_id[key] for key in sorted(by_id)]
