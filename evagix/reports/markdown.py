from __future__ import annotations

from collections.abc import Mapping, Sequence


def table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    if not rows:
        return ""
    header = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join([header, sep, *body]) + "\n"


def bullet_list(items: Sequence[str]) -> str:
    if not items:
        return "- None.\n"
    return "\n".join(f"- {item}" for item in items) + "\n"


def front_matter(data: Mapping[str, object]) -> str:
    lines = ["---"]
    for key, value in data.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n"
