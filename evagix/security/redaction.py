from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from evagix.security.assignment_patterns import (
    CMD_SET_ASSIGNMENT,
    ENVIRONMENT_SETTER,
    QUOTED_ASSIGNMENT,
    SHELL_ENVIRONMENT_ASSIGNMENT,
    YAML_SECRET_BLOCK_HEADER,
    unquoted_assignment_pattern,
)
from evagix.security.labels import is_secret_label

REDACTION_MARKER: Final = "[REDACTED]"
Replacement = str | Callable[[re.Match[str]], str]


@dataclass(frozen=True)
class RedactionRule:
    """One deterministic text-redaction rule applied in declaration order."""

    name: str
    pattern: re.Pattern[str]
    replacement: Replacement


def _redact_yaml_secret_blocks(value: str) -> str:
    """Redact complete YAML secret block scalars, including internal blank lines."""

    lines = value.splitlines(keepends=True)
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        line_body = line.rstrip("\r\n")
        match = YAML_SECRET_BLOCK_HEADER.match(line_body)
        if match is None:
            output.append(line)
            index += 1
            continue

        base_indent = len(match.group("indent"))
        cursor = index + 1
        first_content_indent = ""
        has_content = False
        while cursor < len(lines):
            candidate = lines[cursor]
            candidate_body = candidate.rstrip("\r\n")
            if not candidate_body.strip():
                cursor += 1
                continue
            indent_match = re.match(r"[ \t]*", candidate_body)
            indentation = indent_match.group(0) if indent_match else ""
            if len(indentation) <= base_indent:
                break
            if not first_content_indent:
                first_content_indent = indentation
            has_content = True
            cursor += 1

        if not has_content:
            output.append(line)
            index += 1
            continue

        newline = "\r\n" if line.endswith("\r\n") else "\n"
        output.append(line)
        output.append(f"{first_content_indent}{REDACTION_MARKER}{newline}")
        index = cursor
    return "".join(output)


def _is_docker_auth_value(value: str) -> bool:
    """Return whether a string is Docker's base64-encoded ``user:password`` form."""

    padded = value + "=" * (-len(value) % 4)
    try:
        decoded = base64.b64decode(padded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    return ":" in decoded


def _redact_docker_auth(match: re.Match[str]) -> str:
    """Redact Docker config auth only when the value decodes to user:password."""

    if not _is_docker_auth_value(match.group("value")):
        return match.group(0)
    return f"{match.group('prefix')}{match.group('quote')}{REDACTION_MARKER}{match.group('quote')}"


def _redact_credential_url(match: re.Match[str]) -> str:
    return f"{match.group('prefix')}{REDACTION_MARKER}{match.group('suffix')}"


def _redact_curl_user(match: re.Match[str]) -> str:
    quote = match.group("quote") or ""
    return f"{match.group('prefix')}{quote}{match.group('user')}:{REDACTION_MARKER}{quote}"


def _redact_unquoted_assignment(match: re.Match[str]) -> str:
    value = match.group("value")
    normalized = value.strip()
    if normalized.startswith(REDACTION_MARKER) or re.fullmatch(r"[|>][+-]?", normalized):
        return match.group(0)
    trailing = value[len(value.rstrip()) :]
    return f"{match.group('prefix')}{REDACTION_MARKER}{trailing}"


def _redact_cli_secret_flag(match: re.Match[str]) -> str:
    quote = match.group("quote") or ""
    return f"{match.group('prefix')}{quote}{REDACTION_MARKER}{quote}"


def _redact_shell_environment_assignment(match: re.Match[str]) -> str:
    quote = match.group("quote") or ""
    return f"{match.group('prefix')}{quote}{REDACTION_MARKER}{quote}{match.group('suffix')}"


def _redact_cmd_set_assignment(match: re.Match[str]) -> str:
    return f"{match.group('prefix')}{REDACTION_MARKER}{match.group('suffix')}"


def _redact_mysql_short_password(match: re.Match[str]) -> str:
    separator = match.group("separator") or ""
    return f"{match.group('prefix')}{separator}{REDACTION_MARKER}"


_RULES: Final[tuple[RedactionRule, ...]] = (
    RedactionRule(
        "private-key",
        re.compile(
            r"-----BEGIN [^-\r\n]*PRIVATE KEY-----[\s\S]*?-----END [^-\r\n]*PRIVATE KEY-----",
            re.IGNORECASE,
        ),
        "-----BEGIN PRIVATE KEY-----\n[REDACTED]\n-----END PRIVATE KEY-----",
    ),
    RedactionRule(
        "credential-url",
        re.compile(
            r"\b(?P<prefix>[a-z][a-z0-9+.-]*://[^\s/@:]*:)(?P<password>[^\s/@]+)(?P<suffix>@)",
            re.IGNORECASE,
        ),
        _redact_credential_url,
    ),
    RedactionRule(
        "curl-user",
        re.compile(
            r"(?P<prefix>\bcurl\b[^\r\n]*?(?:--user|-u)\s+)(?P<quote>[\"']?)"
            r"(?P<user>[^:\s\"']+):(?P<password>[^\s\"']+)(?P=quote)",
            re.IGNORECASE,
        ),
        _redact_curl_user,
    ),
    RedactionRule(
        "cli-secret-flag",
        re.compile(
            r"(?P<prefix>(?<![\w-])--(?:password|passwd|pwd|token|api-key|apikey|client-secret|"
            r"access-token|auth-token|secret|secret-key)(?:\s*=\s*|\s+))"
            r"(?P<quote>[\"']?)(?P<value>[^\s\"']+)(?P=quote)",
            re.IGNORECASE,
        ),
        _redact_cli_secret_flag,
    ),
    RedactionRule(
        "docker-login-password",
        re.compile(
            r"(?P<prefix>\bdocker\s+login\b[^\r\n]*?\s-p(?:\s+|=))"
            r"(?P<quote>[\"']?)(?P<value>[^\s\"']+)(?P=quote)",
            re.IGNORECASE,
        ),
        _redact_cli_secret_flag,
    ),
    RedactionRule(
        "mysql-short-password-attached",
        re.compile(
            r"(?P<prefix>\bmysql\b[^\r\n]*?\s-p)(?P<separator>)"
            r"(?P<value>[^=\s-][^\s]*)",
            re.IGNORECASE,
        ),
        _redact_mysql_short_password,
    ),
    RedactionRule(
        "mysql-short-password-separated",
        re.compile(
            r"(?P<prefix>\bmysql\b[^\r\n]*?\s-p)(?P<separator>\s+|=)"
            r"(?P<value>(?!-)[^\s]+)",
            re.IGNORECASE,
        ),
        _redact_mysql_short_password,
    ),
    RedactionRule(
        "aws-configure-secret",
        re.compile(
            r"(?P<prefix>\baws\s+configure\s+set\s+"
            r"(?:aws_secret_access_key|aws_session_token)\s+)"
            r"(?P<quote>[\"']?)(?P<value>[^\s\"']+)(?P=quote)",
            re.IGNORECASE,
        ),
        _redact_cli_secret_flag,
    ),
    RedactionRule(
        "npmrc-auth-token",
        re.compile(
            r"(?P<prefix>(?://[^\s=]+/:)?_authToken\s*=\s*)"
            r"(?P<quote>[\"']?)(?P<value>[^\s\"']+)(?P=quote)",
            re.IGNORECASE,
        ),
        _redact_cli_secret_flag,
    ),
    RedactionRule(
        "shell-environment-assignment",
        SHELL_ENVIRONMENT_ASSIGNMENT,
        _redact_shell_environment_assignment,
    ),
    RedactionRule(
        "cmd-set-assignment",
        CMD_SET_ASSIGNMENT,
        _redact_cmd_set_assignment,
    ),
    RedactionRule(
        "environment-setter",
        ENVIRONMENT_SETTER,
        _redact_cli_secret_flag,
    ),
    RedactionRule(
        "authorization",
        re.compile(r"\b((?:authorization\s*:\s*)?(?:bearer|basic|token)\s+)[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
        rf"\1{REDACTION_MARKER}",
    ),
    RedactionRule(
        "docker-auth",
        re.compile(
            r"(?P<prefix>[\"']?auth[\"']?\s*:\s*)(?P<quote>[\"'])(?P<value>[A-Za-z0-9+/]{8,}={0,2})(?P=quote)",
            re.IGNORECASE,
        ),
        _redact_docker_auth,
    ),
    RedactionRule(
        "github-token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
        REDACTION_MARKER,
    ),
    RedactionRule(
        "gitlab-token",
        re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
        REDACTION_MARKER,
    ),
    RedactionRule(
        "aws-access-key",
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        REDACTION_MARKER,
    ),
    RedactionRule(
        "google-api-key",
        re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
        REDACTION_MARKER,
    ),
    RedactionRule(
        "slack-token",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
        REDACTION_MARKER,
    ),
    RedactionRule(
        "package-registry-token",
        re.compile(r"\b(?:npm_[A-Za-z0-9]{20,}|pypi-[A-Za-z0-9_-]{20,})\b"),
        REDACTION_MARKER,
    ),
    RedactionRule(
        "service-api-key",
        re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b"),
        REDACTION_MARKER,
    ),
    RedactionRule(
        "openai-compatible-key",
        re.compile(r"\bsk-(?:(?:proj|svcacct)-)?[A-Za-z0-9_-]{20,}\b"),
        REDACTION_MARKER,
    ),
    RedactionRule(
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        REDACTION_MARKER,
    ),
    RedactionRule(
        "quoted-assignment",
        QUOTED_ASSIGNMENT,
        rf"\g<prefix>\g<quote>{REDACTION_MARKER}\g<quote>",
    ),
    RedactionRule(
        "unquoted-assignment",
        unquoted_assignment_pattern(REDACTION_MARKER),
        _redact_unquoted_assignment,
    ),
)


def _redact_mapping_value(key: Any, value: Any) -> Any:
    """Redact a value using its mapping key as additional security context."""

    if isinstance(key, str):
        if is_secret_label(key):
            return REDACTION_MARKER
        if key.strip().strip("\"'").casefold() == "auth" and isinstance(value, str) and _is_docker_auth_value(value):
            return REDACTION_MARKER
    return redact_for_output(value)


def redact_sensitive_text(value: str) -> str:
    """Return text with common credential forms replaced by a stable marker.

    The operation is deterministic and idempotent. It intentionally preserves
    surrounding context so findings remain useful without copying credentials
    into logs, reports, generated context, or CI artifacts.
    """

    redacted = _redact_yaml_secret_blocks(value)
    for rule in _RULES:
        redacted = rule.pattern.sub(rule.replacement, redacted)
    return redacted


def _redact_mapping(value: Mapping[Any, Any]) -> dict[Any, Any]:
    """Redact mapping keys and values without collisions or derived secret hashes."""

    prepared: list[tuple[Any, Any, Any]] = []
    collision_groups: dict[Any, list[Any]] = {}
    for key, item in value.items():
        redacted_key = redact_sensitive_text(key) if isinstance(key, str) else key
        prepared.append((key, redacted_key, item))
        collision_groups.setdefault(redacted_key, []).append(key)

    proposed_keys: dict[Any, Any] = {}
    for redacted_key, original_keys in collision_groups.items():
        if len(original_keys) == 1:
            proposed_keys[original_keys[0]] = redacted_key
            continue
        for index, original_key in enumerate(sorted(original_keys, key=repr), start=1):
            proposed_keys[original_key] = f"{redacted_key}#{index}" if isinstance(redacted_key, str) else redacted_key

    assigned_keys: dict[Any, Any] = {}
    occupied: set[Any] = set()
    ordered_proposals = sorted(
        proposed_keys.items(),
        key=lambda item: (
            repr(item[1]),
            item[0] != item[1],
            repr(item[0]),
        ),
    )
    for original_key, proposed_key in ordered_proposals:
        output_key = proposed_key
        if output_key in occupied and isinstance(output_key, str):
            suffix = 1
            while f"{output_key}#{suffix}" in occupied:
                suffix += 1
            output_key = f"{output_key}#{suffix}"
        assigned_keys[original_key] = output_key
        occupied.add(output_key)

    output: dict[Any, Any] = {}
    for original_key, _redacted_key, item in prepared:
        output[assigned_keys[original_key]] = _redact_mapping_value(original_key, item)
    return output


def redact_for_output(value: Any) -> Any:
    """Recursively redact keys and values while preserving JSON-compatible shape."""

    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, Mapping):
        return _redact_mapping(value)
    if isinstance(value, list):
        return [redact_for_output(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_for_output(item) for item in value)
    if isinstance(value, set | frozenset):
        return type(value)(redact_for_output(item) for item in value)
    return value
