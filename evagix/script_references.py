"""Extract a bounded subset of literal script commands with source positions."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from evagix.reference_links import (
    _FENCE,
    _HTML_BLOCK,
    _HTML_TAG_LINE,
    LocalLink,
    _blank,
    _markdown_lines,
    _visible_text,
)

_LANGUAGES = frozenset({"bash", "sh", "shell", "zsh", "powershell", "pwsh", "ps1"})
_HEADING = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+|$)")
_INLINE = re.compile(
    r"^ {0,3}(?:(?:[-+*]|[0-9]{1,9}[.)]) )?(?:Run|Execute) "
    r"(?P<ticks>\x60{1,3})(?P<command>[^\x60\r\n]{1,4096})(?P=ticks)\.?[ \t]*$",
    re.IGNORECASE,
)
_TOKEN = re.compile(r"""'[^'\r\n]*'|"[^"\r\n]*"|[^ \t'"\r\n]+""")
_PYTHON = re.compile(r"python(?:3(?:\.[0-9]+)?)?(?:\.exe)?\Z")
_PYTHON_FLAGS = frozenset({"-B", "-E", "-I", "-O", "-OO", "-s", "-S", "-u"})
_SHELL_FLAGS = frozenset({"-e", "-u", "-x", "-n", "-eu", "-ue", "-eux"})
_POWERSHELL_FLAGS = frozenset({"-nologo", "-noprofile", "-noninteractive"})
_METACHARACTERS = re.compile(r"[$\x60;&|<>{}()*?\[\]\\#]")
_COMMAND_LIMIT = 4096
_TARGET_LIMIT = 2048


@dataclass(frozen=True)
class _Token:
    value: str
    start: int


def _tokens(command: str) -> list[_Token] | None:
    if (
        len(command) > _COMMAND_LIMIT
        or _METACHARACTERS.search(command)
        or any(
            (unicodedata.category(char).startswith("C") and char != "\t") or char in "\u2028\u2029" for char in command
        )
    ):
        return None
    result = []
    cursor = 0
    while cursor < len(command):
        if command[cursor] in " \t":
            cursor += 1
            continue
        match = _TOKEN.match(command, cursor)
        if match is None or (match.end() < len(command) and command[match.end()] not in " \t"):
            return None
        raw = match[0]
        result.append(_Token(raw[1:-1] if raw.startswith(("'", '"')) else raw, cursor))
        cursor = match.end()
    return result


def _target(value: str) -> str | None:
    # Shell paths are not URLs. Never decode percent escapes, fragments, or "..".
    if (
        not value
        or len(value) > _TARGET_LIMIT
        or value.startswith(("/", "~", "-", "+"))
        or value.endswith(("/", "/."))
        or value != value.strip()
        or ":" in value
        or ".." in value.split("/")
        or any(unicodedata.category(char).startswith("C") or char in "\u2028\u2029" for char in value)
    ):
        return None
    return "/".join(part for part in value.split("/") if part not in {"", "."}) or None


def _script_argument(command: str) -> _Token | None:
    tokens = _tokens(command)
    if not tokens:
        return None
    if command[tokens[0].start] in {"'", '"'}:
        # Quoted executable names can be string expressions in PowerShell.
        return None
    program = tokens[0].value
    index = 1
    if _PYTHON.fullmatch(program):
        while index < len(tokens) and tokens[index].value in _PYTHON_FLAGS:
            index += 1
    elif program in {"bash", "sh", "zsh"}:
        while index < len(tokens) and tokens[index].value in _SHELL_FLAGS:
            index += 1
    elif program in {"node", "node.exe"}:
        pass
    elif program in {"pwsh", "powershell", "pwsh.exe", "powershell.exe"}:
        while index < len(tokens) and tokens[index].value.lower() in _POWERSHELL_FLAGS:
            index += 1
        if index >= len(tokens) or tokens[index].value.lower() != "-file":
            return None
        index += 1
    elif program.startswith("./"):
        index = 0
    else:
        return None
    if index >= len(tokens):
        return None
    token = tokens[index]
    target = _target(token.value)
    return _Token(target, token.start) if target is not None else None


def _fence_references(lines: list[tuple[int, str]]) -> list[LocalLink]:
    result = []
    for number, line in lines:
        if not line.strip() or line.lstrip(" \t").startswith("#"):
            continue
        token = _script_argument(line)
        if token is None:
            # A different line may change cwd, start a heredoc, or wrap commands.
            return []
        result.append(LocalLink(token.value, number, token.start + 1))
    return result


def _inline_references(text: str) -> dict[int, LocalLink]:
    result: dict[int, LocalLink] = {}
    pending: dict[int, LocalLink] = {}
    valid = True
    visible_lines = _markdown_lines(_visible_text(text))
    for number, line in enumerate(_markdown_lines(text), 1):
        value = line.rstrip("\r\n")
        if not value.strip() or _HEADING.match(value) or _FENCE.match(value):
            if valid:
                result.update(pending)
            pending = {}
            valid = True
            continue
        instruction = _INLINE.fullmatch(value)
        token = _script_argument(instruction["command"]) if instruction else None
        if instruction is None or token is None:
            valid = False
            continue
        prefix_end = instruction.start("command") - len(instruction["ticks"])
        if visible_lines[number - 1][:prefix_end] != value[:prefix_end]:
            valid = False
            continue
        pending[number] = LocalLink(token.value, number, instruction.start("command") + token.start + 1)
    if valid:
        result.update(pending)
    return result


def extract_script_references(text: str) -> list[LocalLink]:
    """Inspect explicit instructions, assuming commands start at the repo root.

    Accept closed, top-level, labeled shell fences containing only supported
    direct invocations, blank lines and comments. Also accept whole-line Run or
    Execute instructions with one inline code span and optional final period,
    in contiguous blocks containing only supported instructions.
    Positions point to the original argument, including its quote if present.
    Unsupported syntax is excluded, not interpreted as proof of valid commands.
    """
    masked = re.sub(r"<!--.*?(?:-->|\Z)", lambda match: _blank(match[0]), text, flags=re.DOTALL)
    masked = re.sub(
        r"<(pre|code|script|style|textarea)(?=[\s>])[^>]*>.*?(?:</\1\s*>|\Z)",
        lambda match: _blank(match[0]),
        masked,
        flags=re.IGNORECASE | re.DOTALL,
    )
    result = []
    fence = ""
    supported = False
    block: list[tuple[int, str]] = []
    quoted = False
    html_block = False
    inline = _inline_references(text)
    for number, (original, line) in enumerate(zip(_markdown_lines(text), _markdown_lines(masked), strict=True), 1):
        value = line.rstrip("\r\n")
        marker = _FENCE.match(value)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                if supported:
                    result.extend(_fence_references(block))
                fence = ""
                block = []
            else:
                supported = supported and original == line
                block.append((number, value))
            continue
        if quoted or original.lstrip(" ").startswith(">"):
            quoted = bool(original.strip(" \t\r\n"))
            continue
        if html_block or _HTML_BLOCK.match(line) or _HTML_TAG_LINE.fullmatch(value):
            html_block = bool(original.strip(" \t\r\n"))
            continue
        if marker and (marker[1][0] != "\x60" or "\x60" not in marker[2]):
            fence = marker[1]
            supported = not line.startswith((" ", "\t")) and marker[2].strip().lower() in _LANGUAGES
            continue
        if original != line:
            continue
        if number in inline:
            result.append(inline[number])
    return result
