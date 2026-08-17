from __future__ import annotations

import re

from evagix.core.text import line_at_index
from evagix.readme.claim_text_scan import _is_adjacent_attribution_reference, _is_markdown_link_destination
from evagix.readme.findings import ReadmeClaim


def _claim_occurrences(pattern: str, text: str, *, root_name: str = "") -> list[tuple[str, int]]:
    occurrences: list[tuple[str, int]] = []
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        phrase = match.group(0).strip()
        if not phrase or _is_markdown_link_destination(text, match.start()):
            continue
        line = line_at_index(text, match.start())
        line_start = text.rfind("\n", 0, match.start()) + 1
        relative_start = match.start() - line_start
        relative_end = match.end() - line_start
        clause, clause_start = _claim_clause(line, relative_start, relative_end)
        if _is_negated_or_future_claim(
            clause,
            relative_start - clause_start,
            relative_end - clause_start,
        ):
            continue
        if _is_non_project_claim_context(text, match.start(), match.end(), root_name=root_name):
            continue
        occurrences.append((phrase, text.count("\n", 0, match.start()) + 1))
    return occurrences


def _is_non_project_claim_context(text: str, match_start: int, match_end: int, *, root_name: str) -> bool:
    """Reject clear references to downstream users, integrations, lessons, or other components."""
    line_start = text.rfind("\n", 0, match_start) + 1
    line_end = text.find("\n", match_end)
    if line_end < 0:
        line_end = len(text)
    line = " ".join(text[line_start:line_end].casefold().split())
    before = " ".join(text[line_start:match_start].casefold().split())
    after = " ".join(text[match_end:line_end].casefold().split())
    heading_context = " / ".join(_active_markdown_headings(text, match_start))
    list_context = _list_lead_in(text, line_start)
    root_assertion = _has_root_subject(line)
    phrase = text[match_start:match_end]

    if _is_adjacent_attribution_reference(text, match_start) or _is_non_project_list_context(list_context):
        return True
    if _is_downstream_or_comparison_reference(before, after, line, phrase=phrase, root_name=root_name):
        return True
    if _is_integration_reference(before, heading_context, root_assertion=root_assertion):
        return True
    if _is_other_component_property(
        before,
        heading_context,
        root_name=root_name,
        root_subject_before_claim=_has_root_subject(before),
    ):
        return True
    if root_assertion:
        return False

    educational_markers = (
        "course",
        "curriculum",
        "syllabus",
        "lesson",
        "module",
        "learning objective",
        "topics taught",
        "you will learn",
        "teaches",
        "workshop",
    )
    if any(marker in line or marker in heading_context for marker in educational_markers):
        return True

    reference_sections = (
        "related project",
        "other project",
        "used by",
        "users",
        "customers",
        "framework integration",
        "compatibility",
        "documentation navigation",
        "table of contents",
    )
    return any(marker in heading_context for marker in reference_sections)


def _has_root_subject(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:this|the)\s+(?:project|repository|tool|package|library|application|service|codebase)\b|"
            r"\bour\s+(?:project|repository|tool|package|library|application|service|codebase)\b|\bwe\b",
            text,
        )
    )


def _active_markdown_headings(text: str, position: int) -> list[str]:
    active: dict[int, str] = {}
    rst_levels: dict[str, int] = {}
    lines = text[:position].splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^\s*(#{1,6})\s+(.+?)\s*$", line)
        if match:
            level = len(match.group(1))
            active = {key: value for key, value in active.items() if key < level}
            active[level] = match.group(2).strip().casefold()
            index += 1
            continue
        if index + 1 < len(lines):
            underline = re.match(r"^\s*([=\-~^\"'+*#])\1{2,}\s*$", lines[index + 1])
            title = line.strip()
            if underline and title and len(lines[index + 1].strip()) >= len(title):
                marker = underline.group(1)
                level = rst_levels.setdefault(marker, len(rst_levels) + 1)
                active = {key: value for key, value in active.items() if key < level}
                active[level] = title.casefold()
                index += 2
                continue
        index += 1
    return [active[level] for level in sorted(active)]


def _list_lead_in(text: str, line_start: int) -> str:
    line_end = text.find("\n", line_start)
    if line_end < 0:
        line_end = len(text)
    current = text[line_start:line_end]
    if not re.match(r"^\s*(?:[-+*]|\d+[.)])\s+", current):
        return ""
    for previous in reversed(text[:line_start].splitlines()):
        stripped = previous.strip()
        if not stripped or re.match(r"^(?:[-+*]|\d+[.)])\s+", stripped):
            continue
        return " ".join(stripped.casefold().split())
    return ""


def _is_non_project_list_context(lead_in: str) -> bool:
    if not lead_in:
        return False
    downstream = (
        r"\b(?:is\s+)?(?:used|adopted)\s+(?:by|in)\b",
        r"\b(?:projects?|repositories|applications|customers|users)\s+"
        r"(?:using|that use|include|including)\b",
    )
    integrations = (
        r"\bintegrates?\s+with\b",
        r"\bcompatible\s+with\b",
        r"\bworks?\s+with\b",
        r"\b(?:integrations?|adapters?|plugins?|support)\s+(?:with|for)\b",
    )
    return any(re.search(pattern, lead_in) for pattern in (*downstream, *integrations))


def _is_downstream_or_comparison_reference(
    before: str,
    after: str,
    line: str,
    *,
    phrase: str,
    root_name: str,
) -> bool:
    if re.search(r"\bused\s+by\s*$", before):
        return True
    if re.search(r"\b(?:projects?|tools?|libraries?)\s+using\s+(?:this|our)\s+\w+\s+include\s*$", before):
        return True
    if _is_root_owned_passive(after):
        return False
    if re.match(r"^\s*(?:is|are|uses?|adopts?|depends\s+on)\b", after) and not before:
        return not _subject_matches_root(phrase, root_name)
    if re.search(r"\b(?:for example|e\.g\.|such as|including|unlike|compared (?:to|with)|similar to)\s*,?\s*$", before):
        return True
    return "comparison" in line and not before


def _is_root_owned_passive(after: str) -> bool:
    return bool(
        re.match(
            r"^\s*(?:is|are|was|were)\s+(?:directly\s+)?"
            r"(?:used|adopted|implemented|included|provided|supported)\s+by\s+"
            r"(?:this|the|our)\s+(?:project|repository|tool|package|library|application|service|codebase)\b",
            after,
        )
    )


def _is_integration_reference(before: str, heading_context: str, *, root_assertion: bool) -> bool:
    if re.search(
        r"\b(?:integrates?\s+with|compatible\s+with|works?\s+with|integration\s+(?:with|for)|"
        r"adapter\s+for|plugin\s+for|support\s+for)\s*$",
        before,
    ):
        return True
    return not root_assertion and any(
        marker in heading_context for marker in ("integration", "compatibility", "works with")
    )


def _is_other_component_property(
    before: str,
    heading_context: str,
    *,
    root_name: str,
    root_subject_before_claim: bool,
) -> bool:
    if root_subject_before_claim:
        return False
    subject = _explicit_subject(before)
    if not subject or _subject_matches_root(subject, root_name):
        return False
    related_section = any(
        marker in heading_context
        for marker in ("related project", "other project", "related component", "ecosystem", "suite")
    )
    explicitly_named = "`" in subject or "[" in subject
    return related_section or explicitly_named


def _explicit_subject(before: str) -> str:
    markdown_entry = re.search(
        r"(?:^|[-*]\s+)(?:\*\*)?(\[[^\]]+\]\([^)]+\)|`[^`]+`)(?:\*\*)?\s*(?:—|–|:)",
        before,
    )
    if markdown_entry:
        return markdown_entry.group(1)
    candidates = re.findall(
        r"(`[^`]+`|\[[^\]]+\]\([^)]+\)|[\w.-]+(?:\s+[\w.-]+){0,3})\s+"
        r"(?:is|are|has|adds|provides|offers|includes|features)\b",
        before,
    )
    return candidates[-1] if candidates else ""


def _subject_matches_root(subject: str, root_name: str) -> bool:
    if not root_name:
        return False
    cleaned_subject = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", subject)
    cleaned_subject = cleaned_subject.strip("`*_ ")
    cleaned_subject = re.sub(r"^(?:the|a|an)\s+", "", cleaned_subject)
    normalized_subject = re.sub(r"[^a-z0-9]+", "", cleaned_subject.casefold())
    raw_aliases = {root_name.casefold(), root_name.casefold().replace("\\", "/").rsplit("/", 1)[-1]}
    raw_aliases.update(part for part in root_name.casefold().split("__") if part)
    aliases = {re.sub(r"[^a-z0-9]+", "", alias.removesuffix(".git")) for alias in raw_aliases}
    if normalized_subject in aliases:
        return True
    generic_suffixes = ("project", "repository", "tool", "package", "library", "application", "service", "cli")
    return any(normalized_subject == alias + suffix for alias in aliases for suffix in generic_suffixes)


def _claim_clause(line: str, match_start: int, match_end: int) -> tuple[str, int]:
    boundaries = []
    for boundary in re.finditer(r"[.!?]+|,|;|\b(?:and|but|however|although|yet)\b", line, flags=re.IGNORECASE):
        if boundary.group(0).casefold() == "yet" and re.search(r"\bnot\s+$", line[: boundary.start()], re.IGNORECASE):
            continue
        boundaries.append(boundary)
    clause_start = 0
    clause_end = len(line)
    for boundary in boundaries:
        if boundary.end() <= match_start:
            clause_start = boundary.end()
        elif boundary.start() >= match_end:
            clause_end = boundary.start()
            break
    return line[clause_start:clause_end], clause_start


def _is_negated_or_future_claim(text: str, match_start: int, match_end: int) -> bool:
    lower = text.casefold()
    before = lower[:match_start]
    after = lower[match_end:]
    non_negating_not_only = re.search(r"\bnot\s+only\s*$", before)
    if not non_negating_not_only and re.search(
        r"(?:\bnot(?:\s+(?:yet|currently))?|\bisn't|\baren't|\bunsupported)"
        r"(?:\s+[\w-]+){0,2}\s*$",
        before,
    ):
        return True
    if re.match(
        r"^\s*(?:(?:is|are|was|were)\s+)?(?:not\b|isn't\b|aren't\b|unsupported\b)",
        after,
    ):
        return True
    future_markers = (
        "planned",
        "future",
        "roadmap",
        "coming soon",
        "will add",
    )
    return any(marker in lower for marker in future_markers)


def _strip_ignored_blocks(text: str) -> str:
    text = _strip_audit_ignore_blocks(text)
    text = re.sub(r"```.*?```", _blank_matched_lines, text, flags=re.DOTALL)
    return _strip_documentation_examples(text)


def _strip_audit_ignore_blocks(text: str) -> str:
    return re.sub(
        r"<!--\s*evagix:audit-ignore-start\s*-->.*?<!--\s*evagix:audit-ignore-end\s*-->",
        _blank_matched_lines,
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )


def _blank_matched_lines(match: re.Match[str]) -> str:
    """Blank ignored content while preserving original line numbering."""
    return "\n".join("" for _ in match.group(0).splitlines())


def _strip_documentation_examples(text: str) -> str:
    """Remove README prose that explains Evagix claim types instead of making project claims."""
    cleaned: list[str] = []
    skip_until_heading_level: int | None = None
    example_headings = (
        "readme claim audit",
        "strict evidence mode",
        "broken context demo",
        "what evagix does not do",
        "stable schemas",
    )
    for line in text.splitlines():
        stripped = line.strip()
        heading = re.match(r"^(#{2,6})\s+(.+)$", stripped)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip().lower()
            if skip_until_heading_level is not None and level <= skip_until_heading_level:
                skip_until_heading_level = None
            if any(title.startswith(item) for item in example_headings):
                skip_until_heading_level = level
                cleaned.append("")
                continue
        if skip_until_heading_level is not None:
            cleaned.append("")
            continue
        lower = stripped.lower()
        if "evagix" in lower and any(
            word in lower for word in ["detects", "checks", "flags", "audits", "claims such as"]
        ):
            cleaned.append("")
            continue
        if "claim" in lower and any(word in lower for word in ["example", "examples", "unsupported", "evidence"]):
            cleaned.append("")
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def _line_number_for_phrase(text: str, phrase: str) -> int | None:
    if not phrase:
        return None
    lower_text = text.lower()
    lower_phrase = phrase.lower()
    index = lower_text.find(lower_phrase)
    if index < 0:
        return None
    return text.count("\n", 0, index) + 1


def _claim_confidence(verdict: str, claim: str) -> str:
    if verdict in {"supported", "unsupported"} and claim not in {"production-ready", "secure", "monitoring"}:
        return "high"
    if verdict in {"manual_review_required", "waived"}:
        return "low"
    return "medium"


def _score(claims: list[ReadmeClaim], *, strict: bool = False) -> int:
    if not claims:
        return 100
    score = 100
    for item in claims:
        if item.verdict == "unsupported":
            score -= 18
        elif item.verdict == "weak_evidence":
            score -= 12
        elif item.verdict in {"manual_review_required", "waived"}:
            score -= 10
        elif item.verdict in {"partial", "partially_supported"}:
            score -= 8
    bounded = max(0, min(100, score))
    if strict and any(item.claim in {"secure", "production-ready"} and item.verdict != "supported" for item in claims):
        bounded = min(bounded, 79)
    if any(item.verdict == "waived" for item in claims):
        bounded = min(bounded, 89)
    return bounded
