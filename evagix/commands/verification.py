"""Explicit network-enabled verification of a caller-selected GitHub check."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from evagix.core.io import safe_read_text_result
from evagix.utils import stable_json
from evagix.verification._json import decode_object
from evagix.verification.checks import evaluate_check
from evagix.verification.contracts import CheckRequest, ContractError, parse_request
from evagix.verification.github_actions import GitHubActionsScope
from evagix.verification.github_collection import GitHubCollectionError, collect_actions_attempt

_MAX_REQUEST_CHARS = 65_536
_MAX_GITHUB_ID = 2**63 - 1


def _github_id(value: str, prefix: str = "") -> int:
    match = re.fullmatch(re.escape(prefix) + r"([1-9][0-9]*)", value)
    if match is None or int(match[1]) > _MAX_GITHUB_ID:
        raise ContractError("Invalid GitHub identifier")
    return int(match[1])


def _github_scope(request: CheckRequest) -> GitHubActionsScope:
    if request.subject.subject_kind != "commit":
        raise ContractError("Unsupported GitHub subject kind")
    _github_id(request.subject.workflow, "github-actions:workflow:")
    _github_id(request.subject.job, "github-actions:job:")
    return GitHubActionsScope(
        repository_id=_github_id(request.subject.repository, "github:repository:"),
        run_id=_github_id(request.run_id),
        attempt=request.attempt,
    )


def _cmd_verify_check(request_path: Path, repository: str, output_format: str) -> int:
    try:
        contents = safe_read_text_result(request_path, max_chars=_MAX_REQUEST_CHARS)
    except (OSError, UnicodeError, ValueError):
        print("ERROR: Unable to read request file as UTF-8.", file=sys.stderr)
        return 2
    if contents.truncated:
        print("ERROR: Request file exceeds 65536 characters.", file=sys.stderr)
        return 2
    try:
        request = parse_request(decode_object(contents.text))
        scope = _github_scope(request)
    except ContractError:
        print("ERROR: Request must be a valid GitHub commit check request.", file=sys.stderr)
        return 2

    try:
        collected = collect_actions_attempt(repository, scope=scope, token=os.environ.get("EVAGIX_GITHUB_TOKEN"))
        result = evaluate_check(request, collected.batch, assessment=collected.assessment)
    except GitHubCollectionError as exc:
        print(f"ERROR: {exc} ({exc.code})", file=sys.stderr)
        return 2
    except ContractError:
        print("ERROR: GitHub evidence could not be evaluated.", file=sys.stderr)
        return 2

    if output_format == "json":
        print(stable_json(result.to_dict(), redact=False))
    else:
        print(f"GitHub-reported check result: {result.condition}")
        print(f"Reason: {result.reason}")
        print(f"Repository ID: {request.subject.repository}")
        print(f"Revision: {request.subject.revision}")
        print(f"Workflow ID: {request.subject.workflow}")
        print(f"Job ID: {request.subject.job}")
        print(f"Run: {request.run_id}; attempt: {request.attempt}")
        print(f"Source verification: {result.source_verification}")
        print(f"Inventory: {result.completeness}; evidence match: {result.evidence_match}")
        print("Scope: Caller-selected check; provider-reported metadata only.")
        print("Policy decision: not_evaluated")
    return 0 if result.condition == "supported" else 1
