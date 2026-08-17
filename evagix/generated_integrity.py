from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from evagix.utils import normalize_generated_content, sha256_text, stable_json

CONTENT_DIGEST_PREFIX = "evagix:content-digest="
CONTENT_DIGEST_RE = re.compile(rf"{re.escape(CONTENT_DIGEST_PREFIX)}([a-f0-9]{{64}})")
JSON_CONTENT_DIGEST_KEY = "_evagix_content_digest"
INTEGRITY_MANIFEST_PATH = ".evagix/integrity.json"
INTEGRITY_MANIFEST_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class IntegrityManifest:
    """Recorded digests from the last successful context generation."""

    source_fingerprint: str
    target_digests: dict[str, str]


def with_integrity_manifest(outputs: dict[str, str], source_fingerprint: str) -> dict[str, str]:
    """Return generated outputs plus a sidecar manifest of last-generation digests."""

    managed = dict(outputs)
    target_digests = {
        path: generated_content_digest(content)
        for path, content in sorted(managed.items())
        if path != INTEGRITY_MANIFEST_PATH
    }
    payload = {
        "_evagix_generated": "evagix:generated",
        "_evagix_fingerprint": f"evagix:fingerprint={source_fingerprint}",
        "schema_version": INTEGRITY_MANIFEST_SCHEMA_VERSION,
        "targets": {path: {"content_digest": digest} for path, digest in target_digests.items()},
    }
    managed[INTEGRITY_MANIFEST_PATH] = attach_content_digest(stable_json(payload, redact=False) + "\n")
    return managed


def parse_integrity_manifest(content: str) -> IntegrityManifest | None:
    """Parse a generated integrity manifest, returning None for invalid content."""

    try:
        payload = json.loads(normalize_generated_content(content))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("_evagix_generated") != "evagix:generated":
        return None
    if payload.get("schema_version") != INTEGRITY_MANIFEST_SCHEMA_VERSION:
        return None
    fingerprint_marker = payload.get("_evagix_fingerprint")
    raw_targets = payload.get("targets")
    if not isinstance(fingerprint_marker, str) or not isinstance(raw_targets, dict):
        return None
    prefix = "evagix:fingerprint="
    if not fingerprint_marker.startswith(prefix):
        return None
    source_fingerprint = fingerprint_marker[len(prefix) :]
    if not source_fingerprint:
        return None
    target_digests: dict[str, str] = {}
    for path, metadata in raw_targets.items():
        if not isinstance(path, str) or not isinstance(metadata, dict):
            return None
        digest = metadata.get("content_digest")
        if not isinstance(digest, str) or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
            return None
        target_digests[path] = digest
    return IntegrityManifest(source_fingerprint=source_fingerprint, target_digests=target_digests)


def attach_content_digest(content: str) -> str:
    """Attach a deterministic digest to an Evagix-managed output.

    Markdown-like outputs store the digest in the existing management marker.
    JSON outputs store it in a reserved top-level key. Re-applying this
    function is idempotent.
    """

    normalized = normalize_generated_content(content)
    if _looks_like_json(normalized):
        return _attach_json_digest(normalized)
    return _attach_text_digest(normalized)


def extract_content_digest(content: str) -> str | None:
    normalized = normalize_generated_content(content)
    if _looks_like_json(normalized):
        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError:
            return None
        value = payload.get(JSON_CONTENT_DIGEST_KEY) if isinstance(payload, dict) else None
        return value if isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) else None
    match = CONTENT_DIGEST_RE.search(normalized)
    return match.group(1) if match else None


def content_digest_matches(content: str) -> bool | None:
    """Return True/False for managed digests, or None for legacy outputs."""

    existing = extract_content_digest(content)
    if existing is None:
        return None
    return existing == generated_content_digest(content)


def generated_content_digest(content: str) -> str:
    """Return the canonical digest for generated content excluding its digest field."""

    normalized = normalize_generated_content(content)
    if _looks_like_json(normalized):
        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError:
            return sha256_text(_strip_text_digest(normalized))
        if isinstance(payload, dict):
            payload = dict(payload)
            payload.pop(JSON_CONTENT_DIGEST_KEY, None)
            return sha256_text(stable_json(payload, redact=False) + "\n")
    return sha256_text(_strip_text_digest(normalized))


def _attach_text_digest(content: str) -> str:
    without_digest = _strip_text_digest(content)
    digest = sha256_text(without_digest)
    lines = without_digest.splitlines(keepends=True)
    for index, line in enumerate(lines[:5]):
        if "evagix:generated" not in line:
            continue
        newline = "\n" if line.endswith("\n") else ""
        body = line[:-1] if newline else line
        if body.rstrip().endswith("-->"):
            body = body.rstrip()[:-3].rstrip() + f" {CONTENT_DIGEST_PREFIX}{digest} -->"
        else:
            body = body.rstrip() + f" {CONTENT_DIGEST_PREFIX}{digest}"
        lines[index] = body + newline
        return "".join(lines)
    return content


def _strip_text_digest(content: str) -> str:
    return re.sub(rf"\s+{re.escape(CONTENT_DIGEST_PREFIX)}[a-f0-9]{{64}}", "", content)


def _attach_json_digest(content: str) -> str:
    try:
        payload: Any = json.loads(content)
    except json.JSONDecodeError:
        return content
    if not isinstance(payload, dict) or "_evagix_generated" not in payload:
        return content
    clean = dict(payload)
    clean.pop(JSON_CONTENT_DIGEST_KEY, None)
    digest = sha256_text(stable_json(clean, redact=False) + "\n")
    clean[JSON_CONTENT_DIGEST_KEY] = digest
    return stable_json(clean) + "\n"


def _looks_like_json(content: str) -> bool:
    return content.lstrip().startswith("{")
