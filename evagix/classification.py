from __future__ import annotations

from pathlib import Path

from evagix.classification_models import ProjectClassification, ProjectTypeMatch
from evagix.classification_rules import _is_primary_candidate, _Rule, _rule_priority, _rules
from evagix.core.io import safe_read_text
from evagix.model import RepoFacts
from evagix.scanner_utils import TraversalDiagnostics, _iter_repo_files
from evagix.security.output import redacted_text_output
from evagix.utils import stable_json


def format_primary_classification(classification: object) -> str:
    """Format a primary classification label and confidence safely."""

    primary = classification.get("primary") if isinstance(classification, dict) else None
    if not isinstance(primary, dict) or not primary.get("label"):
        return ""
    confidence = primary.get("confidence", 0.0)
    try:
        return f"{primary['label']} ({float(confidence):.2f})"
    except (TypeError, ValueError):
        return str(primary["label"])


def classify_project(root: Path, facts: RepoFacts) -> ProjectClassification:
    """Classify repository shape without executing project code.

    The classifier is deliberately heuristic: it reports evidence and confidence,
    not absolute truth. Scanner facts remain the source of evidence; this layer
    interprets those facts into user-facing project shapes.
    """

    root = Path(root)
    signal_index = _signal_index(root, facts)
    raw_matches = [_match_rule(rule, signal_index) for rule in _rules()]
    matches: list[ProjectTypeMatch] = [match for match in raw_matches if match is not None]
    if facts.languages:
        matches = [match for match in matches if match.name != "docs-only-repo"]
    matches.sort(key=lambda item: (-item.confidence, -_rule_priority(item.name), item.label))

    primary_candidates = [item for item in matches if _is_primary_candidate(item.name)]
    primary = primary_candidates[0] if primary_candidates else (matches[0] if matches else None)
    secondary = [item for item in matches if primary is None or item.name != primary.name][:10]
    return ProjectClassification(primary=primary, secondary=secondary, detected_signals=_public_signals(signal_index))


@redacted_text_output
def render_classification_text(classification: ProjectClassification) -> str:
    lines = ["Evagix Project Classification"]
    if classification.primary is None:
        lines.append("Primary project type: not detected")
    else:
        lines.append(f"Primary project type: {classification.primary.label} ({classification.primary.confidence:.2f})")
        for item in classification.primary.evidence:
            lines.append(f"  - {item}")
    lines.append("")
    lines.append("Secondary capabilities:")
    if not classification.secondary:
        lines.append("  - none detected")
    for match in classification.secondary:
        lines.append(f"  - {match.label} ({match.confidence:.2f})")
        for item in match.evidence[:3]:
            lines.append(f"    - {item}")
    return "\n".join(lines).rstrip() + "\n"


def render_classification_json(classification: ProjectClassification) -> str:
    return stable_json({"schema_version": "1.0", "classification": classification.to_dict()}) + "\n"


def _match_rule(rule: _Rule, signals: dict[str, set[str]]) -> ProjectTypeMatch | None:
    required_hits = [item for item in rule.required_any if _has_signal(signals, item)]
    path_hits = [item for item in rule.path_any if _has_path(signals, item)]
    if len(required_hits) + len(path_hits) < rule.min_required:
        return None

    support_hits = [item for item in rule.supporting_any if _has_signal(signals, item) or _has_path(signals, item)]
    raw_score = (0.55 * len(required_hits)) + (0.45 * len(path_hits)) + (0.18 * len(support_hits))
    # Broad `required_any` rules should not be penalized for options that are
    # alternatives rather than mandatory requirements. Score against the
    # evidence required to justify the match plus supporting evidence that
    # actually appeared, so composite AI/backend repos are not dominated by
    # one-signal frontend rules.
    expected_required = max(rule.min_required, len(required_hits))
    expected_paths = max(len(path_hits), min(len(rule.path_any), 1 if rule.path_any else 0))
    expected_support = max(len(support_hits), min(len(rule.supporting_any), 2 if rule.supporting_any else 0))
    max_score = max(1.0, (0.55 * expected_required) + (0.45 * expected_paths) + (0.18 * expected_support))
    confidence = max(0.52, min(0.99, round(raw_score / max_score, 2)))
    evidence = [_evidence_label(item) for item in required_hits + path_hits + support_hits]
    return ProjectTypeMatch(
        name=rule.name,
        label=rule.label,
        confidence=confidence,
        evidence=evidence[:8],
        signals=sorted(set(required_hits + path_hits + support_hits)),
    )


def _signal_index(root: Path, facts: RepoFacts) -> dict[str, set[str]]:
    pyproject_text = _safe_read(root / "pyproject.toml").lower()
    package_json_text = _safe_read(root / "package.json").lower()
    readme_text = _safe_read(root / "README.md").lower()
    diagnostics = TraversalDiagnostics()
    paths = {path.relative_to(root).as_posix().lower() for path in _iter_bounded_files(root, diagnostics=diagnostics)}
    if diagnostics.incomplete:
        warning = diagnostics.warning("Project classification path scan")
        if warning not in facts.warnings:
            facts.warnings.append(warning)
    return {
        "languages": {item.lower() for item in facts.languages},
        "frameworks": {item.lower() for item in facts.frameworks},
        "backend_tools": {item.lower() for item in facts.backend_tools},
        "frontend_tools": {item.lower() for item in facts.frontend_tools},
        "llm_tools": {item.lower() for item in facts.llm_tools},
        "ml_data_tools": {item.lower() for item in facts.ml_data_tools},
        "dev_tools": {item.lower() for item in facts.dev_tools},
        "package_managers": {item.lower() for item in facts.package_managers},
        "ci_platforms": {item.lower() for item in facts.ci_platforms},
        "infrastructure_tools": {item.lower() for item in facts.infrastructure_tools},
        "container_platforms": {item.lower() for item in facts.container_platforms},
        "databases": {item.lower() for item in facts.databases},
        "queues": {item.lower() for item in facts.queues},
        "runtimes": {item.lower() for item in facts.runtimes},
        "commands": {item.lower() for item in facts.commands},
        "paths": paths,
        "text": {pyproject_text, package_json_text, readme_text},
    }


def _has_signal(signals: dict[str, set[str]], value: str) -> bool:
    normalized = value.lower()
    if normalized == "ci":
        return bool(signals.get("ci_platforms", set()))
    if normalized == "workspace":
        return any("workspace" in blob for blob in signals.get("text", set()))
    if normalized in {"pyproject:scripts", "pyproject.toml", "package.json", "py.typed"}:
        return _has_path(signals, normalized)
    for bucket, values in signals.items():
        if bucket in {"paths", "text"}:
            continue
        if normalized in values:
            return True
    return False


def _has_path(signals: dict[str, set[str]], pattern: str) -> bool:
    paths = signals.get("paths", set())
    normalized = pattern.lower()
    if normalized == "pyproject:scripts":
        return any("[project.scripts]" in blob or "console_scripts" in blob for blob in signals.get("text", set()))
    if normalized.endswith("/"):
        return any(path.startswith(normalized) for path in paths)
    if normalized.startswith("*/"):
        suffix = normalized[2:]
        return any(path.endswith(suffix) for path in paths)
    return normalized in paths or any(path.endswith("/" + normalized) for path in paths)


def _evidence_label(signal: str) -> str:
    labels = {
        "pyproject:scripts": "pyproject.toml declares a console script entrypoint",
        "*/py.typed": "typed package marker detected",
        "ci": "CI workflow evidence detected",
    }
    return labels.get(signal, f"{signal} detected")


def _public_signals(signals: dict[str, set[str]]) -> dict[str, list[str]]:
    hidden = {"text", "paths"}
    return {key: sorted(values) for key, values in signals.items() if key not in hidden and values}


def _iter_bounded_files(
    root: Path,
    *,
    max_files: int = 12_000,
    diagnostics: TraversalDiagnostics | None = None,
) -> list[Path]:
    files: list[Path] = []
    for path in _iter_repo_files(root, diagnostics=diagnostics):
        if len(files) >= max_files:
            if diagnostics is not None:
                diagnostics.result_limit_reached = True
            break
        files.append(path)
    return files


def _safe_read(path: Path) -> str:
    try:
        if path.exists() and path.is_file():
            return safe_read_text(path, max_chars=80_000)
    except (OSError, UnicodeError):
        return ""
    return ""
