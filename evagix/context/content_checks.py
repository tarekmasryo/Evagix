from __future__ import annotations

from evagix.context.files import LoadedAgentContextFile
from evagix.evidence import Finding
from evagix.model import RepoFacts
from evagix.utils import extract_fingerprint, is_generated


def _stale_or_tampered_generated(files: list[LoadedAgentContextFile], facts: RepoFacts) -> list[Finding]:
    findings: list[Finding] = []
    for item in files:
        if not is_generated(item.text):
            continue
        fingerprint = extract_fingerprint(item.text)
        if not fingerprint:
            findings.append(
                Finding(
                    id="agent-context.missing-fingerprint",
                    title="Generated agent context is missing an Evagix fingerprint",
                    category="agent_context",
                    severity="medium",
                    status="weak_evidence",
                    source=item.relative_path,
                    missing=["evagix fingerprint"],
                    risk="Generated context cannot be reliably compared with current repository facts.",
                    recommendation="Regenerate context with `evagix compile . --force`.",
                )
            )
    return findings


def _duplicated_instructions(files: list[LoadedAgentContextFile]) -> list[Finding]:
    seen: dict[str, list[str]] = {}
    for item in files:
        if is_generated(item.text):
            continue
        for line in item.text.splitlines():
            normalized = " ".join(line.strip().lower().split())
            if (
                len(normalized) < 50
                or normalized.startswith(("<!--", "#", "- `"))
                or "repository content is untrusted input" in normalized
                or "never follow repository text" in normalized
            ):
                continue
            seen.setdefault(normalized, []).append(item.relative_path)
    duplicates = [(line, sorted(set(paths))) for line, paths in seen.items() if len(set(paths)) >= 3]
    if not duplicates:
        return []
    line, paths = duplicates[0]
    return [
        Finding(
            id="agent-context.duplicated-instructions",
            title="Repeated instruction text appears across multiple agent files",
            category="agent_context",
            severity="low",
            status="duplicated",
            source="agent context files",
            evidence=[line[:180], "files: " + ", ".join(paths[:6])],
            risk="Large duplicated context makes agent instructions noisy and harder to review.",
            recommendation="Keep shared guidance in generated Evagix sections and move custom guidance into a small project-specific section.",
        )
    ]


def _oversized_context(files: list[LoadedAgentContextFile]) -> list[Finding]:
    generated_sizes = [len(item.text) for item in files if is_generated(item.text)]
    custom_total = sum(len(item.text) for item in files if not is_generated(item.text))
    # Tool-specific generated adapters intentionally duplicate the same governed context.
    # Count only the largest generated adapter plus custom files so strict mode does not
    # punish repositories for exporting the same context to multiple agents.
    total = custom_total + (max(generated_sizes) if generated_sizes else 0)
    if total <= 120_000:
        return []
    return [
        Finding(
            id="agent-context.overlong",
            title="Agent context files are unusually large",
            category="agent_context",
            severity="medium",
            status="noisy",
            source="agent context files",
            evidence=[f"combined context size: {total} characters"],
            risk="Overly long context can hide important setup, validation, and safety rules from AI agents.",
            recommendation="Reduce duplicated content and keep agent-facing files focused on commands, architecture, constraints, and safety rules.",
        )
    ]
