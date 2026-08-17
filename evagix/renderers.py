"""Backward-compatible public facade for generated-context rendering."""

from __future__ import annotations

from evagix.rendering.context import (
    DEFAULT_TARGETS,
    TARGETS,
    render_agent_brief_md,
    render_all,
    render_repo_map_md,
    render_safety_policy_md,
    render_universal_context_json,
    render_universal_context_md,
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
from evagix.task_renderers import render_agent_tasks

__all__ = [
    "DEFAULT_TARGETS",
    "TARGETS",
    "render_agent_brief_md",
    "render_agent_tasks",
    "render_agents_md",
    "render_aider_conventions",
    "render_all",
    "render_claude_md",
    "render_cline_rule",
    "render_continue_rule",
    "render_copilot_instructions",
    "render_cursor_rule",
    "render_gemini_md",
    "render_generic_agent_context",
    "render_openhands_skill",
    "render_repo_map_md",
    "render_roo_rule",
    "render_safety_policy_md",
    "render_universal_context_json",
    "render_universal_context_md",
    "render_windsurf_rule",
]
