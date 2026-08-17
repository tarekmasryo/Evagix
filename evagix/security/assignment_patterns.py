from __future__ import annotations

import re
from typing import Final

from evagix.security.labels import SECRET_LABEL_REGEX

_LABEL_START: Final = r"(?<![A-Za-z0-9_-])"
_LABEL_END: Final = r"(?![A-Za-z0-9_-])"

YAML_SECRET_BLOCK_HEADER: Final[re.Pattern[str]] = re.compile(
    rf"""^(?P<indent>[ \t]*)["']?{SECRET_LABEL_REGEX}["']?\s*:\s*[|>][+-]?[^\r\n]*$""",
    re.IGNORECASE,
)
SHELL_ENVIRONMENT_ASSIGNMENT: Final[re.Pattern[str]] = re.compile(
    rf"(?P<prefix>(?:^|[;&|])[ \t]*(?:(?:env|export)[ \t]+)?{SECRET_LABEL_REGEX}=)"
    rf"(?P<quote>[\"']?)(?P<value>[^\r\n]*?)(?P=quote)"
    r"(?P<suffix>[ \t]+(?=\S))",
    re.IGNORECASE | re.MULTILINE,
)
CMD_SET_ASSIGNMENT: Final[re.Pattern[str]] = re.compile(
    rf"(?P<prefix>\bset[ \t]+[\"']{SECRET_LABEL_REGEX}=)"
    r"(?P<value>[^\"'\r\n]*)(?P<suffix>[\"'])",
    re.IGNORECASE,
)
ENVIRONMENT_SETTER: Final[re.Pattern[str]] = re.compile(
    rf"(?P<prefix>\bsetx?\s+{SECRET_LABEL_REGEX}\s+)"
    rf"""(?P<quote>["']?)(?P<value>[^\s"']+)(?P=quote)""",
    re.IGNORECASE,
)
QUOTED_ASSIGNMENT: Final[re.Pattern[str]] = re.compile(
    rf"""(?P<prefix>{_LABEL_START}["']?{SECRET_LABEL_REGEX}["']?{_LABEL_END}\s*[:=]\s*)"""
    rf"""(?P<quote>["'])(?P<value>[^\r\n]*?)(?P=quote)""",
    re.IGNORECASE,
)


def unquoted_assignment_pattern(redaction_marker: str) -> re.Pattern[str]:
    """Build the generic assignment pattern around the configured marker."""

    return re.compile(
        rf"(?P<prefix>{_LABEL_START}{SECRET_LABEL_REGEX}{_LABEL_END}\s*[:=]\s*)"
        rf"""(?P<value>(?![ \t]*["'])(?![ \t]*{re.escape(redaction_marker)})[^\r\n;#]+)""",
        re.IGNORECASE,
    )
