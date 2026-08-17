from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from evagix.constants import DEFAULT_GITHUB_REF, DEFAULT_GITHUB_REPO


class EvagixSafetyError(ValueError):
    """Raised when user-provided paths or workflow inputs are unsafe."""


@dataclass(frozen=True)
class RepositoryPathPolicy:
    """Centralized repository-root validation for CLI commands.

    Evagix is a filesystem-aware governance tool. It should never silently
    create or inspect a missing repository path, and it should never treat a
    regular file as a repository root.
    """

    require_existing_directory: bool = True

    def normalize(self, root: Path) -> Path:
        normalized = Path(os.path.abspath(root))
        if self.require_existing_directory:
            self._ensure_existing_directory(normalized)
        try:
            return normalized.resolve(strict=self.require_existing_directory)
        except (OSError, RuntimeError) as exc:
            raise EvagixSafetyError(f"unable to resolve repository path: {root}") from exc

    @staticmethod
    def _ensure_existing_directory(root: Path) -> None:
        if not root.exists():
            raise EvagixSafetyError(f"repository path does not exist: {root}")
        if not root.is_dir():
            raise EvagixSafetyError(f"repository path is not a directory: {root}")


@dataclass(frozen=True)
class WorkflowInstallInputPolicy:
    """Validate and render install commands used by generated GitHub Actions.

    Values that are later embedded in `run:` steps are validated and shell-quoted.
    This avoids workflow command injection while still keeping generated CI files
    readable and deterministic.
    """

    repo_slug_re: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    ref_re: re.Pattern[str] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
    package_version_re: re.Pattern[str] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._!+~-]{0,127}$")

    def clean_github_repo_slug(self, repo: str) -> str:
        value = repo.strip()
        value = value.removeprefix("https://github.com/").removeprefix("http://github.com/").removesuffix(".git")
        if not self.repo_slug_re.fullmatch(value):
            raise EvagixSafetyError("repo must be a GitHub slug like owner/name")
        return value

    def clean_git_ref(self, ref: str) -> str:
        value = ref.strip() or "main"
        if ".." in value or not self.ref_re.fullmatch(value):
            raise EvagixSafetyError("ref contains unsafe characters")
        return value

    def clean_package_version(self, version: str | None) -> str | None:
        if version is None:
            return None
        value = version.strip()
        if not value or not self.package_version_re.fullmatch(value):
            raise EvagixSafetyError("package version contains unsafe characters")
        return value

    def install_command(
        self,
        install_mode: str,
        repo: str = DEFAULT_GITHUB_REPO,
        ref: str = DEFAULT_GITHUB_REF,
        package_version: str | None = None,
    ) -> str:
        if install_mode == "pypi":
            package = "evagix"
            clean_version = self.clean_package_version(package_version)
            if clean_version:
                package = f"{package}=={clean_version}"
            return f"python -m pip install {shlex.quote(package)}"
        if install_mode == "github":
            clean_repo = self.clean_github_repo_slug(repo)
            clean_ref = self.clean_git_ref(ref)
            package = f"git+https://github.com/{clean_repo}.git@{clean_ref}"
            return f"python -m pip install {shlex.quote(package)}"
        return "python -m pip install -e ."


@dataclass(frozen=True)
class GitRevisionPolicy:
    """Validate Git revisions accepted by changed-file and PR-risk commands.

    Git treats revision arguments that start with a dash as options. Evagix
    never passes refs through a shell, but validating here prevents Git option
    injection such as `--output=/tmp/file` being interpreted as a diff option.
    """

    ref_re: re.Pattern[str] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")

    def clean_ref(self, ref: str, *, field_name: str = "git ref") -> str:
        value = ref.strip()
        if not value:
            raise EvagixSafetyError(f"{field_name} must not be empty")
        if value.startswith("-") or ".." in value or not self.ref_re.fullmatch(value):
            raise EvagixSafetyError(f"{field_name} contains unsafe characters")
        return value


REPOSITORY_PATH_POLICY = RepositoryPathPolicy()
WORKFLOW_INPUT_POLICY = WorkflowInstallInputPolicy()
GIT_REVISION_POLICY = GitRevisionPolicy()
