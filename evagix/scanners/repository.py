from __future__ import annotations

from pathlib import Path
from typing import Any

from evagix.model import RepoFacts
from evagix.scanner import scan_repo


def scan_repository(root: Path, ignored_paths: list[str] | None = None) -> RepoFacts:
    return scan_repo(root, ignored_paths=ignored_paths)


def repository_summary(facts: RepoFacts) -> dict[str, Any]:
    return {
        "name": facts.root_name,
        "languages": list(facts.languages),
        "frameworks": list(facts.frameworks),
        "commands": dict(facts.commands),
        "profiles": list(facts.active_profiles),
        "ci_workflows": list(facts.ci_workflows),
    }
