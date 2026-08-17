from __future__ import annotations

from pathlib import Path
from typing import Any

from evagix.utils import resolve_output_path

CONFIG_FILENAMES = ("evagix.toml", ".evagix.toml")

_ALLOWED_ROOT_KEYS = {"targets", "profiles", "policy", "severity", "commands", "rules", "ignore", "readme_audit"}
_ALLOWED_TARGET_KEYS = {
    "universal_md",
    "universal_json",
    "agent_brief",
    "safety_policy",
    "repo_map",
    "agent_tasks",
    "agents",
    "claude",
    "gemini",
    "cursor",
    "copilot",
    "windsurf",
    "continue",
    "cline",
    "roo",
    "aider",
    "openhands",
    "generic",
    "custom",
}
_ALLOWED_POLICY_KEYS = {"fail_on_stale", "fail_under", "ignore_findings", "ignored_findings", "require_onboarding_pack"}
_ALLOWED_RULE_KEYS = {"general", "forbidden"}
_ALLOWED_IGNORE_KEYS = {"paths"}
_ALLOWED_README_AUDIT_KEYS = {"ignore_claims", "waive_claims"}
_ALLOWED_SEVERITIES = {"info", "warning", "error"}


def _validate_raw_config(raw: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    _unknown_keys("root", raw, _ALLOWED_ROOT_KEYS, errors)
    _require_mapping(raw, "targets", errors)
    _require_mapping(raw, "profiles", errors)
    _require_mapping(raw, "policy", errors)
    _require_mapping(raw, "severity", errors)
    _require_mapping(raw, "commands", errors)
    _require_mapping(raw, "rules", errors)
    _require_mapping(raw, "ignore", errors)
    _require_mapping(raw, "readme_audit", errors)

    targets = raw.get("targets", {})
    if isinstance(targets, dict):
        _unknown_keys("targets", targets, _ALLOWED_TARGET_KEYS, errors)
        for key, value in targets.items():
            if key == "custom":
                _validate_custom_targets(value, errors, root)
            elif not isinstance(value, bool):
                errors.append(f"targets.{key} must be a boolean")

    profiles = raw.get("profiles", {})
    if isinstance(profiles, dict):
        _unknown_keys("profiles", profiles, {"profiles"}, errors)
        _require_string_list(profiles.get("profiles", []), "profiles.profiles", errors)

    policy = raw.get("policy", {})
    if isinstance(policy, dict):
        _unknown_keys("policy", policy, _ALLOWED_POLICY_KEYS, errors)
        if "fail_on_stale" in policy and not isinstance(policy["fail_on_stale"], bool):
            errors.append("policy.fail_on_stale must be a boolean")
        if "require_onboarding_pack" in policy and not isinstance(policy["require_onboarding_pack"], bool):
            errors.append("policy.require_onboarding_pack must be a boolean")
        if "fail_under" in policy:
            value = policy["fail_under"]
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
                errors.append("policy.fail_under must be an integer from 0 to 100")
        for key in ("ignore_findings", "ignored_findings"):
            if key in policy:
                _require_string_list(policy[key], f"policy.{key}", errors)

    severity = raw.get("severity", {})
    if isinstance(severity, dict):
        for key, value in severity.items():
            if not isinstance(value, str) or value.strip().lower() not in _ALLOWED_SEVERITIES:
                errors.append(f"severity.{key} must be one of: {', '.join(sorted(_ALLOWED_SEVERITIES))}")

    commands = raw.get("commands", {})
    if isinstance(commands, dict):
        for key, value in commands.items():
            if not isinstance(value, str) or not value.strip():
                errors.append(f"commands.{key} must be a non-empty string")

    rules = raw.get("rules", {})
    if isinstance(rules, dict):
        _unknown_keys("rules", rules, _ALLOWED_RULE_KEYS, errors)
        for key in _ALLOWED_RULE_KEYS:
            if key in rules:
                _require_string_list(rules[key], f"rules.{key}", errors)

    ignore = raw.get("ignore", {})
    if isinstance(ignore, dict):
        _unknown_keys("ignore", ignore, _ALLOWED_IGNORE_KEYS, errors)
        if "paths" in ignore:
            _require_string_list(ignore["paths"], "ignore.paths", errors)

    readme_audit = raw.get("readme_audit", {})
    if isinstance(readme_audit, dict):
        _unknown_keys("readme_audit", readme_audit, _ALLOWED_README_AUDIT_KEYS, errors)
        for key in ("ignore_claims", "waive_claims"):
            if key in readme_audit:
                _require_string_list(readme_audit[key], f"readme_audit.{key}", errors)

    return errors


def _require_mapping(raw: dict[str, Any], key: str, errors: list[str]) -> None:
    if key in raw and not isinstance(raw[key], dict):
        errors.append(f"{key} must be a table")


def _unknown_keys(scope: str, values: dict[str, Any], allowed: set[str], errors: list[str]) -> None:
    for key in sorted(set(values) - allowed):
        errors.append(f"unknown {scope} key: {key}")


def _require_string_list(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        errors.append(f"{path} must be a list of strings")


def _validate_custom_targets(value: Any, errors: list[str], root: Path) -> None:
    if not isinstance(value, list):
        errors.append("targets.custom must be a list of tables")
        return
    allowed = {"name", "path", "format", "include"}
    for index, item in enumerate(value):
        prefix = f"targets.custom[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be a table")
            continue
        _unknown_keys(prefix, item, allowed, errors)
        if not isinstance(item.get("name"), str) or not item.get("name", "").strip():
            errors.append(f"{prefix}.name must be a non-empty string")
        raw_path = item.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            errors.append(f"{prefix}.path must be a non-empty string")
        else:
            try:
                resolve_output_path(root, raw_path.strip())
            except ValueError:
                errors.append(f"{prefix}.path must stay inside repository root")
        if "format" in item and item["format"] not in {"markdown", "json"}:
            errors.append(f"{prefix}.format must be markdown or json")
        if "include" in item:
            _require_string_list(item["include"], f"{prefix}.include", errors)
