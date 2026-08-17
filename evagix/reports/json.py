from __future__ import annotations

from typing import Any

from evagix import __version__
from evagix.utils import stable_json


def base_payload(repository: str, *, ok: bool = True, schema_version: str = "1.0") -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "tool": "evagix",
        "version": __version__,
        "repository": repository,
        "ok": ok,
    }


def render_json(payload: dict[str, Any]) -> str:
    return stable_json(payload) + "\n"
