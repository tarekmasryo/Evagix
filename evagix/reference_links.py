"""Conservative extraction of explicit local links from root Markdown documents.

This is deliberately a subset of Markdown: same-line inline links and images,
with simple labels and optional quoted titles. Reference links, HTML attributes,
bare paths, and code examples are not evidence of a live file reference here.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict, deque
from dataclasses import dataclass
from urllib.parse import unquote

_LINK = re.compile(
    r"(?<![\\\[])\[[^\[\]\n]*\]\([ \t]*"
    r"(?:<(?P<angle>[^<>\n]{1,2048})>|(?P<plain>[^\s()<>\[\]]{1,2048}))"
    r"(?:[ \t]+(?:\"[^\"\n]*\"|'[^'\n]*'))?[ \t]*\)"
)
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_HTML_BLOCK = re.compile(
    r"^ {0,3}</?(?:address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|"
    r"details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|h[1-6]|head|"
    r"header|hr|html|iframe|legend|li|link|main|menu|menuitem|nav|noframes|ol|optgroup|option|p|"
    r"param|search|section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul)(?=[\s/>]|$)",
    re.IGNORECASE,
)
_HTML_TAG_LINE = re.compile(r"^ {0,3}</?[A-Za-z][A-Za-z0-9-]*(?:[ \t][^<>]*)?/?>[ \t]*$")
_LIST_ITEM = re.compile(r"^(?:[-+*]|[0-9]{1,9}[.)]) {1,4}(?P<content>\S.*)$")
_PARAGRAPH_BREAK = re.compile(
    r"^(?:[>#<]|(?:[-+*]|[0-9]{1,9}[.)])(?:[ \t]|$)|\[[^\]]+\]:|"
    r"(?:[-*_][ \t]*){3,}$|=+[ \t]*$)"
)


@dataclass(frozen=True)
class LocalLink:
    target: str
    line: int
    column: int


def _blank(text: str) -> str:
    return "".join(char if char in "\r\n" else " " for char in text)


def _markdown_lines(text: str) -> list[str]:
    # str.splitlines also splits Unicode separators that are content in Markdown.
    return re.split(r"(?<=\n)|(?<=\r)(?!\n)", text)


def _list_paragraph_indent(line: str, previous: int | None) -> int | None:
    # Only uninterrupted paragraphs in simple top-level list items are supported.
    # Do not reinterpret blank-separated, nested, tabbed, or code-span content.
    value = line.rstrip("\r\n")
    item = _LIST_ITEM.fullmatch(value)
    if item is not None:
        indent, content = item.start("content"), item["content"]
    elif previous is not None:
        spaces = len(value) - len(value.lstrip(" "))
        if not previous <= spaces <= previous + 3:
            return None
        indent, content = previous, value[spaces:]
    else:
        return None
    if (
        not content
        or "`" in content
        or content.startswith("\t")
        or _PARAGRAPH_BREAK.match(content)
        or _FENCE.match(content)
    ):
        return None
    return indent


def _visible_text(text: str) -> str:
    original_lines = _markdown_lines(text)
    text = re.sub(r"<!--.*?(?:-->|\Z)", lambda match: _blank(match[0]), text, flags=re.DOTALL)
    text = re.sub(
        r"<(pre|code|script|style|textarea)(?=[\s>])[^>]*>.*?(?:</\1\s*>|\Z)",
        lambda match: _blank(match[0]),
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    lines = []
    fence = ""
    quoted = False
    html_block = False
    list_indent = None
    for original, line in zip(original_lines, _markdown_lines(text), strict=True):
        next_list_indent = None
        marker = _FENCE.match(line.rstrip("\r\n"))
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = ""
            lines.append(_blank(line))
        elif quoted or original.lstrip(" ").startswith(">"):
            # Lazily continued quote paragraphs need no repeated > marker.
            quoted = bool(original.strip(" \t\r\n"))
            lines.append(_blank(line))
        elif html_block or _HTML_BLOCK.match(line) or _HTML_TAG_LINE.fullmatch(line.rstrip("\r\n")):
            html_block = bool(original.strip(" \t\r\n"))
            lines.append(_blank(line))
        elif marker and (marker[1][0] != "`" or "`" not in marker[2]):
            fence = marker[1]
            lines.append(_blank(line))
        else:
            next_list_indent = _list_paragraph_indent(line, list_indent)
            if original.startswith(("    ", "\t")) and next_list_indent is None:
                lines.append(_blank(line))
            else:
                lines.append(line)
        list_indent = next_list_indent
    text = "".join(lines)
    ticks = list(re.finditer(r"(?<![\\`])`+", text))
    by_length: dict[int, deque[int]] = defaultdict(deque)
    for index, match in enumerate(ticks):
        by_length[len(match[0])].append(index)
    output = list(text)
    index = 0
    while index < len(ticks):
        opener = ticks[index]
        matching = by_length[len(opener[0])]
        while matching and matching[0] <= index:
            matching.popleft()
        if matching:
            closing = matching.popleft()
            end = ticks[closing].end()
            output[opener.start() : end] = _blank(text[opener.start() : end])
            index = closing + 1
        else:
            index += 1
    return "".join(output)


def _local_target(raw: str) -> str | None:
    if re.search(r"%(?![0-9a-fA-F]{2})", raw):
        return None
    # Fragment delimiters are interpreted before URL decoding: %23 is a filename
    # character, whereas a literal # introduces a Markdown link fragment.
    raw = raw.split("#", 1)[0]
    try:
        path = unquote(raw, encoding="utf-8", errors="strict")
    except UnicodeError:
        return None
    if (
        not path
        or path.startswith(("/", "~"))
        or path.endswith(("/", "/.", "/.."))
        or any(char in path for char in "\\:?*[]{}$<>|")
        or any(unicodedata.category(char).startswith("C") or char in "\u2028\u2029" for char in path)
        or path != path.strip()
    ):
        return None
    parts: list[str] = []
    for part in path.split("/"):
        if part == "..":
            if not parts:
                return None
            parts.pop()
        elif part not in {"", "."}:
            parts.append(part)
    return "/".join(parts) or None


def extract_local_links(text: str) -> list[LocalLink]:
    """Return local link destinations and one-based positions in root documents.

    Positions point to the original destination, before decoding or normalizing.
    Fenced/indented code, blockquotes, comments and inline code are excluded.
    Quote continuations are conservatively excluded until a blank line.
    Raw HTML block tags and standalone tags are also excluded until a blank line.
    Plain list paragraphs may continue at their content indent plus 0-3 spaces.
    Backticks end this exception to avoid changing cross-line code-span masking.
    Unsupported syntax is ignored rather than guessed.
    """
    result = []
    for number, line in enumerate(_markdown_lines(_visible_text(text)), start=1):
        for match in _LINK.finditer(line):
            group = "angle" if match["angle"] is not None else "plain"
            target = _local_target(match[group])
            if target is not None:
                result.append(LocalLink(target, number, match.start(group) + 1))
    return result
