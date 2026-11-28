"""Bounded extraction of literal pytest-cov declarations from block workflows.

This deliberately supports a subset of YAML and command syntax. It is neither a
workflow validator nor a shell interpreter; unsupported evidence stays explicit.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

_NODE_LIMIT = 10_000
_DEPTH_LIMIT = 32
_FLAG = "--cov-fail-under"
_KEY = re.compile(r"([\w-]+|'(?:[^']|'')*'|\"(?:[^\"\\]|\\.)*\"):(?:[ \t]+|$)(.*)")
_VALUE_OPTIONS = {
    "--cov",
    "--cov-report",
    "--cov-config",
    "--cov-precision",
    "--junitxml",
    "--junit-xml",
    "--rootdir",
    "--confcutdir",
    "--maxfail",
    "-c",
    "-k",
    "-m",
}
_SWITCHES = {
    "--cov-branch",
    "--cov-append",
    "--no-cov-on-fail",
    "--disable-warnings",
    "--strict-markers",
    "-q",
    "-qq",
    "-v",
    "-vv",
    "-x",
}


@dataclass(frozen=True)
class CoverageThreshold:
    job: str
    step_kind: str
    step: str
    value: str
    line: int
    column: int
    signature: tuple[str, ...]


@dataclass(frozen=True)
class ThresholdExtraction:
    thresholds: dict[tuple[str, str, str], CoverageThreshold]
    limitations: list[str]


@dataclass
class _Node:
    value: str | dict[str, _Node] | list[_Node]
    line: int
    column: int
    style: str = "plain"
    source_lines: list[tuple[int, int, str]] | None = None


def _uncomment(text: str) -> str:
    quote = ""
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            if quote == '"' and char == "\\":
                index += 2
                continue
            if char == quote:
                if quote == "'" and text[index : index + 2] == "''":
                    index += 2
                    continue
                quote = ""
        elif index == 0 and char in "\"'":
            # Only a quote opening the YAML scalar protects YAML comments.
            quote = char
        elif char == "#" and (index == 0 or text[index - 1].isspace()):
            return text[:index].rstrip()
        index += 1
    return text.rstrip()


def _literal(text: str) -> str:
    if text.startswith('"'):
        value = json.loads(text)
        if not isinstance(value, str):
            raise ValueError("unsupported string")
        return value
    if text.startswith("'"):
        if not re.fullmatch(r"'(?:[^']|'')*'", text):
            raise ValueError("unsupported string")
        return text[1:-1].replace("''", "'")
    if not text or text[0] in "&*!|>{[" or "${{" in text:
        raise ValueError("nonliteral identity")
    return text


class _Workflow:
    """Read block ownership without interpreting expressions or flow values."""

    def __init__(self, source: str) -> None:
        if any(char in source for char in "\x00\x85\u2028\u2029") or len(source.splitlines()) > _NODE_LIMIT:
            raise ValueError("workflow exceeds syntax limits")
        self.lines = source.splitlines()
        self.index = 0
        self.nodes = 0

    def peek(self) -> tuple[int, str, int] | None:
        while self.index < len(self.lines):
            raw = self.lines[self.index]
            if not raw.strip() or raw.lstrip().startswith("#"):
                self.index += 1
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            if raw[indent:].startswith("\t"):
                raise ValueError("tab indentation")
            return indent, raw[indent:].rstrip(), self.index + 1
        return None

    def block(self, indent: int, depth: int = 0) -> _Node:
        self.nodes += 1
        if depth > _DEPTH_LIMIT or self.nodes > _NODE_LIMIT:
            raise ValueError("workflow exceeds syntax limits")
        first = self.peek()
        if first is None or first[0] != indent:
            raise ValueError("unsupported indentation")
        if first[1] == "-" or first[1].startswith("- "):
            items: list[_Node] = []
            while (row := self.peek()) is not None and row[0] == indent and (row[1] == "-" or row[1].startswith("- ")):
                self.index += 1
                body = row[1][2:] if row[1] != "-" else ""
                if not body:
                    child = self.peek()
                    if child is None or child[0] <= indent:
                        raise ValueError("empty sequence entry")
                    items.append(self.block(child[0], depth + 1))
                elif _KEY.fullmatch(body):
                    items.append(self.mapping(indent + 2, depth + 1, (indent + 2, body, row[2])))
                else:
                    items.append(self.scalar(body, row[2], indent + 3, indent, depth + 1))
            return _Node(items, first[2], indent + 1)
        return self.mapping(indent, depth)

    def mapping(self, indent: int, depth: int, initial: tuple[int, str, int] | None = None) -> _Node:
        entries: dict[str, _Node] = {}
        first_line = initial[2] if initial else self.index + 1
        while True:
            row = initial or self.peek()
            if row is None or row[0] < indent:
                break
            if row[0] != indent:
                raise ValueError("unsupported indentation")
            if row[1] == "-" or row[1].startswith("- "):
                break
            match = _KEY.fullmatch(row[1])
            if match is None:
                raise ValueError("unsupported mapping")
            if initial is None:
                self.index += 1
            initial = None
            key = _literal(match[1])
            if key in entries or key == "<<":
                raise ValueError("duplicate or merged key")
            entries[key] = self.scalar(match[2], row[2], indent + match.start(2) + 1, indent, depth + 1)
        return _Node(entries, first_line, indent + 1)

    def scalar(self, text: str, line: int, column: int, indent: int, depth: int) -> _Node:
        self.nodes += 1
        if depth > _DEPTH_LIMIT or self.nodes > _NODE_LIMIT:
            raise ValueError("workflow exceeds syntax limits")
        text = _uncomment(text)
        if not text:
            child = self.peek()
            if child and (child[0] > indent or (child[0] == indent and child[1].startswith("-"))):
                return self.block(child[0], depth)
            return _Node("", line, column)
        if text.startswith(("&", "*", "!")):
            raise ValueError("YAML anchors, aliases or tags are unsupported")
        if text[0] in "|>":
            body: list[tuple[int, int, str]] = []
            while self.index < len(self.lines):
                raw = self.lines[self.index]
                width = len(raw) - len(raw.lstrip(" "))
                if raw.strip() and width <= indent:
                    break
                body.append((self.index + 1, width + 1, raw[width:]))
                self.index += 1
            return _Node("\n".join(item[2] for item in body), line, column, text, body)
        if text[0] in "\"'":
            # Multiline quoted scalars are deliberately unsupported.
            return _Node(_literal(text), line, column, "quoted")
        if ": " in text and not text.startswith(("{", "[")):
            raise ValueError("unsupported plain scalar")
        return _Node(text, line, column)

    def parse(self) -> dict[str, _Node]:
        root = self.block(0)
        if self.peek() is not None or not isinstance(root.value, dict):
            raise ValueError("unsupported workflow structure")
        return root.value


@dataclass(frozen=True)
class _Word:
    value: str
    offset: int
    expanded: bool


def _words(command: str) -> list[_Word]:
    words = []
    index = 0
    while index < len(command):
        if command[index].isspace():
            index += 1
            continue
        if command[index] == "#":
            break
        start, quote, expanded, value = index, "", False, ""
        while index < len(command) and (quote or not command[index].isspace()):
            char = command[index]
            if char in "\\`" or (not quote and char in ";&|<>(){}%*?[]"):
                raise ValueError("unsupported shell syntax")
            if char in "\"'" and (not quote or quote == char):
                quote = "" if quote else char
                index += 1
                continue
            if char == "$" and quote != "'":
                if quote != '"' or re.match(r"\$[A-Za-z_][A-Za-z0-9_]*", command[index:]) is None:
                    raise ValueError("unsupported expansion")
                expanded = True
            value += char
            index += 1
        if quote:
            raise ValueError("unclosed shell quote")
        words.append(_Word(value, start, expanded))
    return words


def _command(node: _Node) -> tuple[str, int, int]:
    if not isinstance(node.value, str) or node.style not in {"plain", "|", "|-", "|+"}:
        raise ValueError("unsupported run scalar")
    lines = node.source_lines or [(node.line, node.column, node.value)]
    active = [(line, col, text) for line, col, text in lines if text.strip() and not text.lstrip().startswith("#")]
    if len(active) != 1 or "${{" in active[0][2]:
        raise ValueError("run is not one literal command")
    line, col, text = active[0]
    return text, line, col


def _threshold(node: _Node) -> tuple[str, int, int, tuple[str, ...]] | None:
    if isinstance(node.value, str) and _FLAG not in node.value:
        return None
    command, line, column = _command(node)
    words = _words(command)
    if not any(_FLAG in word.value for word in words):
        return None
    values = [word.value for word in words]
    if words and command[words[0].offset] in "\"'":
        raise ValueError("quoted executable")
    if values[:1] == ["pytest"]:
        start = 1
    elif (
        len(values) >= 3
        and re.fullmatch(r"python(?:3(?:\.[0-9]+)?)?(?:\.exe)?", values[0])
        and values[1:3] == ["-m", "pytest"]
    ):
        start = 3
    else:
        raise ValueError("not a direct pytest invocation")
    signature = values[:start]
    found: tuple[str, int] | None = None
    index = start
    while index < len(words):
        word = words[index]
        option, separator, attached = word.value.partition("=")
        if option == _FLAG or option in _VALUE_OPTIONS:
            value = attached
            expanded = word.expanded
            if not separator:
                if index + 1 >= len(words) or words[index + 1].value.startswith("-"):
                    if option == "--cov":
                        signature.append(option)
                        index += 1
                        continue
                    raise ValueError("missing option value")
                index += 1
                value = words[index].value
                expanded = words[index].expanded
            if expanded and option not in {"--junitxml", "--junit-xml"}:
                raise ValueError("dynamic command argument")
            if option == _FLAG:
                if found is not None or expanded or len(value) > 64 or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
                    raise ValueError("ambiguous or nonliteral threshold")
                if Decimal(value) > 100:
                    raise ValueError("threshold outside percentage range")
                integer, dot, fraction = value.partition(".")
                normalized = integer.lstrip("0") or "0"
                if dot and fraction.rstrip("0"):
                    normalized += "." + fraction.rstrip("0")
                found = (normalized, column + word.offset)
                signature.extend((option, "<threshold>"))
            else:
                signature.extend((option, value))
        elif word.expanded or word.value.startswith("-") and word.value not in _SWITCHES:
            raise ValueError("unsupported pytest argument")
        else:
            signature.append(word.value)
        index += 1
    return (found[0], line, found[1], tuple(signature)) if found else None


def _mapping(node: _Node | None) -> dict[str, _Node]:
    if node is None or not isinstance(node.value, dict):
        raise ValueError("expected block mapping")
    return node.value


def _identity(node: _Node | None) -> str | None:
    if node is None:
        return None
    if not isinstance(node.value, str) or node.style not in {"plain", "quoted"}:
        raise ValueError("nonliteral step identity")
    value = _literal(node.value) if node.style == "plain" else node.value
    if not value or "${{" in value or "\n" in value or "\r" in value:
        raise ValueError("nonliteral step identity")
    return value


def _default_shell(fields: dict[str, _Node]) -> str | None:
    defaults = fields.get("defaults")
    if defaults is None:
        return None
    run = _mapping(defaults).get("run")
    return _identity(_mapping(run).get("shell")) if run is not None else None


def extract_coverage_thresholds(source: str) -> ThresholdExtraction:
    """Extract declarations; no execution, effective coverage, or policy claims."""
    report = ThresholdExtraction({}, [])
    try:
        root = _Workflow(source).parse()
        jobs = _mapping(root.get("jobs"))
        for job, job_node in jobs.items():
            fields = _mapping(job_node)
            steps_node = fields.get("steps")
            if steps_node is None:
                if "uses" in fields:
                    report.limitations.append(
                        f"line {job_node.line}: reusable workflows are outside the inspection scope."
                    )
                continue
            if not isinstance(steps_node.value, list):
                raise ValueError("unsupported steps structure")
            steps = [_mapping(item) for item in steps_node.value]
            ids = [_identity(step.get("id")) for step in steps]
            names = [_identity(step.get("name")) for step in steps]
            id_counts = Counter(ids)
            name_counts = Counter(names)
            for step, step_id, name in zip(steps, ids, names, strict=True):
                run = step.get("run")
                if run is None:
                    continue
                try:
                    extracted = _threshold(run)
                    if extracted is None:
                        continue
                    identity = ("id", step_id) if step_id else ("name", name)
                    count = id_counts[step_id] if step_id else name_counts[name]
                    if not identity[1] or count != 1 or "uses" in step:
                        raise ValueError("ambiguous step identity")
                    shell = _identity(step.get("shell")) or _default_shell(fields) or _default_shell(root)
                    if shell is not None and shell not in {"bash", "sh"}:
                        raise ValueError("unsupported shell")
                    value, line, column, signature = extracted
                    key = (job, identity[0], identity[1])
                    report.thresholds[key] = CoverageThreshold(*key, value, line, column, signature)
                except ValueError:
                    report.limitations.append(
                        f"line {run.line}: coverage declaration has unsupported or ambiguous command/step syntax."
                    )
    except (ValueError, RecursionError):
        # Never expose parser messages or raw repository commands.
        return ThresholdExtraction({}, ["Workflow structure is outside the supported block YAML subset."])
    return report
