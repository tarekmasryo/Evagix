from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TextIO

_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = "\x1b[2m"
_RED = "\x1b[31m"
_GREEN = "\x1b[32m"
_YELLOW = "\x1b[33m"
_CYAN = "\x1b[36m"


@dataclass(frozen=True)
class TerminalStyle:
    enabled: bool = False

    def _apply(self, text: str, code: str) -> str:
        if not self.enabled:
            return text
        return f"{code}{text}{_RESET}"

    def heading(self, text: str) -> str:
        return self._apply(text, _BOLD)

    def muted(self, text: str) -> str:
        return self._apply(text, _DIM)

    def success(self, text: str) -> str:
        return self._apply(text, _GREEN)

    def warning(self, text: str) -> str:
        return self._apply(text, _YELLOW)

    def error(self, text: str) -> str:
        return self._apply(text, _RED)

    def info(self, text: str) -> str:
        return self._apply(text, _CYAN)

    def semantic(self, text: str) -> str:
        normalized = text.strip().casefold().replace("_", "-")
        if normalized in {"pass", "passed", "ok", "ready", "clear", "merge"}:
            return self.success(text)
        if normalized in {"warn", "warning", "review", "limited", "early", "medium"}:
            return self.warning(text)
        if normalized in {"fail", "failed", "error", "not-ready", "block", "critical", "high"}:
            return self.error(text)
        if normalized in {"info", "low"}:
            return self.info(text)
        return text

    def maturity(self, maturity_level: str) -> str:
        normalized = maturity_level.strip().casefold()
        if normalized in {"clear", "ready"}:
            return self._apply(maturity_level, _GREEN)
        if normalized in {"limited", "early"}:
            return self._apply(maturity_level, _YELLOW)
        if normalized == "not-ready":
            return self._apply(maturity_level, _RED)
        return self._apply(maturity_level, _CYAN)

    def status(self, status: str, *, width: int = 0) -> str:
        label = _status_label(status)
        padded = label.ljust(width)
        if label == "PASS":
            return self._apply(padded, _GREEN)
        if label == "WARN":
            return self._apply(padded, _YELLOW)
        if label in {"FAIL", "ERROR", "CRITICAL", "HIGH"}:
            return self._apply(padded, _RED)
        return self._apply(padded, _CYAN)

    def severity(self, severity: str, *, width: int = 0) -> str:
        normalized = severity.strip().casefold()
        label = {"warning": "WARN", "error": "ERROR", "info": "INFO"}.get(normalized, normalized.upper())
        padded = label.ljust(width)
        if normalized in {"critical", "error", "high"}:
            return self._apply(padded, _RED)
        if normalized in {"warning", "medium"}:
            return self._apply(padded, _YELLOW)
        return self._apply(padded, _CYAN)


PLAIN_STYLE = TerminalStyle()


def terminal_style(
    stream: TextIO,
    *,
    no_color: bool = False,
    environ: Mapping[str, str] | None = None,
) -> TerminalStyle:
    environment = os.environ if environ is None else environ
    if no_color or "NO_COLOR" in environment or "CI" in environment:
        return PLAIN_STYLE
    if environment.get("TERM", "").casefold() == "dumb":
        return PLAIN_STYLE
    try:
        return TerminalStyle(enabled=bool(stream.isatty()))
    except (AttributeError, OSError):
        return PLAIN_STYLE


def _status_label(status: str) -> str:
    normalized = status.strip().casefold().replace("_", "-")
    if normalized in {"pass", "passed", "ok", "ready", "clear"}:
        return "PASS"
    if normalized in {"warn", "warning", "needs-attention", "limited", "early"}:
        return "WARN"
    if normalized in {"fail", "failed", "error", "not-ready"}:
        return "FAIL" if normalized != "error" else "ERROR"
    return status.upper()


_SEMANTIC_TOKEN = re.compile(r"(?<![A-Za-z0-9_-])(PASS|WARN|FAIL|ERROR|INFO|CRITICAL|HIGH|MEDIUM|LOW)(?![A-Za-z0-9_-])")


def style_human_text(content: str, style: TerminalStyle) -> str:
    """Style line-oriented human output without changing its visible text."""

    if not style.enabled:
        return content
    lines = content.splitlines(keepends=True)
    first_content = next((index for index, line in enumerate(lines) if line.strip()), None)
    rendered: list[str] = []
    for index, line in enumerate(lines):
        body = line.rstrip("\r\n")
        ending = line[len(body) :]
        stripped = body.strip()
        is_heading = bool(stripped) and (
            index == first_content
            or (stripped.startswith("#") and stripped.lstrip("#").startswith(" "))
            or (not body.startswith((" ", "-", "*")) and stripped.endswith(":"))
        )
        if is_heading:
            body = style.heading(body)
        elif stripped.startswith(("Experimental:", "Preview:", "Scope:", "Apply with:")):
            body = style.muted(body)
        else:
            body = _SEMANTIC_TOKEN.sub(lambda match: style.semantic(match.group(0)), body)
        rendered.append(body + ending)
    return "".join(rendered)
