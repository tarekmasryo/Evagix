"""Associate a local artifact archive with GitHub metadata, not test execution."""

from __future__ import annotations

import hashlib
import io
import os
import re
import stat
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evagix.security.redaction import redact_for_output
from evagix.verification.github_collection import GitHubCollectionError, _Client, _repository_name
from evagix.verification.junit import MAX_REPORT_BYTES, JUnitReport, _parse

MAX_ARCHIVE_BYTES = MAX_REPORT_BYTES + 100_000
_MAX_ID = 2**63 - 1
_SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_STATES = {"queued", "in_progress", "completed", "waiting", "pending", "requested"}
_CONCLUSIONS = {
    "success",
    "failure",
    "neutral",
    "cancelled",
    "skipped",
    "timed_out",
    "action_required",
    "stale",
    "startup_failure",
}


class _ArchiveError(ValueError):
    pass


class _MissingMetadata(ValueError):
    pass


def _id(value: object) -> int:
    if type(value) is not int or not 1 <= value <= _MAX_ID:
        raise ValueError("Invalid positive identifier")
    return value


@dataclass(frozen=True, repr=False)
class JUnitArtifactRequest:
    repository: str
    run_id: int
    attempt: int
    artifact_id: int
    revision: str
    member: str = "evagix-quality-junit.xml"

    def __post_init__(self) -> None:
        _repository_name(self.repository)
        for value in (self.run_id, self.attempt, self.artifact_id):
            _id(value)
        if type(self.revision) is not str or not _SHA.fullmatch(self.revision):
            raise ValueError("A full lowercase revision is required")
        if (
            type(self.member) is not str
            or not 1 <= len(self.member) <= 256
            or re.fullmatch(r"[A-Za-z0-9_./-]+\.xml", self.member) is None
            or any(part in {"", ".", ".."} for part in self.member.split("/"))
        ):
            raise ValueError("An explicit safe XML member name is required")


@dataclass(frozen=True, repr=False)
class GitHubJUnitReport:
    _payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(redact_for_output(self._payload))

    @property
    def exit_code(self) -> int:
        data = self._payload
        if data["collection_status"] == "error":
            return 2
        usable = (
            data["collection_status"] == "complete"
            and data["archive_binding"] == "matched"
            and data["artifact_run_match"] == "match"
            and data["revision_match"] == "match"
            and data["selected_attempt_status"] == "current"
            and data["junit"] is not None
            and data["junit"]["collection_status"] == "complete"
        )
        return 0 if usable else 1


def _read_archive(path: Path) -> bytes:
    try:
        if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
            raise _ArchiveError("archive_not_regular")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(path, flags), "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise _ArchiveError("archive_not_regular")
            contents = handle.read(MAX_ARCHIVE_BYTES + 1)
    except (OSError, ValueError) as exc:
        if isinstance(exc, _ArchiveError):
            raise
        raise _ArchiveError("archive_read_error") from None
    if len(contents) > MAX_ARCHIVE_BYTES:
        raise _ArchiveError("archive_limit_exceeded")
    return contents


def _inspect_archive(contents: bytes, member: str) -> JUnitReport:
    try:
        with zipfile.ZipFile(io.BytesIO(contents)) as archive:
            entries = archive.infolist()
            if len(entries) != 1 or entries[0].filename != member or entries[0].orig_filename != member:
                raise _ArchiveError("archive_member_mismatch")
            entry = entries[0]
            mode = stat.S_IFMT(entry.external_attr >> 16)
            if (
                entry.is_dir()
                or entry.external_attr & 0x10
                or mode not in {0, stat.S_IFREG}
                or entry.flag_bits & (1 | 64)
                or entry.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
            ):
                raise _ArchiveError("unsupported_archive_member")
            if entry.file_size > MAX_REPORT_BYTES:
                raise _ArchiveError("report_limit_exceeded")
            with archive.open(entry) as handle:
                xml = handle.read(MAX_REPORT_BYTES + 1)
            if len(xml) > MAX_REPORT_BYTES:
                raise _ArchiveError("report_limit_exceeded")
            if len(xml) != entry.file_size:
                raise _ArchiveError("invalid_archive")
    except (OSError, ValueError, RuntimeError, EOFError, zipfile.BadZipFile, NotImplementedError, zlib.error) as exc:
        if isinstance(exc, _ArchiveError):
            raise
        raise _ArchiveError("invalid_archive") from None
    return _parse(xml)


def _required(data: dict[str, Any], key: str) -> Any:
    if key not in data or data[key] is None:
        raise _MissingMetadata("metadata_incomplete")
    return data[key]


def _object(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError("Invalid metadata object")
    return value


def _revision(value: object) -> str:
    if type(value) is not str or not _SHA.fullmatch(value):
        raise ValueError("Invalid metadata revision")
    return value


def _run(payload: dict[str, Any]) -> dict[str, Any]:
    repository = _object(_required(payload, "repository"))
    head_repository = _object(_required(payload, "head_repository"))
    status = _required(payload, "status")
    if "conclusion" not in payload:
        raise _MissingMetadata("metadata_incomplete")
    conclusion = payload["conclusion"]
    event = _required(payload, "event")
    if (
        type(status) is not str
        or status not in _STATES
        or (conclusion is not None and (type(conclusion) is not str or conclusion not in _CONCLUSIONS))
        or (status != "completed" and conclusion is not None)
        or type(event) is not str
        or re.fullmatch(r"[a-z_]{1,64}", event) is None
    ):
        raise ValueError("Unsupported run metadata")
    return {
        "id": _id(_required(payload, "id")),
        "repository_id": _id(_required(repository, "id")),
        "head_repository_id": _id(_required(head_repository, "id")),
        "workflow_id": _id(_required(payload, "workflow_id")),
        "provider_head_sha": _revision(_required(payload, "head_sha")),
        "attempt": _id(_required(payload, "run_attempt")),
        "event": event,
        "status": status,
        "conclusion": conclusion,
    }


def _artifact(payload: dict[str, Any]) -> dict[str, Any]:
    run = _object(_required(payload, "workflow_run"))
    digest = payload.get("digest")
    if digest is not None and (type(digest) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None):
        raise ValueError("Unsupported artifact digest")
    size, expired = _required(payload, "size_in_bytes"), _required(payload, "expired")
    if type(size) is not int or not 0 <= size <= _MAX_ID or type(expired) is not bool:
        raise ValueError("Invalid artifact metadata")
    return {
        "id": _id(_required(payload, "id")),
        "run_id": _id(_required(run, "id")),
        "repository_id": _id(_required(run, "repository_id")),
        "head_repository_id": _id(_required(run, "head_repository_id")),
        "provider_head_sha": _revision(_required(run, "head_sha")),
        "digest": digest,
        "size_in_bytes": size,
        "expired": expired,
    }


def _collect(request: JUnitArtifactRequest, token: str | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    client = _Client(token)
    base = f"/repos/{request.repository}"
    repository, _ = client.get(base)
    repository_id = _id(_required(repository, "id"))
    name = _required(repository, "full_name")
    if type(name) is not str or name.lower() != request.repository.lower():
        raise GitHubCollectionError("scope_mismatch")
    run_path = f"{base}/actions/runs/{request.run_id}"
    attempt_path = f"{run_path}/attempts/{request.attempt}"
    artifact_path = f"{base}/actions/artifacts/{request.artifact_id}"
    run = _run(client.get(run_path)[0])
    attempt = _run(client.get(attempt_path)[0])
    artifact = _artifact(client.get(artifact_path)[0])
    if artifact != _artifact(client.get(artifact_path)[0]):
        raise GitHubCollectionError("run_changed")
    if attempt != _run(client.get(attempt_path)[0]) or run != _run(client.get(run_path)[0]):
        raise GitHubCollectionError("run_changed")
    if (
        run["id"] != request.run_id
        or run["repository_id"] != repository_id
        or attempt["id"] != request.run_id
        or attempt["attempt"] != request.attempt
        or artifact["id"] != request.artifact_id
        or any(
            attempt[key] != run[key]
            for key in ("repository_id", "head_repository_id", "workflow_id", "provider_head_sha", "event")
        )
        or (request.attempt == run["attempt"] and attempt != run)
        or request.attempt > run["attempt"]
    ):
        raise GitHubCollectionError("scope_mismatch")
    return run, attempt, artifact


def inspect_github_junit(
    path: Path,
    *,
    request: JUnitArtifactRequest,
    token: str | None = None,
) -> GitHubJUnitReport:
    """Read one local ZIP and opt in to GitHub.com metadata requests.

    Hash and parse the same bounded buffer. Neither an archive name nor a
    provider run's current attempt authenticates the artifact-producing attempt.
    """
    data: dict[str, Any] = {
        "schema_version": "1.0",
        "kind": "github_junit_association",
        "request": {
            "repository": request.repository,
            "run_id": request.run_id,
            "attempt": request.attempt,
            "artifact_id": request.artifact_id,
            "revision": request.revision,
            "member": request.member,
        },
        "collection_status": "incomplete",
        "metadata_source": None,
        "archive_binding": "unknown",
        "artifact_run_match": "unknown",
        "revision_match": "unknown",
        "selected_attempt_status": "unknown",
        "artifact_attempt_binding": "unknown",
        "tested_revision_binding": "unknown",
        "execution_verification": "unverified",
        "policy_decision": "not_evaluated",
        "run": None,
        "attempt": None,
        "artifact": None,
        "junit": None,
        "issues": [],
    }
    try:
        contents = _read_archive(path)
        # Reject unsupported archives before making any network requests.
        junit = _inspect_archive(contents, request.member)
        if junit.collection_status == "error":
            raise _ArchiveError("invalid_junit_report")
        run, attempt, artifact = _collect(request, token)
        data.update(
            collection_status="complete",
            metadata_source="github.com-rest:2026-03-10:tls",
            run=run,
            attempt=attempt,
            artifact=artifact,
            selected_attempt_status="current" if request.attempt == run["attempt"] else "stale",
        )
        data["artifact_run_match"] = (
            "match"
            if (
                artifact["run_id"] == run["id"]
                and all(
                    artifact[key] == run[key] for key in ("repository_id", "head_repository_id", "provider_head_sha")
                )
            )
            else "mismatch"
        )
        data["revision_match"] = "match" if run["provider_head_sha"] == request.revision else "mismatch"
        if artifact["digest"] is None:
            data["collection_status"] = "incomplete"
            data["issues"].append("artifact_digest_unavailable")
        else:
            data["archive_binding"] = (
                "matched"
                if (
                    artifact["digest"] == "sha256:" + hashlib.sha256(contents).hexdigest()
                    and artifact["size_in_bytes"] == len(contents)
                )
                else "mismatched"
            )
        if artifact["expired"]:
            data["collection_status"] = "incomplete"
            data["issues"].append("artifact_expired")
        if data["archive_binding"] == "matched" and data["artifact_run_match"] == "match":
            data["junit"] = junit.to_dict()
            if junit.collection_status != "complete":
                data["collection_status"] = "incomplete"
    except _MissingMetadata:
        data["issues"].append("metadata_incomplete")
    except _ArchiveError as exc:
        data["collection_status"] = "error"
        data["issues"].append(str(exc))
    except GitHubCollectionError as exc:
        data["collection_status"] = "error"
        data["issues"].append(exc.code)
    except ValueError:
        data["collection_status"] = "error"
        data["issues"].append("invalid_response")
    return GitHubJUnitReport(data)
