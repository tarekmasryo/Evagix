from __future__ import annotations

import re
from typing import Final

_DIRECT_SECRET_LABEL: Final = (
    r"(?:api[_-]?key|secret(?:[_-]?key)?|token|access[_-]?token|session[_-]?token|"
    r"auth[_-]?token|client[_-]?secret|password|passwd|pwd|account[_-]?key|"
    r"aws[_-]?secret[_-]?access[_-]?key|aws[_-]?session[_-]?token|"
    r"pgpassword|pgpassfile|fernet[_-]?key|encryption[_-]?key|secret[_-]?key[_-]?base)"
)
_COMPOUND_SECRET_SUFFIX: Final = (
    r"(?:password|passwd|pwd|secret(?:[_-]?key)?|token|access[_-]?token|session[_-]?token|"
    r"auth[_-]?token|api[_-]?key|client[_-]?secret|private[_-]?key|signing[_-]?key|"
    r"encryption[_-]?key|master[_-]?key|account[_-]?key)"
)

# The prefix accepts multiple repository-, provider-, and framework-specific
# segments. The credential-bearing suffix must remain at the end, which keeps
# metadata such as token_count and password_policy outside the match.
SECRET_LABEL_REGEX: Final = rf"(?:{_DIRECT_SECRET_LABEL}|[A-Za-z][A-Za-z0-9._-]*(?:[_-]{_COMPOUND_SECRET_SUFFIX}))"
_SECRET_LABEL_PATTERN: Final = re.compile(rf"(?:{SECRET_LABEL_REGEX})", re.IGNORECASE)


def is_secret_label(value: str) -> bool:
    """Return whether a field name conventionally carries credential material."""

    normalized = value.strip().strip("\"'")
    return _SECRET_LABEL_PATTERN.fullmatch(normalized) is not None
