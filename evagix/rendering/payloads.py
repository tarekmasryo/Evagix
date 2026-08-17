from __future__ import annotations

from typing import Any

from evagix.config import CustomTarget
from evagix.model import RepoFacts
from evagix.rendering.fingerprints import generated_markdown_header
from evagix.rendering.sections import (
    _commands,
    _evidence,
    _forbidden_actions,
    _project_summary,
    _repository_map,
    _safety_policy,
)
from evagix.utils import facts_fingerprint, stable_json

_MANAGED_CONTEXT_KEYS = (
    "_evagix_generated",
    "_evagix_fingerprint",
    "schema_version",
    "tool",
    "repository",
    "fingerprint",
)


def render_custom_context(facts: RepoFacts, target: CustomTarget) -> str:
    if target.output_format == "json":
        payload = _filter_payload(_universal_context_payload(facts), target.include)
        payload["custom_target"] = {"name": target.name, "path": target.path, "format": target.output_format}
        return stable_json(payload) + "\n"
    sections = _custom_markdown_sections(facts, target.include)
    return generated_markdown_header(facts) + f"# {target.name} Context\n\n" + "\n\n".join(sections).strip() + "\n"


def _universal_context_payload(facts: RepoFacts) -> dict[str, Any]:
    facts_payload = facts.to_dict()
    facts_payload.pop("generated_targets", None)
    fingerprint = facts_fingerprint(facts_payload)
    return {
        "_evagix_fingerprint": f"evagix:fingerprint={fingerprint}",
        "_evagix_generated": "evagix:generated",
        "schema_version": "1.0",
        "tool": "evagix",
        "repository": facts.root_name,
        "fingerprint": fingerprint,
        "facts": facts_payload,
        "classification": facts.classification,
        "commands": facts.commands,
        "risk_flags": facts.risk_flags,
        "safety": {
            "custom_rules": facts.custom_rules,
            "forbidden_actions": [
                "Do not commit secrets, tokens, API keys, private certificates, or local .env files.",
                "Do not remove tests to make a failing suite pass.",
                "Do not claim validation passed unless the command was actually run successfully.",
            ]
            + facts.custom_forbidden_actions,
        },
        "export_model": "universal_context_with_tool_specific_adapters",
    }


def _filter_payload(payload: dict[str, Any], include: list[str]) -> dict[str, Any]:
    if not include:
        return payload
    aliases = {
        "risks": "risk_flags",
        "policies": "safety",
        "policy": "safety",
    }
    filtered: dict[str, Any] = {key: payload[key] for key in _MANAGED_CONTEXT_KEYS}
    for raw_key in include:
        key = aliases.get(raw_key, raw_key)
        if key in payload:
            filtered[key] = payload[key]
        elif key == "repo_map":
            filtered["repo_map"] = {
                "folders": payload["facts"].get("folders", []),
                "subprojects": payload["facts"].get("subprojects", []),
                "config_files": payload["facts"].get("config_files", []),
            }
    return filtered


def _custom_markdown_sections(facts: RepoFacts, include: list[str]) -> list[str]:
    sections = {
        "facts": _project_summary(facts),
        "commands": _commands(facts),
        "risks": _safety_policy(facts),
        "risk_flags": _safety_policy(facts),
        "policies": _forbidden_actions(facts),
        "policy": _forbidden_actions(facts),
        "repo_map": _repository_map(facts),
        "evidence": _evidence(facts),
    }
    selected = include or ["facts", "commands", "repo_map", "risks", "policies", "evidence"]
    return [sections[key] for key in selected if key in sections]
