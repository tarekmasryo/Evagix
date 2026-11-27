"""Preview CI adapter for advisory reports bound to explicit Git commits."""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import NoReturn

from evagix.reference_drift import build_reference_drift_report, render_reference_drift_markdown
from evagix.reports.github_junit import render_github_junit_markdown
from evagix.reports.junit import render_junit_report_markdown
from evagix.reports.pr_checks import render_pr_checks_markdown
from evagix.safety import REPOSITORY_PATH_POLICY
from evagix.scanning.git_snapshot import GitSnapshot
from evagix.script_drift import build_script_drift_report, render_script_drift_markdown
from evagix.security.output import execute_with_redacted_output
from evagix.security.redaction import redact_sensitive_text
from evagix.verification._json import decode_object
from evagix.verification.contracts import ContractError
from evagix.verification.github_collection import GitHubCollectionError
from evagix.verification.github_junit import JUnitArtifactRequest, inspect_github_junit
from evagix.verification.github_pr_checks import _pull_url, collect_pr_checks
from evagix.verification.junit import read_junit_report
from evagix.verification.pr_expectations import CheckExpectations, compare_pr_checks, parse_expectations

_SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_EXPECTATIONS_BYTES = 65_536
_SUMMARY_BYTES = 950_000


class _SummaryError(ValueError):
    """A fixed diagnostic that does not contain repository or argument values."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _SummaryError("Invalid summary arguments; use --help for usage.")


def _commit(value: str) -> str:
    if not _SHA.fullmatch(value):
        raise argparse.ArgumentTypeError("A full lowercase commit ID is required.")
    return value


def _git_path(value: str) -> str:
    if (
        not 1 <= len(value) <= 1024
        or "\\" in value
        or ":" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or any(unicodedata.category(char) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for char in value)
    ):
        raise argparse.ArgumentTypeError("An explicit repository-relative Git path is required.")
    return value


def _positive(value: str) -> int:
    if re.fullmatch(r"[1-9][0-9]{0,18}", value) is None or int(value) > 2**63 - 1:
        raise argparse.ArgumentTypeError("A positive identifier is required.")
    return int(value)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="python -m evagix.pr_summary",
        description=(
            "Preview advisory PR summary for explicit committed revisions. Reads Git objects and contacts "
            "GitHub.com; never fetches objects, executes repository commands, or writes repository files. "
            "Exit 0 means complete collection and inspection, not check success or merge approval; "
            "exit 1 means incomplete evidence or unmatched/stale optional artifact linkage; "
            "exit 2 means invalid input or operational failure."
        ),
    )
    parser.add_argument("url", metavar="PR_URL", help="https://github.com/OWNER/REPO/pull/N")
    parser.add_argument("--repo", required=True, type=Path, help="Local repository containing the requested commits.")
    parser.add_argument("--base", required=True, type=_commit, help="Full immutable base commit ID.")
    parser.add_argument("--head", required=True, type=_commit, help="Full immutable head commit ID.")
    parser.add_argument(
        "--expectations",
        type=_git_path,
        metavar="GIT_PATH",
        help=(
            "Optional regular expectations file read only from the requested base commit. "
            "If omitted, report observed checks without evaluating required-check coverage."
        ),
    )
    junit_input = parser.add_mutually_exclusive_group()
    junit_input.add_argument(
        "--junit-report",
        type=Path,
        action="append",
        metavar="PATH",
        help=(
            "Optional local pytest JUnit XML file, relative to the caller's working directory. "
            "Specify once; source and revision remain unverified."
        ),
    )
    junit_input.add_argument(
        "--junit-archive",
        type=Path,
        action="append",
        metavar="PATH",
        help="Optional original local artifact ZIP. Requires explicit run, attempt and artifact IDs, each once.",
    )
    for option, description in (
        ("--junit-run-id", "Selected GitHub run ID in the PR repository."),
        ("--junit-attempt", "Explicit attempt within the selected run."),
        ("--junit-artifact-id", "Selected artifact ID in the PR repository."),
    ):
        parser.add_argument(option, type=_positive, action="append", metavar="N", help=description)
    parser.add_argument(
        "--junit-member",
        action="append",
        metavar="XML",
        help="Sole archive member, once; defaults to evagix-quality-junit.xml. Requires --junit-archive.",
    )
    return parser


def _junit_request(args: argparse.Namespace) -> JUnitArtifactRequest | None:
    required = (args.junit_archive, args.junit_run_id, args.junit_attempt, args.junit_artifact_id)
    if all(value is None for value in required) and args.junit_member is None:
        return None
    if (
        args.junit_report is not None
        or any(value is None or len(value) != 1 for value in required)
        or (args.junit_member is not None and len(args.junit_member) != 1)
    ):
        raise _SummaryError(
            "Select one JUnit archive with one run, attempt and artifact ID; do not mix local XML input."
        )
    try:
        repository, _ = _pull_url(args.url)
        return JUnitArtifactRequest(
            repository,
            args.junit_run_id[0],
            args.junit_attempt[0],
            args.junit_artifact_id[0],
            args.head,
            args.junit_member[0] if args.junit_member is not None else "evagix-quality-junit.xml",
        )
    except (ValueError, GitHubCollectionError):
        raise _SummaryError("Invalid JUnit association arguments; use --help for usage.") from None


def _read_expectations(git: GitSnapshot, base: str, path: str) -> CheckExpectations:
    entry = git.tree(base).get(path)
    if entry is None or not entry.regular:
        raise _SummaryError("Expectations must be a regular tracked file at the requested base commit.")
    return parse_expectations(decode_object(git.text(entry, limit=_EXPECTATIONS_BYTES)))


def _run(args: argparse.Namespace) -> tuple[str, int]:
    request = _junit_request(args)
    association = None
    junit = None
    if args.junit_report is not None:
        if len(args.junit_report) != 1:
            raise _SummaryError("Select exactly one local JUnit report.")
        junit = read_junit_report(args.junit_report[0])
        if junit.collection_status == "error":
            raise _SummaryError(
                "Unable to inspect the selected local JUnit report; use evagix junit-report PATH for details."
            )
    try:
        root = REPOSITORY_PATH_POLICY.normalize(args.repo)
        git = GitSnapshot(root)
        if git.resolve(args.base) != args.base or git.resolve(args.head) != args.head:
            raise _SummaryError("The requested object IDs must identify commits directly.")
        expectations = _read_expectations(git, args.base, args.expectations) if args.expectations is not None else None
        references = build_reference_drift_report(root, base=args.base, head=args.head)
        scripts = build_script_drift_report(root, base=args.base, head=args.head)
    except _SummaryError:
        raise
    except (OSError, RuntimeError, ValueError):
        if args.expectations is None:
            raise _SummaryError(
                "Unable to inspect committed inputs; check local history and repository data."
            ) from None
        raise _SummaryError(
            "Unable to inspect committed inputs; check local history and the bounded UTF-8 expectations file."
        ) from None

    if request is not None:
        association = inspect_github_junit(
            args.junit_archive[0], request=request, token=os.environ.get("EVAGIX_GITHUB_TOKEN")
        )
        if association.exit_code == 2:
            raise _SummaryError(
                "Unable to inspect the selected JUnit association; use evagix junit-github for details."
            )
    try:
        checks = collect_pr_checks(args.url, token=os.environ.get("EVAGIX_GITHUB_TOKEN"))
    except GitHubCollectionError as exc:
        raise _SummaryError(
            f"GitHub collection failed ({exc.code}); check access, PR availability, and retry."
        ) from None

    snapshot = checks.to_dict()
    if snapshot["base_sha"] != args.base or snapshot["head_sha"] != args.head:
        raise _SummaryError("The PR no longer matches the requested base and head commits; collect a new snapshot.")
    repository_match = head_repository_match = None
    if association is not None:
        run = association.to_dict()["run"]
        if run is not None:
            repository_match = run["repository_id"] == snapshot["repository_id"]
            if checks.head_repository_id is not None:
                head_repository_match = run["head_repository_id"] == checks.head_repository_id
    try:
        if expectations is None:
            payload = snapshot
            expectations_note = (
                "No expectations supplied; observed checks only. "
                "Required-check coverage is unknown; merge readiness is not evaluated."
            )
        else:
            payload = compare_pr_checks(checks, expectations).to_dict()
            expectations_note = (
                "Expectations were read from the base commit; this does not authenticate repository acceptance policy."
            )
        scope_note = (
            "All sections use the requested base and head commits. "
            if junit is None
            else "GitHub checks and repository sections use the requested base and head commits. "
            "The optional local JUnit section has no verified revision binding. "
        )
        junit_section = "\n\n" + render_junit_report_markdown(junit).rstrip() if junit is not None else ""
        if association is not None:
            scope_note = (
                "GitHub checks and repository sections use the requested base and head commits. "
                "The optional artifact section compares selected run metadata with the PR head; "
                "artifact-producing attempt and tested code remain unverified. "
            )
            junit_section = (
                "\n\n"
                + render_github_junit_markdown(
                    association, repository_match=repository_match, head_repository_match=head_repository_match
                ).rstrip()
            )
        output = redact_sensitive_text(
            "# Pull request review (advisory)\n\n"
            + scope_note
            + expectations_note
            + "\n\n"
            + render_pr_checks_markdown(payload, show_all=False).rstrip()
            + "\n\n"
            + render_reference_drift_markdown(references).rstrip()
            + "\n\n"
            + render_script_drift_markdown(scripts).rstrip()
            + junit_section
            + "\n"
        )
    except ContractError:
        raise _SummaryError("Unable to compare expectations with the collected repository and evidence.") from None
    except (UnicodeError, ValueError):
        raise _SummaryError(
            "Unable to render a bounded Markdown summary; inspect the individual JSON reports."
        ) from None
    if len(output.encode("utf-8")) > _SUMMARY_BYTES:
        raise _SummaryError("Combined summary exceeds the output limit; inspect the individual JSON reports.")
    complete = checks.complete and references.complete and scripts.complete
    if junit is not None:
        complete = complete and junit.collection_status == "complete"
    if association is not None:
        complete = (
            complete and association.exit_code == 0 and repository_match is True and head_repository_match is True
        )
    return output, 0 if complete else 1


def _main(argv: list[str] | None) -> int:
    try:
        output, status = _run(_parser().parse_args(argv))
    except _SummaryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(output, end="")
    return status


def main(argv: list[str] | None = None) -> int:
    """Run the opt-in summary behind the shared output-redaction boundary."""
    return execute_with_redacted_output(lambda: _main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
