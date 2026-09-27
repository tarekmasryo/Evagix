from __future__ import annotations

from textwrap import dedent
from typing import cast

from evagix.config import CustomTarget
from evagix.core.paths import output_path_key
from evagix.generated_integrity import INTEGRITY_MANIFEST_PATH, attach_content_digest
from evagix.model import RepoFacts
from evagix.rendering.fingerprints import generated_markdown_header
from evagix.rendering.payloads import _universal_context_payload, render_custom_context
from evagix.rendering.sections import (
    _commands,
    _forbidden_actions,
    _project_summary,
    _repository_map,
    _safety_policy,
    _shared_sections,
)
from evagix.rendering.target_renderers import (
    render_agents_md,
    render_aider_conventions,
    render_claude_md,
    render_cline_rule,
    render_continue_rule,
    render_copilot_instructions,
    render_cursor_rule,
    render_gemini_md,
    render_generic_agent_context,
    render_openhands_skill,
    render_roo_rule,
    render_windsurf_rule,
)
from evagix.safety import EvagixSafetyError
from evagix.security.redaction import redact_sensitive_text
from evagix.targets import DEFAULT_TARGET_KEYS, TARGET_ADAPTERS, builtin_output_paths, target_paths
from evagix.task_renderers import render_agent_tasks
from evagix.utils import format_csv, stable_json

TARGETS = target_paths(default_only=False)
DEFAULT_TARGETS = target_paths(default_only=True)


def render_all(
    facts: RepoFacts,
    target_keys: list[str] | None = None,
    custom_targets: list[CustomTarget] | None = None,
) -> dict[str, str]:
    keys = list(DEFAULT_TARGET_KEYS) if target_keys is None else list(target_keys)
    renderers = {
        "universal_md": render_universal_context_md,
        "universal_json": render_universal_context_json,
        "agent_brief": render_agent_brief_md,
        "safety_policy": render_safety_policy_md,
        "repo_map": render_repo_map_md,
        "agent_tasks": render_agent_tasks,
        "agents": render_agents_md,
        "claude": render_claude_md,
        "gemini": render_gemini_md,
        "cursor": render_cursor_rule,
        "copilot": render_copilot_instructions,
        "windsurf": render_windsurf_rule,
        "continue": render_continue_rule,
        "cline": render_cline_rule,
        "roo": render_roo_rule,
        "aider": render_aider_conventions,
        "openhands": render_openhands_skill,
        "generic": render_generic_agent_context,
    }
    outputs: dict[str, str] = {}
    paths: set[str] = set()

    def add_output(path: str, content: str) -> None:
        key = output_path_key(path)
        if key in paths:
            raise EvagixSafetyError(f"duplicate generated output path: {path}")
        paths.add(key)
        outputs[path] = attach_content_digest(redact_sensitive_text(content))

    for key in dict.fromkeys(keys):
        renderer = renderers.get(key)
        if renderer is None:
            available = ", ".join(sorted(renderers))
            raise ValueError(f"Unknown render target: {key}. Available targets: {available}")
        rendered = renderer(facts)
        if isinstance(rendered, dict):
            for path, content in cast(dict[str, str], rendered).items():
                add_output(path, content)
        else:
            add_output(TARGET_ADAPTERS[key].path, cast(str, rendered))
    reserved = {output_path_key(path) for path in builtin_output_paths() | {INTEGRITY_MANIFEST_PATH}}
    names: set[str] = set()
    for target in custom_targets or []:
        if target.name.strip() in names:
            raise EvagixSafetyError(f"duplicate custom target name: {target.name}")
        names.add(target.name.strip())
        if output_path_key(target.path) in reserved:
            raise EvagixSafetyError(f"Custom target collides with reserved generated output path: {target.path}")
        add_output(target.path, render_custom_context(facts, target))
    return outputs


def render_universal_context_md(facts: RepoFacts) -> str:
    intro = dedent(
        """
        # Evagix Universal Repository Context

        Evidence-backed, tool-agnostic repository context for any AI coding agent, model, CLI wrapper, reviewer, or internal automation.
        Tool-specific export files are adapters built from this shared context.
        """
    ).strip()
    return generated_markdown_header(facts) + intro + "\n\n" + _shared_sections(facts)


def render_universal_context_json(facts: RepoFacts) -> str:
    payload = _universal_context_payload(facts)
    return stable_json(payload) + "\n"


def render_agent_brief_md(facts: RepoFacts) -> str:
    lines = [
        generated_markdown_header(facts).rstrip(),
        "# Evagix Agent Brief",
        "",
        f"- Repository: `{facts.root_name}`",
        f"- Languages: {format_csv(facts.languages)}",
        f"- Frameworks: {format_csv(facts.frameworks)}",
        f"- Commands: {format_csv(sorted(facts.commands))}",
        f"- Risk flags: `{len(facts.risk_flags)}` detected" if facts.risk_flags else "- Risk flags: `0` detected",
        "",
        "## Start Here",
        "",
        "- Inspect existing patterns before changing code.",
        "- Use detected commands only when they fit the changed area.",
        "- Keep changes small, reviewable, and reversible.",
        "- Report validation commands actually run and any skipped checks.",
    ]
    return "\n".join(lines).strip() + "\n"


def render_safety_policy_md(facts: RepoFacts) -> str:
    return (
        generated_markdown_header(facts)
        + "# Evagix Safety Policy\n\n"
        + _safety_policy(facts)
        + "\n\n"
        + _forbidden_actions(facts)
        + "\n"
    )


def render_repo_map_md(facts: RepoFacts) -> str:
    return (
        generated_markdown_header(facts)
        + "# Evagix Repository Map\n\n"
        + _project_summary(facts)
        + "\n\n"
        + _commands(facts)
        + "\n\n"
        + _repository_map(facts)
        + "\n"
    )
