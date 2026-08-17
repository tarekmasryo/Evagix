"""Shared parsing helpers for commands documented in repository text."""

from __future__ import annotations

import re

_SHELL_FENCE_LANGUAGES = frozenset({"", "bash", "sh", "shell", "powershell", "ps1", "zsh"})
_DOCUMENTATION_MARKERS = ("checks", "detects", "flags", "only treated as supported")
_EXAMPLE_MARKERS = ("for example", "example output", "example finding")


def strip_command_documentation_examples(text: str) -> str:
    """Remove prose examples that should not be treated as executable guidance."""

    cleaned: list[str] = []
    for line in text.splitlines():
        lower = line.lower()
        if "evagix" in lower and any(marker in lower for marker in _DOCUMENTATION_MARKERS):
            cleaned.append("")
            continue
        if "`" in line and any(marker in lower for marker in _EXAMPLE_MARKERS):
            cleaned.append("")
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def extract_shell_code_blocks(text: str) -> list[str]:
    """Return fenced or RST literal blocks that can contain shell commands."""

    blocks: list[str] = []
    for match in re.finditer(r"```([^`\n]*)\n(.*?)```", text, flags=re.IGNORECASE | re.DOTALL):
        language_info = match.group(1).strip().lower()
        language = language_info.split()[0] if language_info else ""
        if language in _SHELL_FENCE_LANGUAGES:
            blocks.append(match.group(2))
    blocks.extend(_extract_rst_shell_literal_blocks(text))
    return blocks


def _extract_rst_shell_literal_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if not lines[index].rstrip().endswith("::"):
            index += 1
            continue
        cursor = index + 1
        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1
        literal_lines: list[str] = []
        while cursor < len(lines):
            match = re.match(r"^[ \t]+(.*)$", lines[cursor])
            if not match:
                break
            literal_lines.append(match.group(1))
            cursor += 1
        if literal_lines and _has_shell_literal_signal(literal_lines):
            blocks.append("\n".join(literal_lines))
        index = max(index + 1, cursor)
    return blocks


def _has_shell_literal_signal(lines: list[str]) -> bool:
    for line in lines:
        stripped = line.lstrip()
        if re.match(r"^(?:[$>]\s+\S|\./\S)", stripped):
            return True
        if re.search(r"\s(?:&&|\|\||;)\s", stripped):
            return True
    return False


def split_shell_command_chain(line: str) -> list[str]:
    """Split a documented shell chain into normalized executable commands."""

    return [command for command, _operator in split_shell_command_sequence(line)]


def split_shell_command_sequence(line: str) -> list[tuple[str, str | None]]:
    """Return normalized commands while preserving each preceding chain operator."""

    stripped = line.strip().lstrip("$> ").strip()
    if not stripped:
        return []
    commands: list[tuple[str, str | None]] = []
    operator: str | None = None
    for index, segment in enumerate(re.split(r"\s*(&&|\|\||;)\s*", stripped)):
        if index % 2:
            operator = segment
            continue
        command = segment.strip()
        if command.casefold().startswith("sudo "):
            command = command[5:].lstrip()
        if command:
            commands.append((command, operator))
        operator = None
    return commands
