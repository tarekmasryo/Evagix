from __future__ import annotations

from pathlib import Path

from evagix.command_safety import (
    scan_dangerous_commands,
    scan_package_script_dangers,
    scan_task_recipe_dangers,
)
from evagix.context.command_checks import _conflicting_commands, _missing_validation_context
from evagix.context.content_checks import (
    _duplicated_instructions,
    _oversized_context,
    _stale_or_tampered_generated,
)
from evagix.context.files import (
    LoadedAgentContextFile,
    _agent_context_files,
    _unsafe_context_paths,
    invalid_agent_context_findings,
    truncated_agent_context_findings,
)
from evagix.evidence import Finding
from evagix.model import RepoFacts
from evagix.prompt_injection import scan_context_poisoning


def audit_context_quality(root: Path, facts: RepoFacts, *, strict: bool = False) -> list[Finding]:
    files = _agent_context_files(root)
    findings: list[Finding] = []
    findings.extend(_unsafe_context_paths(root))
    findings.extend(invalid_agent_context_findings(root, files))
    findings.extend(truncated_agent_context_findings(files))
    readable_files = [item for item in files if not item.invalid_encoding and not item.read_error]
    if not readable_files:
        if findings:
            return findings
        findings.append(
            Finding(
                id="agent-context.not-configured",
                title="No agent context files were found",
                category="agent_context",
                severity="low",
                status="not_configured",
                source="repository root",
                evidence=["No supported agent context files were detected."],
                risk="This repository has not opted into agent-context workflows; this is informational, not a repository failure.",
                recommendation="Add AGENTS.md or enable Evagix-managed context only if this repo targets AI coding-agent workflows.",
                summary_only=True,
            )
        )
        return findings

    findings.extend(_missing_validation_context(root, readable_files, facts, strict=strict))
    findings.extend(_conflicting_commands(readable_files, facts))
    findings.extend(_stale_or_tampered_generated(readable_files, facts))
    findings.extend(_duplicated_instructions(readable_files))
    findings.extend(_oversized_context(readable_files))
    findings.extend(scan_dangerous_commands(root, paths=[item.path for item in readable_files]))
    findings.extend(scan_package_script_dangers(root))
    findings.extend(scan_task_recipe_dangers(root))
    findings.extend(scan_context_poisoning(root, paths=[item.path for item in readable_files]))
    return findings


__all__ = ["LoadedAgentContextFile", "audit_context_quality"]
