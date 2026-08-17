from __future__ import annotations

import sys
from pathlib import Path

from evagix.config import EvagixConfig, load_config, merge_profiles, selected_targets
from evagix.model import RepoFacts
from evagix.profiles import normalize_profiles
from evagix.renderers import TARGETS
from evagix.safety import REPOSITORY_PATH_POLICY, EvagixSafetyError
from evagix.scanner import scan_repo
from evagix.scanning.shared import _set_command
from evagix.security.redaction import redact_sensitive_text
from evagix.utils import (
    resolve_output_path,
)
from evagix.validators import (
    DoctorReport,
    apply_config_policy,
    doctor_repo,
)


def _normalize_root(root: Path) -> Path:
    try:
        return REPOSITORY_PATH_POLICY.normalize(root)
    except EvagixSafetyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _normalize_existing_root(root: Path) -> Path:
    return _normalize_root(root)


def _resolve_cli_output_path(root: Path, output: str) -> Path:
    try:
        return resolve_output_path(root, output)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _facts(root: Path, profiles: list[str] | None = None) -> tuple[RepoFacts, EvagixConfig]:
    root = _normalize_existing_root(root)
    config = load_config(root)
    if config.parse_error:
        print(f"ERROR: Invalid Evagix config at {config.path}: {config.parse_error}", file=sys.stderr)
        raise SystemExit(1)
    facts = scan_repo(root, ignored_paths=config.ignored_paths)
    try:
        effective_profiles = normalize_profiles(merge_profiles(config, profiles))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    for name in effective_profiles:
        if name not in facts.active_profiles:
            facts.active_profiles.append(name)
    facts.custom_rules.extend(config.custom_rules)
    facts.custom_forbidden_actions.extend(config.custom_forbidden_actions)
    facts.ignored_paths = list(config.ignored_paths)
    facts.readme_ignore_claims = sorted(config.readme_ignore_claims)
    facts.config_path = str(config.path.relative_to(root)) if config.path else ""
    for name, command in config.custom_validation_commands.items():
        _set_command(
            facts,
            name,
            redact_sensitive_text(command),
            "evagix.toml",
            "configured command override",
            "high",
            priority=100,
            status="configured",
        )
    return facts, config


def _targets(config: EvagixConfig, requested: list[str] | None) -> list[str] | None:
    targets = selected_targets(config, requested)
    if targets:
        invalid = [item for item in targets if item not in TARGETS]
        if invalid:
            raise SystemExit(f"Unsupported target(s) in config: {', '.join(invalid)}")
    return targets


def _doctor(
    root: Path, profiles: list[str] | None = None, *, strict: bool = False
) -> tuple[RepoFacts, EvagixConfig, DoctorReport]:
    facts, config = _facts(root, profiles)
    report = doctor_repo(
        root,
        facts,
        target_keys=_targets(config, None),
        custom_targets=config.custom_targets,
        fail_on_stale=config.fail_on_stale,
        strict=strict,
        require_onboarding_pack=config.require_onboarding_pack,
    )
    return facts, config, apply_config_policy(report, config)
