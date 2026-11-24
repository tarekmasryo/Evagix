"""Strict JSON decoding at optional evidence input boundaries."""

from __future__ import annotations

import json
import math
from typing import Any, NoReturn

from evagix.verification.contracts import ContractError


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ContractError("Duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> NoReturn:
    raise ContractError("Non-finite JSON value")


def _float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ContractError("Non-finite JSON value")
    return number


def decode_object(text: str) -> dict[str, Any]:
    """Reject ambiguous objects without including their contents in errors."""
    if type(text) is not str:
        raise ContractError("Invalid JSON text")
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float)
    except (ValueError, RecursionError):
        raise ContractError("Invalid JSON object") from None
    if type(value) is not dict:
        raise ContractError("Expected a JSON object")
    return value
