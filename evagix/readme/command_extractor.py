from __future__ import annotations

import re
from pathlib import Path

from evagix.command_text import (
    extract_shell_code_blocks,
    split_shell_command_chain,
    strip_command_documentation_examples,
)
from evagix.ecosystems import command_supported_by_ecosystem
from evagix.model import RepoFacts
from evagix.readme.evidence_matcher import _command_supported_by_stack
from evagix.readme.findings import ReadmeClaim
from evagix.readme.text_utils import _claim_confidence, _line_number_for_phrase, _strip_audit_ignore_blocks


def _command_claims_from_readme(root: Path, text: str, facts: RepoFacts, *, readme_path: str = "") -> list[ReadmeClaim]:
    """Detect README commands that are stale, unsupported, or scoped to the wrong ecosystem."""
    commands = _extract_readme_commands(_strip_audit_ignore_blocks(text))
    if not commands:
        return []

    claims: list[ReadmeClaim] = []
    detected_values = {value.lower() for value in facts.commands.values()}
    detected_blob = "\n".join(detected_values)

    for command in sorted(commands):
        lower = " ".join(command.lower().split())
        kind = _readme_command_kind(lower)
        if not kind:
            continue

        replacement = _best_detected_command(facts, kind)
        supported, reason = command_supported_by_ecosystem(lower, facts)
        stack_supported = _command_supported(lower, detected_values) or _command_supported_by_stack(
            root,
            lower,
            facts,
            readme_text=text,
        )
        configured_source = facts.command_sources.get(kind)
        configured_override_mismatch = (
            kind != "install"
            and not stack_supported
            and bool(replacement)
            and configured_source is not None
            and configured_source.source == "evagix.toml"
            and replacement.lower() != lower
        )
        if not configured_override_mismatch and (supported or stack_supported):
            continue

        verdict = "unsupported"
        missing = [reason]
        evidence: list[str] = []
        if replacement:
            evidence.append(f"detected {kind} command: {replacement}")
            if kind in {"test", "lint", "typecheck", "build", "run"} and lower not in detected_blob:
                verdict = "partial"
        elif _is_unmodeled_ecosystem_command(lower):
            verdict = "manual_review_required"
            missing = ["no ecosystem support is available for this documented command"]

        if replacement and replacement.lower() == lower:
            continue
        source_line = _line_number_for_phrase(text, command)
        claims.append(
            ReadmeClaim(
                claim="readme-command",
                phrase=command,
                verdict=verdict,
                evidence=evidence,
                missing_evidence=missing,
                suggestion="Update the README command to match executable command evidence from project files.",
                suggested_replacement=replacement,
                source=readme_path,
                source_file=readme_path,
                source_line=source_line,
                line_range=[source_line] if source_line else [],
                confidence=_claim_confidence(verdict, "readme-command"),
            )
        )
    return claims


def _extract_readme_commands(text: str) -> set[str]:
    commands: set[str] = set()
    text = strip_command_documentation_examples(text)
    code_blocks = extract_shell_code_blocks(text)
    inline = re.findall(r"`([^`\n]{3,160})`", text)
    candidates: list[str] = []
    for block in code_blocks:
        candidates.extend(block.splitlines())
    candidates.extend(inline)
    prefixes = (
        "npm ",
        "pnpm ",
        "yarn ",
        "bun ",
        "pip ",
        "python -m pip ",
        "python -m pytest",
        "pytest",
        "ruff ",
        "make ",
        "streamlit ",
        "docker ",
        "docker-compose ",
        "go ",
        "cargo ",
        "mvn ",
        "gradle ",
        "./gradlew ",
        "dotnet ",
        "composer ",
        "vendor/bin/phpunit",
        "bundle ",
        "terraform ",
        "swift ",
        "dart ",
        "flutter ",
        "mix ",
        "sbt ",
    )
    for candidate in candidates:
        for command in split_shell_command_chain(candidate):
            if command.startswith("#"):
                continue
            if command.lower().startswith(prefixes):
                commands.add(command)
    return commands


def _command_supported(command: str, detected_values: set[str]) -> bool:
    normalized = " ".join(command.split())
    for detected in detected_values:
        detected_normalized = " ".join(detected.split())
        if normalized == detected_normalized:
            return True
    return False


def _suggest_replacement(claim: str, phrase: str, facts: RepoFacts) -> str:
    if claim == "tested" and facts.commands.get("test"):
        return facts.commands["test"]
    if claim == "ci/cd" and not facts.ci_workflows:
        return "Add a GitHub Actions workflow that runs tests, lint, evagix check, and evagix doctor."
    if claim == "dockerized":
        if "docker-compose" in facts.container_platforms:
            return "docker compose up --build"
        if "docker" in facts.container_platforms:
            return "docker build ."
    if claim == "deployable" and (facts.commands.get("run") or facts.commands.get("dev")):
        return facts.commands.get("run") or facts.commands.get("dev", "")
    if claim == "production-ready":
        return "production-oriented" if "enterprise" in phrase.lower() else "production-minded"
    if claim == "secure":
        return "security-conscious"
    return ""


def _readme_command_kind(lower: str) -> str:
    if " install" in f" {lower}" or lower.startswith(
        ("pip install", "python -m pip", "uv sync", "uv pip", "terraform init")
    ):
        return "install"
    if "test" in lower or "pytest" in lower or "phpunit" in lower or "rspec" in lower:
        return "test"
    if any(token in lower for token in ["lint", "ruff", "eslint", "clippy", "go vet", "terraform validate"]):
        return "lint"
    if any(
        token in lower
        for token in [
            "typecheck",
            "type-check",
            "check-types",
            "test-types",
            "lint-typescript",
            "tsc",
            "mypy",
            "pyright",
        ]
    ):
        return "typecheck"
    if re.search(r"(?:^|\s)(?:types|typescript)(?:\s|$)", lower):
        return "typecheck"
    if "build" in lower or "package" in lower:
        return "build"
    if lower.startswith(
        ("npm start", "npm run dev", "pnpm dev", "yarn dev", "bun run dev", "streamlit run", "python app.py")
    ):
        return "run"
    return ""


def _best_detected_command(facts: RepoFacts, kind: str) -> str:
    if kind == "run":
        return facts.commands.get("run") or facts.commands.get("dev") or ""
    if facts.commands.get(kind):
        return facts.commands[kind]
    for name, command in sorted(facts.commands.items()):
        if name.endswith(f"_{kind}"):
            return command
    return ""


def _is_unmodeled_ecosystem_command(lower: str) -> bool:
    return lower.startswith(("swift ", "dart ", "flutter ", "mix ", "sbt "))
