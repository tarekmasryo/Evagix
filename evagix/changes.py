from __future__ import annotations

import subprocess
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from evagix.core.collections import unique_preserving_order
from evagix.core.text import escape_github_command_value
from evagix.safety import GIT_REVISION_POLICY
from evagix.security.output import redacted_text_output
from evagix.security.redaction import redact_sensitive_text
from evagix.utils import stable_json


@dataclass(frozen=True)
class ChangedFileRisk:
    path: str
    risk: str
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", redact_sensitive_text(self.path))
        object.__setattr__(self, "reason", redact_sensitive_text(self.reason))


@dataclass(frozen=True)
class ChangedReport:
    base: str
    files: list[ChangedFileRisk]
    required_gates: list[str]
    head: str = "HEAD"

    def __post_init__(self) -> None:
        object.__setattr__(self, "base", redact_sensitive_text(self.base))
        object.__setattr__(self, "head", redact_sensitive_text(self.head))
        object.__setattr__(self, "files", list(self.files))
        object.__setattr__(self, "required_gates", [redact_sensitive_text(item) for item in self.required_gates])

    @property
    def has_high_risk(self) -> bool:
        return any(item.risk == "HIGH" for item in self.files)


def build_changed_report(
    root: Path,
    base: str = "main",
    head: str = "HEAD",
    *,
    commands: Mapping[str, str] | None = None,
) -> ChangedReport:
    clean_base = GIT_REVISION_POLICY.clean_ref(base, field_name="base ref")
    clean_head = GIT_REVISION_POLICY.clean_ref(head, field_name="head ref")
    files = [_classify_changed_path(item) for item in _git_changed_files(root, clean_base, head=clean_head)]
    return ChangedReport(
        base=clean_base, files=files, required_gates=_required_gates(files, commands=commands), head=clean_head
    )


@redacted_text_output
def render_changed_text(report: ChangedReport) -> str:
    lines = [f"Changed files risk assessment against `{report.base}`:", ""]
    if not report.files:
        lines.append("No changed files detected.")
    for item in report.files:
        lines.append(f"  {item.risk:<6} {item.path:<45} — {item.reason}")
    lines.extend(["", "Required gates for this change set:"])
    for gate in report.required_gates:
        lines.append(f"  - {gate}")
    return "\n".join(lines).rstrip() + "\n"


def render_changed_json(report: ChangedReport) -> str:
    payload = {
        "schema_version": "1.0",
        "tool": "evagix",
        "base": report.base,
        "head": report.head,
        "files": [asdict(item) for item in report.files],
        "required_gates": report.required_gates,
        "has_high_risk": report.has_high_risk,
    }
    return stable_json(payload) + "\n"


@redacted_text_output
def render_changed_github_annotations(report: ChangedReport) -> str:
    lines: list[str] = []
    for item in report.files:
        level = "error" if item.risk == "HIGH" else "warning" if item.risk == "MEDIUM" else "notice"
        message = escape_github_command_value(f"{item.risk} risk changed file: {item.reason}")
        path = escape_github_command_value(item.path)
        lines.append(f"::{level} file={path},line=1,title=Evagix changed-file risk::{message}")
    if not lines:
        lines.append("::notice title=Evagix changed-file risk::No changed files detected")
    return "\n".join(lines) + "\n"


def _git_changed_files(root: Path, base: str, head: str = "HEAD") -> list[str]:
    clean_base = GIT_REVISION_POLICY.clean_ref(base, field_name="base ref")
    clean_head = GIT_REVISION_POLICY.clean_ref(head, field_name="head ref")
    candidates = (
        ["git", "diff", "--name-only", "-z", f"{clean_base}...{clean_head}", "--"],
        ["git", "diff", "--name-only", "-z", clean_base, clean_head, "--"],
    )
    last_error = ""
    for command in candidates:
        completed = _run_git(command, root)
        if completed.returncode == 0:
            changed = set(_nul_delimited_paths(completed.stdout))
            worktree = _run_git(["git", "diff", "--name-only", "-z"], root)
            if worktree.returncode == 0:
                changed.update(_nul_delimited_paths(worktree.stdout))
            staged = _run_git(["git", "diff", "--cached", "--name-only", "-z"], root)
            if staged.returncode == 0:
                changed.update(_nul_delimited_paths(staged.stdout))
            untracked = _run_git(["git", "ls-files", "--others", "--exclude-standard", "-z"], root)
            if untracked.returncode == 0:
                changed.update(_nul_delimited_paths(untracked.stdout))
            return sorted(changed)
        last_error = (completed.stderr or completed.stdout or "git diff failed").strip()
    raise RuntimeError(_format_changed_files_error(root, clean_base, clean_head, last_error))


def _nul_delimited_paths(output: str) -> list[str]:
    """Parse Git ``-z`` output without corrupting unusual file names.

    Git permits tabs and newlines in paths. NUL-delimited output is therefore
    the only unambiguous machine-readable form for changed-file discovery.
    """

    return [item for item in output.split("\0") if item]


def _format_changed_files_error(root: Path, base: str, head: str, git_error: str) -> str:
    message = f"Could not inspect changed files between {base!r} and {head!r}: {git_error}"
    hint = _missing_base_ref_hint(root, base)
    if hint:
        return f"{message}\n{hint}"
    return message


def _missing_base_ref_hint(root: Path, base: str) -> str | None:
    branches = _local_branch_names(root)
    if not branches:
        return None
    if base in branches:
        return None
    preferred = _preferred_branch_suggestion(base, branches)
    if preferred is not None:
        return f"Base ref `{base}` was not found. Detected local branch: {preferred}. Try: --base {preferred}"
    if len(branches) == 1:
        branch = branches[0]
        return f"Base ref `{base}` was not found. Detected local branch: {branch}. Try: --base {branch}"
    return f"Base ref `{base}` was not found. Available local branches: {', '.join(branches[:6])}."


def _preferred_branch_suggestion(base: str, branches: list[str]) -> str | None:
    branch_set = set(branches)
    if base == "main" and "master" in branch_set:
        return "master"
    if base == "master" and "main" in branch_set:
        return "main"
    if base.startswith("origin/"):
        local = base.removeprefix("origin/")
        if local in branch_set:
            return local
    return None


def _local_branch_names(root: Path) -> list[str]:
    completed = _run_git(["git", "branch", "--format=%(refname:short)"], root)
    if completed.returncode != 0:
        return []
    return sorted(item.strip().lstrip("* ") for item in completed.stdout.splitlines() if item.strip())


def _run_git(command: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    try:
        # POSIX Git paths are byte sequences. Render undecodable bytes with a
        # replacement marker so reports remain valid text instead of crashing.
        return subprocess.run(
            command,
            cwd=root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Git command timed out while inspecting changed files.") from exc
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Git executable was not found. Install Git or run Evagix PR/change review in an environment with Git available."
        ) from exc
    except OSError as exc:
        raise RuntimeError(f"Could not run Git command {' '.join(command)!r}: {exc}") from exc


def _classify_changed_path(path: str) -> ChangedFileRisk:
    normalized = path.replace("\\", "/").strip("/")
    lower = normalized.lower()
    if not normalized:
        return ChangedFileRisk(path=path, risk="LOW", reason="empty path")
    # Non-executable documentation, tests, and examples remain low-risk even
    # when their paths describe sensitive concepts such as auth, migrations,
    # or deployment. Operational paths are evaluated only after this context.
    if _matches_prefix(lower, LOW_RISK_PREFIXES) or _matches_suffix(lower, LOW_RISK_SUFFIXES):
        return ChangedFileRisk(path=normalized, risk="LOW", reason="documentation, tests, or examples")
    if (
        _matches_prefix(lower, HIGH_RISK_PREFIXES)
        or _matches_name(lower, HIGH_RISK_NAMES)
        or _matches_segment(lower, HIGH_RISK_SEGMENTS)
    ):
        return ChangedFileRisk(path=normalized, risk="HIGH", reason=_high_risk_reason(lower))
    if _matches_suffix(lower, MEDIUM_RISK_SUFFIXES) or _matches_name(lower, MEDIUM_RISK_NAMES):
        return ChangedFileRisk(path=normalized, risk="MEDIUM", reason="project configuration or package metadata")
    return ChangedFileRisk(path=normalized, risk="MEDIUM", reason="source or unclassified project file")


def _required_gates(files: list[ChangedFileRisk], *, commands: Mapping[str, str] | None = None) -> list[str]:
    gates = ["evagix check"]
    if not files:
        return gates
    risks = {item.risk for item in files}
    paths = [item.path.lower() for item in files]
    if any(path.endswith(".py") for path in paths):
        gates.extend(_python_validation_gates(commands))
    if any(path.startswith("tests/") for path in paths):
        gates.append("pytest")
    if "HIGH" in risks:
        gates.extend(["evagix doctor", "human approval"])
    if any(path.startswith(".github/workflows/") for path in paths):
        gates.extend(["workflow review", "evagix doctor"])
    return unique_preserving_order(gates)


def _python_validation_gates(commands: Mapping[str, str] | None = None) -> list[str]:
    configured = commands or {}
    return [
        configured.get("lint", "ruff check ."),
        configured.get("typecheck", "mypy ."),
        configured.get("test", "pytest"),
    ]


def _high_risk_reason(path: str) -> str:
    if path.startswith(".github/workflows/"):
        return "CI workflow can execute shell commands"
    if path in {"pyproject.toml", "setup.py", "setup.cfg"} or path.endswith("lock"):
        return "dependency, build, or package metadata change"
    if _matches_segment(path, MIGRATION_SEGMENTS):
        return "database migration path"
    if _matches_segment(path, DEPLOYMENT_SEGMENTS) or _matches_segment(path, SECURITY_SENSITIVE_SEGMENTS):
        return "security, auth, billing, permissions, or deployment-sensitive path"
    if path.endswith(("dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")):
        return "container or runtime orchestration change"
    if ".env" in path or "secret" in path or "private" in path:
        return "secret-bearing or environment-sensitive path"
    return "high-risk repository path"


def _matches_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path.startswith(prefix) for prefix in prefixes)


def _matches_suffix(path: str, suffixes: tuple[str, ...]) -> bool:
    return any(path.endswith(suffix) for suffix in suffixes)


def _matches_name(path: str, names: tuple[str, ...]) -> bool:
    return path in names or any(path.endswith(f"/{name}") for name in names)


def _matches_segment(path: str, segments: tuple[str, ...]) -> bool:
    parts = tuple(part for part in path.split("/") if part)
    return any(part in segments for part in parts)


HIGH_RISK_PREFIXES = (
    ".github/workflows/",
    "migrations/",
    "alembic/",
    "auth/",
    "security/",
    "infra/",
    "deploy/",
)
MIGRATION_SEGMENTS = (
    "migrations",
    "alembic",
)
DEPLOYMENT_SEGMENTS = (
    "infra",
    "infrastructure",
    "deploy",
    "deployment",
    "terraform",
    "k8s",
    "kubernetes",
)
SECURITY_SENSITIVE_SEGMENTS = (
    "auth",
    "security",
    "permissions",
    "permission",
    "jwt",
    "token",
    "tokens",
    "billing",
    "payment",
    "payments",
    "secret",
    "secrets",
)
HIGH_RISK_SEGMENTS = MIGRATION_SEGMENTS + DEPLOYMENT_SEGMENTS + SECURITY_SENSITIVE_SEGMENTS

HIGH_RISK_NAMES = (
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "requirements-dev.txt",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "uv.lock",
    "poetry.lock",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    ".env",
    ".env.local",
    "auth.py",
    "security.py",
    "permissions.py",
    "permission.py",
    "jwt.py",
    "token.py",
    "tokens.py",
    "billing.py",
    "payment.py",
    "payments.py",
)
MEDIUM_RISK_NAMES = (
    "evagix.toml",
    ".pre-commit-config.yaml",
    "tox.ini",
    "mypy.ini",
    "ruff.toml",
)
MEDIUM_RISK_SUFFIXES = (".toml", ".ini", ".cfg", ".yaml", ".yml", ".json")
LOW_RISK_PREFIXES = ("docs/", "tests/", "examples/")
LOW_RISK_SUFFIXES = (".md", ".rst", ".txt")
