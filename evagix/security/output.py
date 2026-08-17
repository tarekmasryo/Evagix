from __future__ import annotations

import sys
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from functools import wraps
from io import StringIO
from typing import ParamSpec, TextIO, TypeVar

from evagix.security.redaction import redact_for_output, redact_sensitive_text

P = ParamSpec("P")
T = TypeVar("T")


def redacted_text_output(function: Callable[P, str]) -> Callable[P, str]:
    """Decorate a public text renderer with the central redaction policy."""

    @wraps(function)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> str:
        return redact_sensitive_text(function(*args, **kwargs))

    return wrapper


def _redact_exception(exception: BaseException, seen: set[int] | None = None) -> None:
    """Sanitize exception payloads that may be rendered after the CLI boundary exits."""

    visited = seen if seen is not None else set()
    identity = id(exception)
    if identity in visited:
        return
    visited.add(identity)

    exception.args = tuple(redact_for_output(item) for item in exception.args)
    notes = getattr(exception, "__notes__", None)
    if notes is not None:
        exception.__notes__ = [redact_sensitive_text(note) for note in notes]
    if exception.__cause__ is not None:
        _redact_exception(exception.__cause__, visited)
    if exception.__context__ is not None:
        _redact_exception(exception.__context__, visited)


def _write_text(stream: TextIO, text: str) -> None:
    """Write text without failing on characters unsupported by the stream."""

    try:
        stream.write(text)
    except UnicodeEncodeError as error:
        encoding = stream.encoding or error.encoding
        escaped = text.encode(encoding, errors="backslashreplace").decode(encoding)
        stream.write(escaped)


def execute_with_redacted_output(action: Callable[[], T]) -> T:
    """Execute a CLI action behind a final redaction boundary.

    Command implementations may render many output formats and failure paths.
    Capturing each complete stream before emission prevents a forgotten print,
    renderer, or exception message from bypassing the central redaction policy.
    """

    stdout_target = sys.stdout
    stderr_target = sys.stderr
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    try:
        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            return action()
    except BaseException as exception:
        _redact_exception(exception)
        raise
    finally:
        _write_text(stdout_target, redact_sensitive_text(stdout_buffer.getvalue()))
        _write_text(stderr_target, redact_sensitive_text(stderr_buffer.getvalue()))
        stdout_target.flush()
        stderr_target.flush()
