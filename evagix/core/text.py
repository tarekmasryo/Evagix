from __future__ import annotations


def line_at_index(text: str, index: int) -> str:
    """Return the complete line containing ``index`` without its newline."""

    start = text.rfind("\n", 0, index) + 1
    end = text.find("\n", index)
    return text[start:] if end == -1 else text[start:end]


def line_number_at_index(text: str, index: int) -> int:
    """Return the one-based line number containing ``index``."""

    return text.count("\n", 0, index) + 1


def escape_github_command_value(value: str) -> str:
    """Escape one value for GitHub workflow command and annotation syntax."""

    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A").replace(",", "%2C").replace(":", "%3A")
