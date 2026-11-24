from __future__ import annotations

import io
import json
import ssl
from copy import deepcopy
from email.message import Message
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

import pytest

from evagix.verification import CheckRequest, CheckSubject, ContractError, evaluate_check
from evagix.verification import github_collection as collection
from evagix.verification._json import decode_object
from evagix.verification.github_actions import GitHubActionsScope

REVISION = "a" * 40
SCOPE = GitHubActionsScope(10, 20, 2)
REPO = "example/project"
BASE = "https://api.github.com/repos/example/project"
JOBS = BASE + "/actions/runs/20/attempts/2/jobs"


def run(**changes):
    return {
        "id": 20,
        "repository": {"id": 10},
        "head_repository": {"id": 10},
        "workflow_id": 30,
        "head_sha": REVISION,
        "run_attempt": 2,
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        **changes,
    }


def job(identifier=40, **changes):
    return {
        "id": identifier,
        "run_id": 20,
        "run_attempt": 2,
        "head_sha": REVISION,
        "status": "completed",
        "conclusion": "success",
        **changes,
    }


def page(*jobs, total=None):
    return {"total_count": len(jobs) if total is None else total, "jobs": list(jobs)}


def request():
    return CheckRequest(
        CheckSubject("github:repository:10", REVISION, "commit", "github-actions:workflow:30", "github-actions:job:40"),
        "20",
        2,
    )


class Response:
    def __init__(self, payload, *, headers=None, status=200, url=None):
        self.body = io.BytesIO(payload if isinstance(payload, bytes) else json.dumps(payload).encode())
        self.headers = Message()
        self.headers["Content-Type"] = "application/json"
        for name, value in (headers or {}).items():
            self.headers.replace_header(name, value) if name in self.headers else self.headers.add_header(name, value)
        self.status = status
        self.url = url
        self.closed = False
        self.read_calls = 0
        self.on_read = lambda: None

    def read1(self, size):
        self.read_calls += 1
        self.on_read()
        return self.body.read(size)

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True
        self.body.close()


class Transport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.handlers = ()

    def build(self, *handlers):
        self.handlers = handlers
        return self

    def open(self, request, *, timeout):
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if response.url is None:
            response.url = request.full_url
        return response


def install(monkeypatch, responses):
    transport = Transport(responses)
    monkeypatch.setattr(collection, "build_opener", transport.build)
    return transport


def snapshots(*pages, initial=None, attempt_before=None, attempt_after=None, final=None, repo=None):
    initial = initial or run()
    return [
        Response(repo or {"id": 10, "full_name": REPO}),
        Response(deepcopy(initial)),
        Response(attempt_before or deepcopy(initial)),
        *(pages or (Response(page(job())),)),
        Response(attempt_after or deepcopy(initial)),
        Response(final or deepcopy(initial)),
    ]


def result(collected):
    return evaluate_check(request(), collected.batch, assessment=collected.assessment)


@pytest.mark.parametrize("token", [None, "synthetic-token-marker"])
@pytest.mark.parametrize("conclusion,condition", [("success", "supported"), ("failure", "contradicted")])
def test_provider_outcome_is_collected_from_explicit_endpoints(monkeypatch, token, conclusion, condition):
    responses = snapshots(Response(page(job(conclusion=conclusion))), initial=run(conclusion="failure"))
    transport = install(monkeypatch, responses)
    collected = collection.collect_actions_attempt(REPO, scope=SCOPE, token=token)

    assert collected.batch.complete is True
    assert collected.assessment.batch_digest == collected.batch.digest()
    assert collected.assessment.verifier == "github.com-rest:2026-03-10:tls"
    assert result(collected).condition == condition
    assert result(collected).to_dict()["policy_decision"] == "not_evaluated"
    assert [req.full_url for req, _ in transport.requests] == [
        BASE,
        BASE + "/actions/runs/20",
        BASE + "/actions/runs/20/attempts/2",
        JOBS + "?per_page=100&page=1",
        BASE + "/actions/runs/20/attempts/2",
        BASE + "/actions/runs/20",
    ]
    for req, timeout in transport.requests:
        assert req.get_method() == "GET"
        assert req.headers["X-github-api-version"] == "2026-03-10"
        assert req.headers["Accept-encoding"] == "identity"
        assert "Authorization" not in req.headers
        assert req.unredirected_hdrs.get("Authorization") == ("Bearer " + token if token else None)
        assert 0 < timeout <= 10
    assert all(response.closed for response in responses)


def test_private_opener_ignores_proxies_and_requires_verified_tls(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://untrusted.invalid:8888")
    transport = install(monkeypatch, snapshots())
    collection.collect_actions_attempt(REPO, scope=SCOPE)
    proxy = next(h for h in transport.handlers if isinstance(h, ProxyHandler))
    https = next(h for h in transport.handlers if isinstance(h, HTTPSHandler))
    assert proxy.proxies == {}
    assert https._context.check_hostname is True
    assert https._context.verify_mode == ssl.CERT_REQUIRED
    assert any(isinstance(h, collection._NoRedirect) for h in transport.handlers)


def test_pr_api_version_is_explicit_without_changing_default_transport(monkeypatch):
    transport = install(monkeypatch, [Response({}), Response({})])
    collection._Client(None, api_version="2022-11-28").get("/repos/example/project")
    collection._Client(None).get("/repos/example/project")
    assert [req.headers["X-github-api-version"] for req, _ in transport.requests] == ["2022-11-28", "2026-03-10"]


def test_transport_rejects_unsupported_api_versions_before_network(monkeypatch):
    transport = install(monkeypatch, [])
    with pytest.raises(ValueError, match="Unsupported GitHub API version"):
        collection._Client(None, api_version="unsupported")
    assert transport.requests == []


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("destination", ["http://outside.invalid/", "https://outside.invalid/", BASE])
def test_redirect_handler_never_opens_a_replacement_request(monkeypatch, status, destination):
    opener = build_opener(ProxyHandler({}), collection._NoRedirect())

    def unexpected_open(*args, **kwargs):
        pytest.fail("Redirect followed")

    monkeypatch.setattr(opener, "open", unexpected_open)
    headers = Message()
    headers["Location"] = destination
    req = Request(BASE)
    req.add_unredirected_header("Authorization", "Bearer synthetic-token-marker")
    with pytest.raises(HTTPError):
        opener.error("http", req, io.BytesIO(), status, "redirect", headers)


@pytest.mark.parametrize(
    "repository",
    [
        "https://github.com/example/project",
        "a/b/c",
        "a/..",
        "a/.",
        "a/b?token=x",
        "a/b#x",
        "a/b\n",
        "a%2f/b",
        "-a/b",
        "a@host/b",
        None,
    ],
)
def test_invalid_repository_never_opens_transport(monkeypatch, repository):
    transport = install(monkeypatch, [])
    with pytest.raises(collection.GitHubCollectionError) as exc:
        collection.collect_actions_attempt(repository, scope=SCOPE)
    assert exc.value.code == "invalid_repository"
    assert transport.requests == []
    assert transport.handlers == ()


@pytest.mark.parametrize("token", ["", "contains space", "header\r\ninjection", "\u0627", "a" * 4097, 42])
def test_invalid_credentials_never_reach_transport(monkeypatch, token):
    transport = install(monkeypatch, [])
    with pytest.raises(collection.GitHubCollectionError) as exc:
        collection.collect_actions_attempt(REPO, scope=SCOPE, token=token)
    assert exc.value.code == "invalid_token"
    assert transport.requests == []


@pytest.mark.parametrize(
    "repo",
    [
        {"id": 11, "full_name": REPO},
        {"id": True, "full_name": REPO},
        {"id": 10, "full_name": "elsewhere/project"},
        {"id": 10},
    ],
)
def test_repository_name_must_resolve_to_requested_id(monkeypatch, repo):
    transport = install(monkeypatch, snapshots(repo=repo))
    with pytest.raises(collection.GitHubCollectionError) as exc:
        collection.collect_actions_attempt(REPO, scope=SCOPE)
    assert exc.value.code == "scope_mismatch"
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"run_attempt": 3},
        {"workflow_id": 31},
        {"head_sha": "b" * 40},
        {"conclusion": "failure"},
        {"status": "in_progress", "conclusion": None},
    ],
)
@pytest.mark.parametrize("which", ["attempt_before", "attempt_after", "final"])
def test_changed_snapshot_never_produces_assessment(monkeypatch, changes, which):
    transport = install(monkeypatch, snapshots(**{which: run(**changes)}))
    with pytest.raises(collection.GitHubCollectionError) as exc:
        collection.collect_actions_attempt(REPO, scope=SCOPE)
    assert exc.value.code in {"run_changed", "scope_mismatch"}
    assert len(transport.requests) <= 6


def test_missing_attempt_and_wrong_event_are_not_inferred(monkeypatch):
    for altered in (run(event="pull_request"), {k: v for k, v in run().items() if k != "run_attempt"}):
        install(monkeypatch, snapshots(initial=altered))
        with pytest.raises(collection.GitHubCollectionError) as exc:
            collection.collect_actions_attempt(REPO, scope=SCOPE)
        assert exc.value.code == "scope_mismatch"


@pytest.mark.parametrize("initial", [run(status="in_progress", conclusion=None), run(status="queued", conclusion=None)])
def test_unfinished_runs_force_incomplete_inventory_even_for_successful_job(monkeypatch, initial):
    install(monkeypatch, snapshots(initial=initial))
    collected = collection.collect_actions_attempt(REPO, scope=SCOPE)
    assert collected.assessment.verification == "verified"
    assert collected.batch.complete is False
    assert (result(collected).condition, result(collected).reason) == ("unverified", "incomplete_inventory")


@pytest.mark.parametrize("conclusion", ["skipped", "neutral", "cancelled", "timed_out", None])
def test_nondecisive_job_results_stay_unverified(monkeypatch, conclusion):
    install(monkeypatch, snapshots(Response(page(job(conclusion=conclusion)))))
    collected = collection.collect_actions_attempt(REPO, scope=SCOPE)
    assert result(collected).condition == "unverified"


def test_absent_selected_job_does_not_fall_back_to_other_success(monkeypatch):
    install(monkeypatch, snapshots(Response(page(job(41)))))
    assert result(collection.collect_actions_attempt(REPO, scope=SCOPE)).evidence_match == "mismatch"


def test_multiple_pages_and_current_attempt_are_collected_once(monkeypatch):
    link = f'<{JOBS}?page=2&per_page=100>; rel="next", <{JOBS}?page=2&per_page=100>; rel="last"'
    transport = install(
        monkeypatch, snapshots(Response(page(job(), total=2), headers={"Link": link}), Response(page(job(41), total=2)))
    )
    collected = collection.collect_actions_attempt(REPO, scope=SCOPE)
    assert len(collected.batch.records) == 2 and collected.batch.complete
    assert len(transport.requests) == 7
    assert transport.requests[4][0].full_url == JOBS + "?per_page=100&page=2"


@pytest.mark.parametrize(
    "link",
    [
        '<https://outside.invalid/jobs?page=2&per_page=100>; rel="next"',
        f'<{JOBS.replace("https:", "http:")}?page=2&per_page=100>; rel="next"',
        f'<{JOBS.replace("/attempts/2/", "/attempts/1/")}?page=2&per_page=100>; rel="next"',
        f'<{JOBS}?page=1&per_page=100>; rel="next"',
        f'<{JOBS}?page=2&per_page=100&page=2>; rel="next"',
        f'<{JOBS}?page=2&per_page=100#fragment>; rel="next"',
        f'<{JOBS}?page=2&per_page=100>; rel="next", <{JOBS}?page=2&per_page=100>; rel="next"',
        "malformed link",
    ],
)
def test_pagination_cannot_redirect_scope_or_repeat_pages(monkeypatch, link):
    transport = install(monkeypatch, snapshots(Response(page(job()), headers={"Link": link})))
    with pytest.raises(collection.GitHubCollectionError) as exc:
        collection.collect_actions_attempt(REPO, scope=SCOPE)
    assert exc.value.code == "pagination_mismatch"
    assert len(transport.requests) == 4


def test_missing_pages_are_incomplete_and_page_limit_reserves_final_checks(monkeypatch):
    install(monkeypatch, snapshots(Response(page(job(), total=2))))
    assert result(collection.collect_actions_attempt(REPO, scope=SCOPE)).reason == "incomplete_inventory"
    pages = [
        Response(page(job(40 + i), total=11), headers={"Link": f'<{JOBS}?page={i + 2}&per_page=100>; rel="next"'})
        for i in range(10)
    ]
    transport = install(monkeypatch, snapshots(*pages))
    collected = collection.collect_actions_attempt(REPO, scope=SCOPE)
    assert not collected.batch.complete
    assert len(collected.batch.records) == 10
    assert len(transport.requests) == 15
    assert result(collected).condition == "unverified"


@pytest.mark.parametrize(
    "second", [page(job(), total=2), page(job(41), total=3), page(job(41, run_attempt=1), total=2)]
)
def test_inconsistent_pages_stop_collection_before_assessment(monkeypatch, second):
    link = f'<{JOBS}?page=2&per_page=100>; rel="next"'
    transport = install(
        monkeypatch, snapshots(Response(page(job(), total=2), headers={"Link": link}), Response(second))
    )
    with pytest.raises(collection.GitHubCollectionError) as exc:
        collection.collect_actions_attempt(REPO, scope=SCOPE)
    assert exc.value.code == "invalid_response"
    assert len(transport.requests) == 5


@pytest.mark.parametrize(
    "status,headers,code",
    [
        (401, {}, "unauthorized"),
        (403, {}, "forbidden"),
        (404, {}, "not_found"),
        (429, {}, "rate_limited"),
        (403, {"X-RateLimit-Remaining": "0"}, "rate_limited"),
        (403, {"Retry-After": "30"}, "rate_limited"),
        (500, {}, "http_error"),
        (302, {}, "redirect_refused"),
    ],
)
def test_http_errors_are_classified_without_echoing_response_or_credentials(monkeypatch, status, headers, code):
    token = "synthetic-token-marker"
    error = HTTPError(BASE, status, token, headers, io.BytesIO(token.encode()))
    transport = install(monkeypatch, [error])
    with pytest.raises(collection.GitHubCollectionError) as exc:
        collection.collect_actions_attempt(REPO, scope=SCOPE, token=token)
    assert exc.value.code == code
    assert token not in str(exc.value) and token not in repr(exc.value)
    assert error.closed
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("synthetic-token-marker"),
        URLError("synthetic-token-marker"),
        ssl.SSLError("synthetic-token-marker"),
    ],
)
def test_transport_errors_never_fall_back_to_cached_success(monkeypatch, error):
    transport = install(monkeypatch, [error])
    with pytest.raises(collection.GitHubCollectionError) as exc:
        collection.collect_actions_attempt(REPO, scope=SCOPE)
    assert exc.value.code == "transport_error"
    assert "synthetic-token-marker" not in str(exc.value)
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "payload,headers,code",
    [
        (b'{"id":10,"id":11}', {}, "invalid_response"),
        (b'{"v":NaN}', {}, "invalid_response"),
        (b'{"v":1e9999}', {}, "invalid_response"),
        (b"[]", {}, "invalid_response"),
        (b"\xff", {}, "invalid_response"),
        (b"{}", {"Content-Type": "text/html"}, "invalid_response"),
        (b"{}", {"Content-Encoding": "gzip"}, "invalid_response"),
        (b"{}", {"Content-Length": "3"}, "invalid_response"),
        (b"{}", {"Content-Length": "bad"}, "invalid_response"),
        (b"{}", {"Content-Length": "2000001"}, "response_limit"),
        (b"{}", {"Link": "x" * 8193}, "pagination_mismatch"),
    ],
)
def test_response_boundaries_fail_closed_and_close_body(monkeypatch, payload, headers, code):
    response = Response(payload, headers=headers)
    install(monkeypatch, [response])
    with pytest.raises(collection.GitHubCollectionError) as exc:
        collection.collect_actions_attempt(REPO, scope=SCOPE)
    assert exc.value.code == code
    assert response.closed


@pytest.mark.parametrize(
    "limit,value,code",
    [
        ("_MAX_RESPONSE_BYTES", 10, "response_limit"),
        ("_MAX_TOTAL_BYTES", 10, "total_response_limit"),
        ("_MAX_REQUESTS", 2, "request_limit"),
    ],
)
def test_collection_resource_limits_are_enforced(monkeypatch, limit, value, code):
    monkeypatch.setattr(collection, limit, value)
    transport = install(monkeypatch, snapshots())
    with pytest.raises(collection.GitHubCollectionError) as exc:
        collection.collect_actions_attempt(REPO, scope=SCOPE)
    assert exc.value.code == code
    assert len(transport.requests) <= 2


def test_elapsed_budget_is_checked_during_chunked_reads(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(collection.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(collection, "_CHUNK_SIZE", 1)
    response = Response({"id": 10, "full_name": REPO})
    response.on_read = lambda: clock.__setitem__(0, clock[0] + 1)
    transport = install(monkeypatch, [response])
    with pytest.raises(collection.GitHubCollectionError) as exc:
        collection.collect_actions_attempt(REPO, scope=SCOPE)
    assert exc.value.code == "time_budget"
    assert response.read_calls == 30
    assert response.closed and len(transport.requests) == 1


@pytest.mark.parametrize(
    "text",
    [
        '{"x":1,"x":2}',
        '{"x":NaN}',
        '{"x":Infinity}',
        '{"x":-Infinity}',
        '{"x":1e9999}',
        '{"nested":{"x":1,"x":2}}',
        "null",
        "[1]",
        "{invalid",
    ],
)
def test_strict_json_boundary_rejects_ambiguous_or_nonfinite_objects(text):
    with pytest.raises(ContractError):
        decode_object(text)


def test_strict_json_accepts_finite_numbers_and_unicode():
    assert decode_object('{"value":1.25,"label":"العربية"}') == {"value": 1.25, "label": "العربية"}
