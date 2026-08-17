from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from evagix.config_models import CustomTarget, EvagixConfig
from evagix.config_validate import _validate_raw_config
from evagix.core.io import safe_read_text
from evagix.thresholds import coerce_score_threshold

CONFIG_FILENAMES = ("evagix.toml", ".evagix.toml")


def load_config(root: Path) -> EvagixConfig:
    root = root.resolve()
    for filename in CONFIG_FILENAMES:
        path = root / filename
        if path.exists():
            return _parse_config(path)
    return EvagixConfig()


def _parse_config(path: Path) -> EvagixConfig:
    try:
        raw = tomllib.loads(safe_read_text(path, root=path.parent))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        return EvagixConfig(path=path, parse_error=f"{type(exc).__name__}: {exc}")

    validation_errors = _validate_raw_config(raw, path.parent)
    if validation_errors:
        return EvagixConfig(path=path, parse_error="; ".join(validation_errors))

    profiles_raw = raw.get("profiles", {})
    profiles = _list_str(profiles_raw.get("profiles", []) if isinstance(profiles_raw, dict) else profiles_raw)

    targets_raw = raw.get("targets", {}) if isinstance(raw.get("targets", {}), dict) else {}
    enabled_targets = {str(k): bool(v) for k, v in targets_raw.items() if isinstance(v, bool)}
    custom_targets = _parse_custom_targets(targets_raw.get("custom", [])) if isinstance(targets_raw, dict) else []

    policy = raw.get("policy", {}) if isinstance(raw.get("policy", {}), dict) else {}
    fail_under = coerce_score_threshold(policy.get("fail_under", 80))
    fail_on_stale = _bool(policy.get("fail_on_stale", True), default=True)
    require_onboarding_pack = _bool(policy.get("require_onboarding_pack", False), default=False)
    ignored = set(_list_str(policy.get("ignore_findings", policy.get("ignored_findings", []))))

    severity_overrides: dict[str, str] = {}
    severity_raw = raw.get("severity", {}) if isinstance(raw.get("severity", {}), dict) else {}
    for code, severity in severity_raw.items():
        severity_value = str(severity).strip().lower()
        if severity_value in {"info", "warning", "error"}:
            severity_overrides[str(code)] = severity_value

    rules = raw.get("rules", {}) if isinstance(raw.get("rules", {}), dict) else {}
    commands = raw.get("commands", {}) if isinstance(raw.get("commands", {}), dict) else {}
    ignore = raw.get("ignore", {}) if isinstance(raw.get("ignore", {}), dict) else {}
    readme_audit = raw.get("readme_audit", {}) if isinstance(raw.get("readme_audit", {}), dict) else {}

    return EvagixConfig(
        path=path,
        profiles=profiles,
        enabled_targets=enabled_targets,
        custom_targets=custom_targets,
        fail_under=fail_under,
        fail_on_stale=fail_on_stale,
        require_onboarding_pack=require_onboarding_pack,
        ignored_findings=ignored,
        severity_overrides=severity_overrides,
        custom_rules=_list_str(rules.get("general", [])),
        custom_forbidden_actions=_list_str(rules.get("forbidden", [])),
        custom_validation_commands={str(k): str(v) for k, v in commands.items()},
        ignored_paths=_list_str(ignore.get("paths", [])),
        readme_ignore_claims=set(
            _list_str(readme_audit.get("ignore_claims", [])) + _list_str(readme_audit.get("waive_claims", []))
        ),
    )


def selected_targets(config: EvagixConfig, requested: list[str] | None) -> list[str] | None:
    if requested:
        return requested
    if not config.enabled_targets:
        return None
    return [name for name, enabled in config.enabled_targets.items() if enabled]


def merge_profiles(config: EvagixConfig, cli_profiles: list[str] | None) -> list[str]:
    values: list[str] = []
    for profile in config.profiles + (cli_profiles or []):
        if profile not in values:
            values.append(profile)
    return values


def _parse_custom_targets(value: Any) -> list[CustomTarget]:
    if not isinstance(value, list):
        return []
    targets: list[CustomTarget] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        path = str(item.get("path", "")).strip()
        output_format = str(item.get("format", "markdown")).strip().lower() or "markdown"
        if not name or not path or output_format not in {"markdown", "json"}:
            continue
        targets.append(
            CustomTarget(name=name, path=path, output_format=output_format, include=_list_str(item.get("include", [])))
        )
    return targets


def _bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default


def _list_str(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []
