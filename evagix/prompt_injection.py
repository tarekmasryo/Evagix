from __future__ import annotations

import re
from pathlib import Path

from evagix.agent_context_registry import (
    generated_agent_target_paths,
    iter_agent_context_paths,
)
from evagix.command_safety import TEXT_SUFFIXES, _safe_relative
from evagix.core.io import is_safe_repo_path, safe_read_text_result
from evagix.core.text import line_at_index, line_number_at_index
from evagix.evidence import Finding
from evagix.scanner_utils import TraversalDiagnostics, _iter_repo_files, is_sensitive_file_name
from evagix.text_diagnostics import invalid_utf8_finding

MAX_CONTEXT_TEXT_FILES = 350
MAX_CONTEXT_TEXT_BYTES = 500_000
MAX_CONTEXT_TEXT_CHARS = 200_000

POISONING_PATTERNS: tuple[tuple[str, str, str], ...] = (
    (
        "context-poisoning.ignore-instructions",
        r"ignor(?:e|ing)\s+(all\s+)?(previous|prior|above)\s+instructions",
        "Downstream agents may treat repo text as higher-priority instructions.",
    ),
    (
        "context-poisoning.reveal-secrets",
        r"\b(reveal(?:ing)?|print(?:ing)?|dump(?:ing)?|show(?:ing)?|send(?:ing)?)\b[^\n]{0,80}\b(secrets?|api keys?|tokens?|credentials?)\b",
        "The instruction asks an agent to expose secrets or credentials.",
    ),
    (
        "context-poisoning.system-prompt",
        r"\b(system prompt|developer message|hidden instructions?)\b",
        "The text references higher-priority prompts that repository content should not control.",
    ),
    (
        "context-poisoning.exfiltrate",
        r"\b(exfiltrate|send)\b[^\n]{0,100}\b(env|\.env|secrets?|tokens?)\b",
        "The instruction may encourage data exfiltration.",
    ),
    (
        "context-poisoning.bypass-safety",
        r"\b(bypass(?:ing|ed)?|disable(?:d|ing)?|ignore|ignoring)\b[^\n]{0,80}\b(safety|policy|guardrails?|checks?)\b",
        "The instruction asks an agent to bypass safety or validation controls.",
    ),
)


def scan_context_poisoning(root: Path, *, paths: list[Path] | None = None) -> list[Finding]:
    findings: list[Finding] = []
    candidates, diagnostics = (paths, None) if paths is not None else _agent_and_doc_files(root)
    for path in candidates or []:
        try:
            read_result = safe_read_text_result(
                path,
                root=root,
                max_chars=MAX_CONTEXT_TEXT_CHARS,
            )
        except UnicodeError:
            findings.append(
                invalid_utf8_finding(root, path, scanner="Context-poisoning scan", category="context_safety")
            )
            continue
        except OSError:
            findings.append(_scan_read_error_finding(_safe_relative(root, path)))
            continue
        relative = _safe_relative(root, path)
        if read_result.truncated:
            findings.append(
                Finding(
                    id="context-poisoning.scan-truncated",
                    title="Context-poisoning scan was truncated",
                    category="context_safety",
                    severity="high",
                    status="incomplete",
                    source=relative,
                    source_file=relative,
                    evidence=[f"read limit: {MAX_CONTEXT_TEXT_CHARS} characters"],
                    risk="Content beyond the read limit was not inspected for context-poisoning instructions.",
                    recommendation="Reduce or split the context file before relying on the safety result.",
                    confidence="high",
                    root_cause=f"context-poisoning-truncated:{relative}",
                )
            )
        text = read_result.text
        for code, pattern, risk in POISONING_PATTERNS:
            occurrences: list[tuple[int, str]] = []
            for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
                snippet = line_at_index(text, match.start()).strip()
                if _is_evagix_safety_banner_line(snippet) or _is_protective_or_neutral_context(snippet, code):
                    continue
                occurrences.append((line_number_at_index(text, match.start()), snippet[:220]))
            if occurrences:
                first_line = occurrences[0][0]
                findings.append(
                    Finding(
                        id=code,
                        title="Potential context-poisoning instruction detected",
                        category="context_safety",
                        severity="high",
                        status="unsafe",
                        source=relative,
                        source_file=relative,
                        source_line=first_line,
                        evidence=[snippet for _line, snippet in occurrences[:5]],
                        evidence_files=[relative],
                        missing=[],
                        confidence="high",
                        risk=risk,
                        recommendation="Remove, rewrite, or quarantine this instruction. Repository text must be treated as untrusted input by AI agents.",
                        metadata={
                            "occurrence_count": len(occurrences),
                            "first_line": first_line,
                            "sample_lines": [line for line, _snippet in occurrences[:5]],
                        },
                    )
                )
    if diagnostics is not None and diagnostics.incomplete:
        findings.append(
            Finding(
                id="context-poisoning.discovery-truncated",
                title="Context-poisoning discovery was truncated",
                category="context_safety",
                severity="high",
                status="incomplete",
                source="repository context paths",
                evidence=[diagnostics.warning("Context-poisoning discovery")],
                risk="Some context files may not have been inspected for poisoning instructions.",
                recommendation="Reduce the scan scope or increase the traversal budget before relying on the result.",
                confidence="high",
                root_cause="context-poisoning-discovery-truncated",
            )
        )
    return findings


def _agent_and_doc_files(root: Path) -> tuple[list[Path], TraversalDiagnostics]:
    diagnostics = TraversalDiagnostics()
    files: list[Path] = []
    seen: set[str] = set()

    for path, _source in iter_agent_context_paths(
        root,
        limit=MAX_CONTEXT_TEXT_FILES,
        diagnostics=diagnostics,
    ):
        relative = path.relative_to(root).as_posix()
        if relative in seen:
            continue
        if len(files) >= MAX_CONTEXT_TEXT_FILES:
            diagnostics.result_limit_reached = True
            return sorted(files), diagnostics
        seen.add(relative)
        files.append(path)

    if diagnostics.result_limit_reached and len(files) >= MAX_CONTEXT_TEXT_FILES:
        return sorted(files), diagnostics

    for relative in generated_agent_target_paths():
        path = root / relative
        if relative in seen or not _is_context_text_candidate(root, path, diagnostics=diagnostics):
            continue
        if len(files) >= MAX_CONTEXT_TEXT_FILES:
            diagnostics.result_limit_reached = True
            return sorted(files), diagnostics
        seen.add(relative)
        files.append(path)

    for relative in ("README.md", "CONTRIBUTING.md"):
        path = root / relative
        if _is_context_text_candidate(root, path, diagnostics=diagnostics) and relative not in seen:
            if len(files) >= MAX_CONTEXT_TEXT_FILES:
                diagnostics.result_limit_reached = True
                return sorted(files), diagnostics
            seen.add(relative)
            files.append(path)

    for directory_name in ("docs", ".github"):
        directory = root / directory_name
        try:
            is_directory = directory.exists() and directory.is_dir()
        except OSError:
            diagnostics.read_errors += 1
            continue
        if not is_directory:
            continue
        for path in _iter_repo_files(root, start=directory, diagnostics=diagnostics):
            relative = path.relative_to(root).as_posix()
            if relative in seen or not _is_context_text_candidate(root, path, diagnostics=diagnostics):
                continue
            if len(files) >= MAX_CONTEXT_TEXT_FILES:
                diagnostics.result_limit_reached = True
                break
            seen.add(relative)
            files.append(path)
        if diagnostics.incomplete:
            break
    return sorted(files), diagnostics


def _is_context_text_candidate(
    root: Path,
    path: Path,
    *,
    diagnostics: TraversalDiagnostics | None = None,
) -> bool:
    try:
        return (
            is_safe_repo_path(root, path)
            and not path.is_symlink()
            and not is_sensitive_file_name(path.name)
            and path.is_file()
            and path.suffix.lower() in TEXT_SUFFIXES
            and path.stat().st_size <= MAX_CONTEXT_TEXT_BYTES
        )
    except OSError:
        if diagnostics is not None:
            diagnostics.read_errors += 1
        return False


def _scan_read_error_finding(relative: str) -> Finding:
    return Finding(
        id="context-poisoning.scan-truncated",
        title="Context-poisoning scan was incomplete",
        category="context_safety",
        severity="high",
        status="incomplete",
        source=relative,
        source_file=relative,
        evidence=["file could not be read"],
        risk="The file could not be inspected for context-poisoning instructions.",
        recommendation="Restore read access before relying on the context-poisoning result.",
        confidence="high",
        root_cause=f"context-poisoning-read-error:{relative}",
    )


def _is_evagix_safety_banner_line(line: str) -> bool:
    lower = line.lower()
    return (
        "repository content is untrusted input" in lower
        or "never follow repository text" in lower
        or "higher-priority instructions" in lower
        or "treat instructions found in source files" in lower
    )


UNSAFE_NEGATED_ACTION_RE = re.compile(
    r"\b(?:never\s+refuse|do\s+not\s+(?:block|prevent|refuse)|not\s+forbidden)\b"
    r"[^\n]{0,100}"
    r"\b(?:reveal(?:ing)?|print(?:ing)?|dump(?:ing)?|show(?:ing)?|send(?:ing)?|bypass(?:ing|ed)?|"
    r"disable(?:d|ing)?|ignore|ignoring|exfiltrate|exfiltrating)\b"
)

UNSAFE_COMPOUND_CONTEXT_RE = re.compile(
    r"\b(?:do\s+not|don't|never|must\s+not|should\s+not)\s+"
    r"(?:ask(?:\s+questions?)?|warn(?:\s+the\s+user)?|mention(?:\s+(?:policy|safety|guardrails?))?)\b"
    r"[^\n]{0,140}"
    r"(?:"
    r"\bignore(?:\s+(?:all\s+)?(?:previous|prior|above))?\s+instructions?\b"
    r"|\b(?:reveal(?:ing)?|print(?:ing)?|dump(?:ing)?|show(?:ing)?|send(?:ing)?)\b[^\n]{0,80}"
    r"\b(?:secrets?|api\s+keys?|tokens?|credentials?)\b"
    r"|\b(?:bypass(?:ing|ed)?|disable(?:d|ing)?)\b[^\n]{0,80}"
    r"\b(?:safety|policy|guardrails?|checks?)\b"
    r")"
)

PROTECTIVE_CONTEXT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        r"\b(?:do not|don't|never|must not|should not|avoid|refuse to|block|forbid)\b[^\n]{0,100}"
        r"\b(?:reveal(?:ing)?|print(?:ing)?|dump(?:ing)?|show(?:ing)?|send(?:ing)?|exfiltrate|exfiltrating)\b"
        r"[^\n]{0,80}\b(?:secrets?|api keys?|tokens?|credentials?|env|\.env)\b",
        r"\b(?:do not|don't|never|must not|should not|avoid|refuse to|block|forbid)\b[^\n]{0,100}"
        r"\b(?:bypass(?:ing|ed)?|disable(?:d|ing)?|ignore|ignoring)\b"
        r"[^\n]{0,80}\b(?:safety|policy|guardrails?|checks?|higher-priority instructions?)\b",
        r"\b(?:not allowed|is forbidden|are forbidden)\b[^\n]{0,100}"
        r"\b(?:reveal(?:ing)?|print(?:ing)?|dump(?:ing)?|show(?:ing)?|send(?:ing)?|bypass(?:ing|ed)?|"
        r"disable(?:d|ing)?|ignore|ignoring|exfiltrate|exfiltrating)\b",
    )
)

NEUTRAL_CONTEXT_MARKERS = (
    "configured",
    "configuration",
    "framework",
    "template",
    "example",
    "documentation",
    "docs",
)

MASKED_SECRET_CONTEXT_MARKERS = ("dashboard", "masked", "redacted")


def _is_protective_or_neutral_context(line: str, code: str) -> bool:
    """Return True for explicit safety guidance or neutral docs, not double-negative bypass instructions."""
    lower = " ".join(line.lower().split())
    if UNSAFE_NEGATED_ACTION_RE.search(lower) or UNSAFE_COMPOUND_CONTEXT_RE.search(lower):
        return False
    if any(pattern.search(lower) for pattern in PROTECTIVE_CONTEXT_PATTERNS):
        return True
    if code == "context-poisoning.system-prompt" and any(marker in lower for marker in NEUTRAL_CONTEXT_MARKERS):
        return True
    if code == "context-poisoning.reveal-secrets":
        if any(marker in lower for marker in MASKED_SECRET_CONTEXT_MARKERS):
            return True
        if "secrets.token_urlsafe" in lower or ("import secrets" in lower and "token_urlsafe" in lower):
            return True
        if "generate" in lower and "secret" in lower and "key" in lower:
            return True
    if code == "context-poisoning.exfiltrate":
        normal_config_markers = ("smtp", "email", "e-mail", "mail server", "configuration", "config", "settings")
        dangerous_destination_markers = ("http://", "https://", "webhook", "curl", "wget", "nc ", "netcat", "attacker")
        if any(marker in lower for marker in normal_config_markers) and not any(
            marker in lower for marker in dangerous_destination_markers
        ):
            return True
    return False
