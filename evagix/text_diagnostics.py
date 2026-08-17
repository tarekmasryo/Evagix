from __future__ import annotations

from pathlib import Path

from evagix.evidence import Finding


def invalid_utf8_finding(root: Path, path: Path, *, scanner: str, category: str) -> Finding:
    """Return a fail-closed finding without exposing undecodable file bytes."""

    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        relative = path.as_posix()
    return Finding(
        id="text.invalid-utf8",
        title="Text file is not valid UTF-8",
        category=category,
        severity="high",
        status="incomplete",
        source=relative,
        source_file=relative,
        evidence=[f"{scanner} could not decode this file as UTF-8"],
        risk=(
            "The file was not fully inspected; ignoring undecodable bytes could hide commands, credentials, "
            "or hostile instructions."
        ),
        recommendation=(
            "Convert the file to valid UTF-8, review the conversion, and rerun Evagix before relying on the result."
        ),
        confidence="high",
        root_cause=f"invalid-utf8:{relative}",
    )
