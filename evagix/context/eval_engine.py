from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from evagix.config import CustomTarget
from evagix.context.eval_models import ContextCheck, ContextEvaluation
from evagix.context_quality import audit_context_quality
from evagix.core.io import safe_read_text_result
from evagix.evidence import Finding
from evagix.model import RepoFacts
from evagix.renderers import DEFAULT_TARGETS, TARGETS
from evagix.scanners.agent_files import discover_agent_files
from evagix.utils import extract_fingerprint, is_generated

_SEVERITY_PENALTIES = {"critical": 40, "high": 25, "medium": 12, "low": 3}
_MAX_CONTEXT_TARGET_CHARS = 1_000_000


def _finding_check_status(severity: str) -> str:
    return "fail" if severity in {"critical", "high"} else "warn"


def _apply_finding_penalties(score: int, findings: Sequence[Finding]) -> int:
    for finding in findings:
        severity = getattr(finding, "severity", "low")
        score -= _SEVERITY_PENALTIES.get(severity, 3)
    return max(0, min(100, score))


def _checks_from_findings(findings: Sequence[Finding]) -> list[ContextCheck]:
    checks: list[ContextCheck] = []
    for finding in findings[:20]:
        checks.append(
            ContextCheck(
                getattr(finding, "id", "context-finding"),
                _finding_check_status(getattr(finding, "severity", "low")),
                getattr(finding, "title", "Context finding"),
            )
        )
    return checks


def _finding_dicts(findings: Sequence[Finding]) -> list[dict[str, object]]:
    return [item.to_dict() for item in findings]


def _drift_findings(
    root: Path, facts: RepoFacts, target_keys: list[str] | None, custom_targets: list[CustomTarget] | None
) -> list[Finding]:
    from evagix.validators import check_repo

    check = check_repo(root, facts, target_keys=target_keys, custom_targets=custom_targets, fail_on_stale=True)
    findings: list[Finding] = []
    if check.stale_targets:
        findings.append(
            Finding(
                id="generated-context-drift",
                title="Generated Evagix context is stale",
                category="agent_context",
                severity="high",
                status="fail",
                source="generated context fingerprints",
                evidence=list(check.stale_targets),
                risk="AI agents may follow stale commands, repository facts, or safety rules.",
                recommendation="Run `evagix compile .`, review the diff, and commit refreshed generated context.",
                metadata={"affected_targets": list(check.stale_targets)},
            )
        )
    if check.tampered_targets:
        findings.append(
            Finding(
                id="generated-context-tampered",
                title="Generated Evagix context was modified manually",
                category="agent_context",
                severity="high",
                status="fail",
                source="generated context files",
                evidence=list(check.tampered_targets),
                risk="AI agents may follow modified generated instructions that no longer match repository evidence.",
                recommendation="Run `evagix compile .` or move intentional custom instructions outside generated files.",
                metadata={"affected_targets": list(check.tampered_targets)},
            )
        )
    if check.unmanaged_targets:
        findings.append(
            Finding(
                id="generated-context-unmanaged",
                title="Configured Evagix context target is not managed by Evagix",
                category="agent_context",
                severity="high",
                status="fail",
                source="configured targets",
                evidence=list(check.unmanaged_targets),
                risk="Evagix cannot safely update or validate configured files that do not retain generated ownership metadata.",
                recommendation="Move the user-owned files, choose different target paths, or review and regenerate them with `evagix compile --force`.",
                metadata={"affected_targets": list(check.unmanaged_targets)},
            )
        )
    if check.missing_targets:
        findings.append(
            Finding(
                id="generated-context-missing",
                title="Requested generated Evagix context target is missing",
                category="agent_context",
                severity="medium",
                status="fail",
                source="configured targets",
                missing=list(check.missing_targets),
                risk="Configured agent context exports are not present for agents or CI to consume.",
                recommendation="Run `evagix compile .` for the configured targets.",
                metadata={"affected_targets": list(check.missing_targets)},
            )
        )
    if check.truncated_targets:
        findings.append(
            Finding(
                id="generated-context-truncated",
                title="Generated Evagix context exceeded the verification read limit",
                category="agent_context",
                severity="high",
                status="fail",
                source="generated context files",
                evidence=list(check.truncated_targets),
                risk="Evagix cannot verify the complete content of oversized generated context targets.",
                recommendation="Reduce or split the generated targets before relying on the evaluation.",
                metadata={"affected_targets": list(check.truncated_targets)},
            )
        )
    if check.invalid_encoding_targets:
        findings.append(
            Finding(
                id="generated-context-invalid-encoding",
                title="Generated Evagix context is not valid UTF-8",
                category="agent_context",
                severity="high",
                status="fail",
                source="generated context files",
                evidence=list(check.invalid_encoding_targets),
                risk="Evagix could not inspect the complete generated context without discarding undecodable bytes.",
                recommendation="Convert the targets to valid UTF-8, review them, and rerun the evaluation.",
                metadata={"affected_targets": list(check.invalid_encoding_targets)},
            )
        )
    return findings


def evaluate_context(
    root: Path,
    facts: RepoFacts,
    *,
    strict: bool = False,
    target_keys: list[str] | None = None,
    custom_targets: list[CustomTarget] | None = None,
) -> ContextEvaluation:
    present, missing, texts, truncated = _collect_present_generated_targets_with_diagnostics(root)
    if not present:
        return _evaluate_external_or_missing_context(root, facts, strict=strict)
    return _evaluate_generated_context(
        root,
        facts,
        present=present,
        missing=missing,
        texts=texts,
        truncated=truncated,
        strict=strict,
        target_keys=target_keys,
        custom_targets=custom_targets,
    )


def _collect_present_generated_targets(root: Path) -> tuple[list[str], list[str], list[str]]:
    return _collect_present_generated_targets_with_diagnostics(root)[:3]


def _collect_present_generated_targets_with_diagnostics(
    root: Path,
) -> tuple[list[str], list[str], list[str], list[str]]:
    present: list[str] = []
    missing: list[str] = []
    texts: list[str] = []
    truncated: list[str] = []
    targets = dict(DEFAULT_TARGETS)
    for key, target in TARGETS.items():
        path = root / target
        if not path.exists():
            continue
        try:
            read_result = safe_read_text_result(
                path,
                root=root,
                max_chars=_MAX_CONTEXT_TARGET_CHARS,
            )
        except (OSError, UnicodeError):
            continue
        if is_generated(read_result.text):
            targets[key] = target
    for target in targets.values():
        path = root / target
        if path.exists():
            try:
                read_result = safe_read_text_result(
                    path,
                    root=root,
                    max_chars=_MAX_CONTEXT_TARGET_CHARS,
                )
                texts.append(read_result.text)
                present.append(target)
                if read_result.truncated:
                    truncated.append(target)
            except (OSError, UnicodeError):
                missing.append(target)
        else:
            missing.append(target)
    return present, missing, texts, truncated


def _evaluate_external_or_missing_context(root: Path, facts: RepoFacts, *, strict: bool) -> ContextEvaluation:
    discovered = discover_agent_files(root)
    if discovered:
        checks = [
            ContextCheck(
                "external-agent-context",
                "warn",
                "External/user-owned agent context files were detected. Evagix-managed generated context is not enabled.",
            )
        ]
        present_external = [item.path for item in discovered]
    else:
        checks = [
            ContextCheck(
                "agent-context-not-configured",
                "warn",
                "No generated agent instruction files were found. This does not mean the repository is broken; "
                "it means Evagix-managed agent context is not enabled yet.",
            )
        ]
        present_external = []
    strict_findings = audit_context_quality(root, facts, strict=strict) if strict else []
    if not discovered:
        strict_findings = [finding for finding in strict_findings if finding.id != "agent-context.not-configured"]
    checks.extend(_checks_from_findings(strict_findings))
    return ContextEvaluation(
        score=None,
        score_type="unscored_external_context" if discovered else "unscored_missing_context",
        management="external" if discovered else "missing",
        target_count=len(present_external),
        present_targets=present_external,
        missing_targets=[],
        checks=checks,
        findings=_finding_dicts(strict_findings),
    )


def _evaluate_generated_context(
    root: Path,
    facts: RepoFacts,
    *,
    present: list[str],
    missing: list[str],
    texts: list[str],
    truncated: list[str],
    strict: bool,
    target_keys: list[str] | None,
    custom_targets: list[CustomTarget] | None,
) -> ContextEvaluation:
    combined = "\n".join(texts)
    checks = [_generated_marker_check(texts), _fingerprint_check(texts), *_structured_context_checks(combined, facts)]
    if truncated:
        checks.append(
            ContextCheck(
                "generated-context-read-limit",
                "fail",
                "Generated context verification was truncated for: " + ", ".join(truncated),
            )
        )
    drift_findings = _drift_findings(root, facts, target_keys, custom_targets)
    strict_findings = audit_context_quality(root, facts, strict=strict) if strict else []
    all_findings = [*drift_findings, *strict_findings]
    checks.extend(_checks_from_findings(all_findings))
    score = _score_generated_context(missing=missing, checks=checks, findings=all_findings, strict=strict)
    return ContextEvaluation(
        score=score,
        score_type="static_structural",
        management="evagix",
        target_count=len(present),
        present_targets=present,
        missing_targets=missing,
        checks=checks,
        findings=_finding_dicts(all_findings),
    )


def _generated_marker_check(texts: list[str]) -> ContextCheck:
    generated_count = sum(1 for text in texts if is_generated(text))
    return ContextCheck(
        "generated-markers",
        "pass" if generated_count == len(texts) else "warn",
        f"{generated_count}/{len(texts)} present target(s) include Evagix generated markers.",
    )


def _fingerprint_check(texts: list[str]) -> ContextCheck:
    fingerprint_count = sum(1 for text in texts if extract_fingerprint(text))
    return ContextCheck(
        "fingerprints",
        "pass" if fingerprint_count == len(texts) else "warn",
        f"{fingerprint_count}/{len(texts)} present target(s) include a fingerprint.",
    )


def _score_generated_context(
    *, missing: list[str], checks: list[ContextCheck], findings: list[Finding], strict: bool
) -> int:
    score = 100
    if missing:
        score -= min(35, len(missing) * 5)
    finding_ids = {getattr(finding, "id", "") for finding in findings}
    for item in checks:
        if item.name in finding_ids:
            continue
        if item.status == "fail":
            score -= 20
        elif item.status == "warn":
            score -= 10 if strict else 8
    return _apply_finding_penalties(max(0, min(100, score)), findings)


def _structured_context_checks(text: str, facts: RepoFacts) -> list[ContextCheck]:
    return [
        _section_check(
            "project-context",
            text,
            headings=["project context", "repository summary"],
            required=[facts.root_name.lower(), "languages"],
        ),
        _section_check(
            "setup-commands",
            text,
            headings=["common commands", "commands", "setup"],
            required=["install"],
            require_command_markup=True,
        ),
        _section_check(
            "validation-commands",
            text,
            headings=["common commands", "testing policy", "validation"],
            required=["test", "lint", "typecheck"],
            require_command_markup=True,
        ),
        _section_check(
            "safety-rules",
            text,
            headings=["safety rules", "forbidden actions", "change review policy"],
            required=["do not", "approval", "risk"],
        ),
        _section_check(
            "risk-boundaries",
            text,
            headings=["safety rules", "forbidden actions", "repository map"],
            required=["secret", "migration", "dataset", "model", "artifact"],
        ),
    ]


def _section_check(
    name: str,
    text: str,
    *,
    headings: list[str],
    required: list[str],
    require_command_markup: bool = False,
) -> ContextCheck:
    lower_text = text.lower()
    sections = [_extract_section(lower_text, heading) for heading in headings]
    sections = [section for section in sections if section]
    if not sections:
        return ContextCheck(name, "warn", f"No structured section found for: {', '.join(headings[:3])}.")

    section_text = "\n".join(sections)
    matches = [item for item in required if item and item.lower() in section_text]
    has_command_markup = not require_command_markup or (
        "`" in section_text or "```" in section_text or "- " in section_text
    )
    if matches and has_command_markup:
        return ContextCheck(name, "pass", f"Structured evidence found: {', '.join(sorted(set(matches))[:6])}.")
    if matches:
        return ContextCheck(name, "warn", "Section exists, but command-like markup was not clear.")
    return ContextCheck(name, "warn", "Section exists, but expected evidence was not found in that section.")


def _extract_section(text: str, heading: str) -> str:
    marker = f"## {heading.lower()}"
    start = text.find(marker)
    if start == -1:
        return ""
    next_start = text.find("\n## ", start + len(marker))
    if next_start == -1:
        return text[start:]
    return text[start:next_start]
