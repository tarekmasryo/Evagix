from __future__ import annotations

from pathlib import Path

from evagix.classification import classify_project
from evagix.model import RepoFacts
from evagix.profiles import infer_profiles
from evagix.safety import REPOSITORY_PATH_POLICY
from evagix.scanner_utils import _normalize_ignored_paths
from evagix.scanning.base import _apply_config_profiles, _infer_root_name, _scan_top_level
from evagix.scanning.command_evidence import _scan_node_projects
from evagix.scanning.infrastructure import _scan_ci, _scan_docker, _scan_infrastructure_files, _scan_make_like
from evagix.scanning.project_evidence import (
    _derive_fallback_commands,
    _derive_warnings,
    _scan_ecosystem_registry,
    _scan_folders,
    _scan_notebooks,
    _scan_polyglot_projects,
    _scan_source_imports,
)
from evagix.scanning.python_evidence import _scan_python


def scan_repo(root: Path, ignored_paths: list[str] | None = None) -> RepoFacts:
    """Return repository facts derived from local files and lightweight built-in inference.

    This scanner collects filesystem and ecosystem evidence and applies only
    low-level inferred profile hints needed to describe the repository shape.
    It does not apply the full Evagix CLI config contract such as explicit
    command overrides, custom rules, README ignore settings, or selected
    command profiles. CLI commands perform that enrichment through the shared
    facts loader before validation and rendering.
    """
    root = REPOSITORY_PATH_POLICY.normalize(root)
    ignored = _normalize_ignored_paths(ignored_paths)
    warnings: list[str] = []
    facts = RepoFacts(root_name=_infer_root_name(root, warnings))
    facts.warnings.extend(warnings)
    _scan_top_level(root, facts, ignored)
    _scan_python(root, facts, ignored)
    _scan_node_projects(root, facts, ignored)
    _scan_polyglot_projects(root, facts, ignored)
    _scan_infrastructure_files(root, facts, ignored)
    _scan_docker(root, facts, ignored)
    _scan_make_like(root, facts, ignored)
    _scan_ci(root, facts, ignored)
    _scan_source_imports(root, facts, ignored)
    _scan_notebooks(root, facts, ignored)
    _scan_folders(root, facts, ignored)
    _scan_ecosystem_registry(root, facts, ignored)
    _derive_fallback_commands(facts)
    _derive_warnings(facts)
    facts.active_profiles = infer_profiles(facts)
    _apply_config_profiles(root, facts)
    facts.classification = classify_project(root, facts).to_dict()
    return facts
