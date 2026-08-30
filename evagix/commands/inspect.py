from __future__ import annotations

import sys
from pathlib import Path

from evagix.classification import (
    classify_project,
    format_primary_classification,
    render_classification_json,
    render_classification_text,
)
from evagix.commands.common import _facts, _normalize_existing_root, _normalize_root
from evagix.config import load_config
from evagix.explain import explain_finding
from evagix.model import RepoFacts
from evagix.profiles import PROFILES, normalize_profiles
from evagix.targets import ALL_TARGET_KEYS, TARGET_ADAPTERS, target_list_rows
from evagix.terminal import PLAIN_STYLE, TerminalStyle, style_human_text
from evagix.utils import (
    stable_json,
)
from evagix.validators import (
    suggest_actions,
)


def _cmd_scan(
    root: Path,
    as_json: bool,
    verbose: bool = False,
    profiles: list[str] | None = None,
    style: TerminalStyle = PLAIN_STYLE,
) -> int:
    facts, _ = _facts(root, profiles)
    if as_json:
        payload = {"schema_version": "1.0", **facts.to_dict()}
        print(stable_json(payload))
        return 0
    print(style.heading("Evagix Scan"))
    print("")
    print(f"Repository: {facts.root_name}")
    print(f"Languages: {', '.join(facts.languages) or 'not detected'}")
    print(f"Frameworks: {', '.join(facts.frameworks) or 'not detected'}")
    print(f"Backend tools: {', '.join(facts.backend_tools) or 'not detected'}")
    print(f"Frontend tools: {', '.join(facts.frontend_tools) or 'not detected'}")
    print(f"AI/Retrieval tools: {', '.join(facts.llm_tools) or 'not detected'}")
    print(f"ML/data tools: {', '.join(facts.ml_data_tools) or 'not detected'}")
    print(f"Dev tools: {', '.join(facts.dev_tools) or 'not detected'}")
    print(f"Package managers: {', '.join(facts.package_managers) or 'not detected'}")
    print(f"CI platforms: {', '.join(facts.ci_platforms) or 'not detected'}")
    print(f"Infrastructure tools: {', '.join(facts.infrastructure_tools) or 'not detected'}")
    print(f"Container platforms: {', '.join(facts.container_platforms) or 'not detected'}")
    if getattr(facts, "ecosystems", None):
        print("")
        print(style.heading("Ecosystems:"))
        displayed_ecosystems = facts.ecosystems if verbose else facts.ecosystems[:12]
        for item in displayed_ecosystems:
            labels = ", ".join(item.frameworks or item.tools or [item.language])
            detail = style.muted(f"({labels}; {item.support}; {item.confidence})")
            print(f"  - {item.path}: {item.name} {detail}")
        hidden = len(facts.ecosystems) - len(displayed_ecosystems)
        if hidden > 0:
            print(style.muted(f"  - ... {hidden} more ecosystem(s) hidden; re-run with --verbose to show all."))
    else:
        print("Ecosystems: not detected")
    print(f"Runtimes: {', '.join(facts.runtimes) or 'not detected'}")
    print(f"Databases: {', '.join(facts.databases) or 'not detected'}")
    print(f"Queues/caches: {', '.join(facts.queues) or 'not detected'}")
    print(f"Policy profiles: {', '.join(facts.active_profiles) or 'not detected'}")
    if facts.config_path:
        print(f"Config: {facts.config_path}")
    _print_classification_summary(facts)
    if facts.subprojects:
        print("")
        print(style.heading("Subprojects:"))
        displayed_subprojects = facts.subprojects if verbose else facts.subprojects[:20]
        for subproject in displayed_subprojects:
            labels = ", ".join(subproject.frameworks or subproject.dev_tools or [subproject.kind])
            detail = style.muted(f"({subproject.package_manager or 'n/a'})")
            print(f"  - {subproject.path}: {labels} {detail}")
        hidden = len(facts.subprojects) - len(displayed_subprojects)
        if hidden > 0:
            print(style.muted(f"  - ... {hidden} more subproject(s) hidden; re-run with --verbose to show all."))
    print("")
    print(style.heading("Commands:"))
    if facts.commands:
        command_items = list(facts.commands.items())
        displayed_commands = command_items if verbose else _summarize_commands(command_items)
        for name, command in displayed_commands:
            source = facts.command_sources[name]
            detail = style.muted(f"({source.source}, {source.confidence})")
            print(f"  - {name}: {command} {detail}")
        hidden = len(command_items) - len(displayed_commands)
        if hidden > 0:
            print(style.muted(f"  - ... {hidden} more command(s) hidden; re-run with --verbose to show all."))
    else:
        print("  - none detected")
    if facts.warnings:
        print("")
        print(style.heading("Warnings:"))
        displayed_warnings = facts.warnings if verbose else facts.warnings[:20]
        for warning in displayed_warnings:
            print(f"  [{style.status('WARN', width=4)}] {warning}")
        hidden = len(facts.warnings) - len(displayed_warnings)
        if hidden > 0:
            print(style.muted(f"  - ... {hidden} more warning(s) hidden; re-run with --verbose to show all."))
    return 0


def _summarize_commands(command_items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    root_names = {"install", "test", "lint", "typecheck", "build", "dev", "run", "format", "smoke", "eval", "doctor"}
    root_commands = [item for item in command_items if item[0] in root_names]
    remaining = [item for item in command_items if item[0] not in root_names]
    return (root_commands + remaining)[:30]


def _print_classification_summary(facts: RepoFacts) -> None:
    classification = facts.classification or {}
    primary_label = format_primary_classification(classification)
    secondary = classification.get("secondary", []) if isinstance(classification, dict) else []
    if primary_label:
        print(f"Primary type: {primary_label}")
    if isinstance(secondary, list) and secondary:
        labels = []
        for item in secondary[:4]:
            if isinstance(item, dict) and item.get("label"):
                labels.append(f"{item['label']} ({float(item.get('confidence', 0.0)):.2f})")
        if labels:
            print("Secondary capabilities: " + "; ".join(labels))


def _cmd_classify(
    root: Path,
    as_json: bool,
    profiles: list[str] | None = None,
    style: TerminalStyle = PLAIN_STYLE,
) -> int:
    facts, _ = _facts(root, profiles)
    classification = facts.classification
    if classification:
        if as_json:
            print(stable_json({"schema_version": "1.0", "classification": classification}) + "\n", end="")
        else:
            print(style_human_text(_render_classification_text_from_dict(classification), style), end="")
        return 0

    fallback = classify_project(_normalize_existing_root(root), facts)
    if as_json:
        print(render_classification_json(fallback), end="")
    else:
        print(style_human_text(render_classification_text(fallback), style), end="")
    return 0


def _render_classification_text_from_dict(classification: dict[str, object]) -> str:
    lines = ["Evagix Project Classification"]
    primary = classification.get("primary")
    if not isinstance(primary, dict) or not primary.get("label"):
        lines.append("Primary project type: not detected")
    else:
        confidence = float(primary.get("confidence", 0.0))
        lines.append(f"Primary project type: {primary['label']} ({confidence:.2f})")
        evidence = primary.get("evidence", [])
        if isinstance(evidence, list):
            for item in evidence:
                lines.append(f"  - {item}")
    lines.append("")
    lines.append("Secondary capabilities:")
    secondary = classification.get("secondary", [])
    if not isinstance(secondary, list) or not secondary:
        lines.append("  - none detected")
    else:
        for item in secondary:
            if not isinstance(item, dict) or not item.get("label"):
                continue
            confidence = float(item.get("confidence", 0.0))
            lines.append(f"  - {item['label']} ({confidence:.2f})")
            evidence = item.get("evidence", [])
            if isinstance(evidence, list):
                for evidence_item in evidence[:3]:
                    lines.append(f"    - {evidence_item}")
    return "\n".join(lines).rstrip() + "\n"


def _cmd_suggest(
    root: Path,
    profiles: list[str] | None = None,
    style: TerminalStyle = PLAIN_STYLE,
) -> int:
    root = _normalize_root(root)
    facts, _ = _facts(root, profiles)
    print(style.heading("Suggested next actions:"))
    for index, action in enumerate(suggest_actions(root, facts), start=1):
        print(f"  {index}. {action}")
    return 0


def _cmd_profiles(name: str | None = None, style: TerminalStyle = PLAIN_STYLE) -> int:
    if name:
        try:
            normalized = normalize_profiles([name])[0]
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        definition = PROFILES[normalized]
        print(style.heading(f"{definition.name}: {definition.title}"))
        print(definition.description)
        print(style.muted(f"Category: {definition.category}"))
        return 0
    print(style.heading("Available profiles:"))
    for definition in PROFILES.values():
        print(f"  - {definition.name}: {definition.title} ({definition.category})")
    return 0


def _cmd_targets(action: str, name: str | None, style: TerminalStyle = PLAIN_STYLE) -> int:
    if action == "show":
        if not name:
            print("Target name required. Example: `evagix targets show claude`.", file=sys.stderr)
            return 1
        adapter = TARGET_ADAPTERS.get(name)
        if not adapter:
            print(f"Unsupported target: {name}", file=sys.stderr)
            print("Supported targets: " + ", ".join(ALL_TARGET_KEYS), file=sys.stderr)
            return 1
        print(style.heading(f"Target: {adapter.name}"))
        print(f"Path: {adapter.path}")
        print(f"Label: {adapter.label}")
        print(f"Status: {'default' if adapter.default_enabled else 'optional'}")
        print(f"Category: {adapter.category}")
        print(style.muted(f"Description: {adapter.description}"))
        return 0

    print(style.heading("Available targets:"))
    for target_name, path, status, description in target_list_rows():
        print(f"  - {target_name}: {path} ({status})")
        print(style.muted(f"    {description}"))
    print("")
    print(style.heading("Examples:"))
    print("  evagix compile . --target universal_md")
    print("  evagix compile . --target universal_json")
    print("  evagix compile . --target claude")
    print("  evagix compile . --target claude --target cursor")
    return 0


def _cmd_policy(root: Path, as_json: bool, style: TerminalStyle = PLAIN_STYLE) -> int:
    root = _normalize_existing_root(root)
    config = load_config(root)
    payload = {
        "schema_version": "1.0",
        "tool": "evagix",
        "config_path": str(config.path) if config.path else None,
        "profiles": config.profiles,
        "targets": config.enabled_targets,
        "custom_targets": [item.__dict__ for item in config.custom_targets],
        "fail_under": config.fail_under,
        "fail_on_stale": config.fail_on_stale,
        "require_onboarding_pack": config.require_onboarding_pack,
        "parse_error": config.parse_error,
        "ignored_findings": sorted(config.ignored_findings),
        "severity_overrides": config.severity_overrides,
        "custom_rule_count": len(config.custom_rules),
        "custom_forbidden_count": len(config.custom_forbidden_actions),
        "custom_commands": config.custom_validation_commands,
        "ignored_paths": config.ignored_paths,
        "readme_ignore_claims": sorted(config.readme_ignore_claims),
    }
    if as_json:
        print(stable_json(payload))
    else:
        print(style.heading("Evagix Policy"))
        print(f"Config: {payload['config_path'] or 'not found'}")
        if config.parse_error:
            print(f"{style.warning('Invalid config')}: {config.parse_error}")
        print(f"Profiles: {', '.join(config.profiles) or 'not configured'}")
        print(f"Fail under: {config.fail_under}")
        print(f"Fail on stale: {config.fail_on_stale}")
        print(f"Require onboarding pack: {config.require_onboarding_pack}")
        print(f"Ignored findings: {', '.join(sorted(config.ignored_findings)) or 'none'}")
        print(f"Severity overrides: {config.severity_overrides or 'none'}")
        print(f"Custom commands: {config.custom_validation_commands or 'none'}")
        print(f"Ignored paths: {', '.join(config.ignored_paths) or 'none'}")
        print(f"README waived claims: {', '.join(sorted(config.readme_ignore_claims)) or 'none'}")
    return 1 if config.parse_error else 0


def _cmd_explain(code: str, style: TerminalStyle = PLAIN_STYLE) -> int:
    item = explain_finding(code)
    print(style.heading(f"{item.code}: {item.title}"))
    print(f"Severity hint: {style.semantic(item.severity_hint)}")
    print("")
    print(style.heading("Meaning:"))
    print(f"  {item.meaning}")
    print("")
    print(style.heading("Why it matters:"))
    print(f"  {item.why_it_matters}")
    print("")
    print(style.heading("Recommended fix:"))
    print(f"  {item.recommended_fix}")
    return 0
