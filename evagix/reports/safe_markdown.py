"""Literal, redacted values for advisory Markdown reports."""

from __future__ import annotations

import json
import re
import unicodedata
from urllib.parse import quote, urlsplit

from evagix.security.redaction import redact_sensitive_text

_MAX_MARKDOWN_BYTES = 450_000


def markdown_code(value: object) -> str:
    """Keep provider/repository text inside one inline code span, never a table."""
    text = redact_sensitive_text(str(value))
    text = "".join(
        json.dumps(char, ensure_ascii=True)[1:-1]
        if unicodedata.category(char) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
        else char
        for char in text
    )
    delimiter = "`" * (1 + max((len(run) for run in re.findall(r"`+", text)), default=0))
    return f"{delimiter} {text} {delimiter}"


def markdown_details(value: object) -> str:
    """Link an ordinary HTTPS detail URL; render unsafe/redacted URLs literally."""
    text = redact_sensitive_text(str(value))
    try:
        parsed = urlsplit(text)
        safe = (
            len(text) <= 2048
            and parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and parsed.port in (None, 443)
            and "[REDACTED" not in text
            and not any(char.isspace() or unicodedata.category(char)[0] == "C" for char in text)
        )
    except ValueError:
        safe = False
    if not safe:
        return markdown_code(text)
    # The label is fixed. Encode Markdown/HTML delimiters even inside <...>.
    destination = quote(text, safe=":/?#[]@!$&*+,;=%").replace("&", "&amp;")
    return f"[Details](<{destination}>)"


def bounded_markdown(text: str) -> str:
    """Bound each section; combined summaries enforce their own total limit."""
    if len(text.encode("utf-8")) > _MAX_MARKDOWN_BYTES:
        raise ValueError(
            f"Markdown report exceeds the {_MAX_MARKDOWN_BYTES}-byte output limit; use JSON for the complete report."
        )
    return text
