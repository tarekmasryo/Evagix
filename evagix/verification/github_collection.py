"""Explicit, bounded collection of GitHub.com Actions metadata over verified TLS."""

from __future__ import annotations

import re
import ssl
import time
from dataclasses import dataclass, replace
from http.client import HTTPException
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from evagix import __version__
from evagix.verification._json import decode_object
from evagix.verification.contracts import ContractError, EvidenceBatch, SourceAssessment
from evagix.verification.github_actions import GitHubActionsScope, normalize_actions_attempt

_ORIGIN = "https://api.github.com"
_API_VERSION = "2026-03-10"
_SOCKET_TIMEOUT = 10.0
_ELAPSED_BUDGET = 30.0
_MAX_REQUESTS = 15
_MAX_RESPONSE_BYTES = 2_000_000
_MAX_TOTAL_BYTES = 8_000_000
_MAX_PAGES = 10
_PAGE_SIZE = 100
_CHUNK_SIZE = 65_536
_ERRORS = {
    "invalid_repository": "Use an explicit GitHub owner/repository name.",
    "invalid_token": "The optional GitHub credential has an invalid format.",
    "request_limit": "GitHub collection exceeded its request limit.",
    "response_limit": "A GitHub response exceeded its size limit.",
    "total_response_limit": "GitHub collection exceeded its total response size limit.",
    "time_budget": "GitHub collection exceeded its elapsed-time budget.",
    "unauthorized": "GitHub rejected the credential.",
    "forbidden": "GitHub denied access to the requested metadata.",
    "rate_limited": "GitHub rate-limited collection; retry later.",
    "not_found": "GitHub metadata was not found or is not accessible.",
    "redirect_refused": "GitHub redirected the request; use the current repository name.",
    "http_error": "GitHub returned an unsuccessful HTTP response.",
    "transport_error": "The GitHub HTTPS request failed.",
    "invalid_response": "GitHub returned invalid or unsupported metadata.",
    "pagination_mismatch": "GitHub pagination did not match the selected attempt.",
    "scope_mismatch": "GitHub metadata does not match the selected collection scope.",
    "run_changed": "The selected GitHub run changed during collection; collect again.",
}


class GitHubCollectionError(ValueError):
    """A classified error whose message never contains credentials or payloads."""

    def __init__(self, code: str) -> None:
        if code not in _ERRORS:
            raise ValueError("Unknown GitHub collection error")
        self.code = code
        super().__init__(_ERRORS[code])


@dataclass(frozen=True, repr=False)
class CollectedEvidence:
    batch: EvidenceBatch
    assessment: SourceAssessment


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _repository_name(value: object) -> str:
    if (
        type(value) is not str
        or re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}", value) is None
        or value.split("/")[1] in {".", ".."}
    ):
        raise GitHubCollectionError("invalid_repository")
    return value


def _validate_token(token: object) -> None:
    if token is not None and (
        type(token) is not str or not 1 <= len(token) <= 4096 or any(not 33 <= ord(c) <= 126 for c in token)
    ):
        raise GitHubCollectionError("invalid_token")


def _http_error(status: int, headers: Any) -> GitHubCollectionError:
    headers = headers or {}
    if status == 429 or (status == 403 and (headers.get("X-RateLimit-Remaining") == "0" or headers.get("Retry-After"))):
        return GitHubCollectionError("rate_limited")
    code = {401: "unauthorized", 403: "forbidden", 404: "not_found"}.get(status, "http_error")
    if 300 <= status < 400:
        code = "redirect_refused"
    return GitHubCollectionError(code)


class _Client:
    def __init__(self, token: str | None) -> None:
        _validate_token(token)
        self._token = token
        self._deadline = time.monotonic() + _ELAPSED_BUDGET
        self._requests = 0
        self._bytes = 0
        self._opener = build_opener(ProxyHandler({}), _NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))

    def _remaining(self) -> float:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise GitHubCollectionError("time_budget")
        return remaining

    def get(self, path: str) -> tuple[dict[str, Any], str]:
        if self._requests >= _MAX_REQUESTS:
            raise GitHubCollectionError("request_limit")
        remaining = self._remaining()
        self._requests += 1
        request = Request(
            _ORIGIN + path,
            headers={
                "Accept": "application/vnd.github+json",
                "Accept-Encoding": "identity",
                "User-Agent": f"Evagix/{__version__}",
                "X-GitHub-Api-Version": _API_VERSION,
                "Cache-Control": "no-cache",
            },
            method="GET",
        )
        if self._token is not None:
            request.add_unredirected_header("Authorization", "Bearer " + self._token)
        try:
            with self._opener.open(request, timeout=min(_SOCKET_TIMEOUT, remaining)) as response:
                if response.status != 200:
                    raise _http_error(response.status, response.headers)
                if response.geturl() != request.full_url:
                    raise GitHubCollectionError("redirect_refused")
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type not in {"application/json", "application/vnd.github+json"}:
                    raise GitHubCollectionError("invalid_response")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise GitHubCollectionError("invalid_response")
                length = response.headers.get("Content-Length")
                if length is not None:
                    if not length.isascii() or not length.isdecimal():
                        raise GitHubCollectionError("invalid_response")
                    if len(length) > 10 or int(length) > _MAX_RESPONSE_BYTES:
                        raise GitHubCollectionError("response_limit")
                chunks = []
                size = 0
                while True:
                    self._remaining()
                    chunk = response.read1(min(_CHUNK_SIZE, _MAX_RESPONSE_BYTES + 1 - size))
                    self._remaining()
                    size += len(chunk)
                    self._bytes += len(chunk)
                    if size > _MAX_RESPONSE_BYTES:
                        raise GitHubCollectionError("response_limit")
                    if self._bytes > _MAX_TOTAL_BYTES:
                        raise GitHubCollectionError("total_response_limit")
                    if not chunk:
                        break
                    chunks.append(chunk)
                if length is not None and size != int(length):
                    raise GitHubCollectionError("invalid_response")
                links = ", ".join(response.headers.get_all("Link", []))
                if len(links) > 8192:
                    raise GitHubCollectionError("pagination_mismatch")
                return decode_object(b"".join(chunks).decode("utf-8")), links
        except HTTPError as exc:
            error = _http_error(exc.code, exc.headers)
            exc.close()
            raise error from None
        except (URLError, OSError, HTTPException):
            raise GitHubCollectionError("transport_error") from None
        except (ContractError, UnicodeError, RecursionError):
            raise GitHubCollectionError("invalid_response") from None


def _has_next(header: str, path: str, next_page: int) -> bool:
    found = False
    if not header:
        return False
    for part in header.split(","):
        match = re.fullmatch(r'\s*<([^<>]+)>\s*;\s*rel="([A-Za-z ]+)"\s*', part)
        if match is None:
            raise GitHubCollectionError("pagination_mismatch")
        if "next" not in match[2].split():
            continue
        if found:
            raise GitHubCollectionError("pagination_mismatch")
        found = True
        try:
            url = urlsplit(match[1])
            query = parse_qsl(url.query, strict_parsing=True)
        except ValueError:
            raise GitHubCollectionError("pagination_mismatch") from None
        if (
            url.scheme != "https"
            or url.netloc != "api.github.com"
            or url.path.lower() != path.lower()
            or url.fragment
            or len(query) != 2
            or dict(query) != {"per_page": str(_PAGE_SIZE), "page": str(next_page)}
        ):
            raise GitHubCollectionError("pagination_mismatch")
    return found


def _signature(run: dict[str, Any], scope: GitHubActionsScope) -> tuple[Any, ...]:
    try:
        normalize_actions_attempt(run, (), scope=scope)
    except ContractError:
        raise GitHubCollectionError("scope_mismatch") from None
    status, conclusion = run.get("status"), run.get("conclusion")
    if (
        type(status) is not str
        or status not in {"queued", "in_progress", "completed", "waiting", "pending", "requested"}
        or "conclusion" not in run
        or (conclusion is not None and (type(conclusion) is not str or len(conclusion) > 64))
        or (status != "completed" and conclusion is not None)
    ):
        raise GitHubCollectionError("invalid_response")
    return (
        run["id"],
        run["repository"]["id"],
        run["head_repository"]["id"],
        run["workflow_id"],
        run["head_sha"],
        run["run_attempt"],
        run["event"],
        status,
        conclusion,
    )


def collect_actions_attempt(
    repository: str,
    *,
    scope: GitHubActionsScope,
    token: str | None = None,
) -> CollectedEvidence:
    """Collect the explicitly selected current push attempt from GitHub.com.

    The assessment authenticates the source of provider metadata, not the
    caller's policy, actual checkout, test execution, or task completion.
    """
    repository = _repository_name(repository)
    if not isinstance(scope, GitHubActionsScope):
        raise ContractError("Invalid GitHub collection scope")
    client = _Client(token)
    repo_path = f"/repos/{repository}"
    repo, _ = client.get(repo_path)
    if (
        type(repo.get("id")) is not int
        or repo["id"] != scope.repository_id
        or type(repo.get("full_name")) is not str
        or repo["full_name"].lower() != repository.lower()
    ):
        raise GitHubCollectionError("scope_mismatch")
    run_path = f"{repo_path}/actions/runs/{scope.run_id}"
    attempt_path = f"{run_path}/attempts/{scope.attempt}"
    jobs_path = f"{attempt_path}/jobs"
    before, _ = client.get(run_path)
    signature = _signature(before, scope)
    attempt, _ = client.get(attempt_path)
    if _signature(attempt, scope) != signature:
        raise GitHubCollectionError("run_changed")
    pages: list[object] = []
    more = True
    for page_number in range(1, _MAX_PAGES + 1):
        page, link = client.get(f"{jobs_path}?per_page={_PAGE_SIZE}&page={page_number}")
        pages.append(page)
        more = _has_next(link, jobs_path, page_number + 1)
        # Validate every prefix before issuing another request.
        try:
            normalize_actions_attempt(before, tuple(pages), scope=replace(scope, pagination_complete=False))
        except ContractError:
            raise GitHubCollectionError("invalid_response") from None
        if not more:
            break
    after_attempt, _ = client.get(attempt_path)
    after_run, _ = client.get(run_path)
    try:
        unchanged = _signature(after_attempt, scope) == signature and _signature(after_run, scope) == signature
    except GitHubCollectionError:
        raise GitHubCollectionError("run_changed") from None
    if not unchanged:
        raise GitHubCollectionError("run_changed")
    complete = not more and before["status"] == "completed"
    batch = normalize_actions_attempt(before, tuple(pages), scope=replace(scope, pagination_complete=complete))
    assessment = SourceAssessment(batch.digest(), "verified", f"github.com-rest:{_API_VERSION}:tls")
    return CollectedEvidence(batch, assessment)
