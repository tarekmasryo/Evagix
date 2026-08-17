from __future__ import annotations

from evagix.model import RepoFacts
from evagix.rendering.sections_core import (
    _classification_section,
    _commands,
    _profile_section,
    _project_summary,
    _repository_map,
    _untrusted_context_banner,
)
from evagix.rendering.sections_domain import (
    _backend_api_rules,
    _dashboard_rules,
    _database_rules,
    _frontend_rules,
    _llm_rag_rules,
    _ml_project_rules,
    _runtime_rules,
    _worker_queue_rules,
)
from evagix.rendering.sections_policy import (
    _change_review_policy,
    _coding_style,
    _custom_rules,
    _evidence,
    _forbidden_actions,
    _safety_policy,
    _testing_policy,
    _warnings,
)


def _main_body(facts: RepoFacts, title: str) -> str:
    return f"# {title}\n\n" + _shared_sections(facts)


def _shared_sections(facts: RepoFacts) -> str:
    sections = [
        _untrusted_context_banner(),
        _project_summary(facts),
        _classification_section(facts),
        _profile_section(facts),
        _commands(facts),
        _repository_map(facts),
        _coding_style(facts),
        _testing_policy(facts),
        _change_review_policy(facts),
        _custom_rules(facts),
    ]
    if facts.is_backend_project:
        sections.append(_backend_api_rules(facts))
    if facts.has_database_migrations or facts.databases:
        sections.append(_database_rules(facts))
    if facts.queues:
        sections.append(_worker_queue_rules(facts))
    if facts.is_llm_project:
        sections.append(_llm_rag_rules(facts))
    if facts.is_ml_project:
        sections.append(_ml_project_rules(facts))
    if facts.is_dashboard_project:
        sections.append(_dashboard_rules(facts))
    if facts.is_frontend_project:
        sections.append(_frontend_rules(facts))
    if facts.runtimes:
        sections.append(_runtime_rules(facts))
    sections.extend([_safety_policy(facts), _forbidden_actions(facts), _evidence(facts)])
    if facts.warnings:
        sections.append(_warnings(facts))
    return "\n\n".join(section for section in sections if section).strip() + "\n"
