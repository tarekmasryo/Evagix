from __future__ import annotations

import re
from pathlib import Path

from evagix.command_text import extract_shell_code_blocks, strip_command_documentation_examples
from evagix.context.files import LoadedAgentContextFile
from evagix.ecosystems import command_supported_by_ecosystem
from evagix.evidence import Finding
from evagix.model import RepoFacts
from evagix.repository_intent import is_docs_or_education_repo


def _missing_validation_context(
    root: Path, files: list[LoadedAgentContextFile], facts: RepoFacts, *, strict: bool
) -> list[Finding]:
    combined = "\n".join(item.text.lower() for item in files)
    findings: list[Finding] = []
    education_repo = is_docs_or_education_repo(root, facts)
    required = [
        ("install", "setup/install command", "setup"),
        ("test", "test command", "validation"),
        ("lint", "lint command", "validation"),
        ("typecheck", "typecheck command", "validation"),
        ("build", "build command", "validation"),
    ]
    for key, label, category in required:
        detected_commands = _commands_for_kind(facts, key)
        has_detected = bool(detected_commands)
        documented_commands = _extract_commands(combined)
        has_documented = any(command.lower() in combined for command in detected_commands) or any(
            _classify_command(command) == key and command_supported_by_ecosystem(command, facts)[0]
            for command in documented_commands
        )
        optional_quality_gate = key in {"lint", "typecheck", "build"}
        if optional_quality_gate and not has_detected and not has_documented:
            continue
        if not has_detected or not has_documented:
            educational_missing_project_command = education_repo and not has_detected and key in {"install", "test"}
            if educational_missing_project_command:
                severity = "low"
            elif key == "test" and strict:
                severity = "high"
            else:
                severity = "low" if optional_quality_gate else "medium"
            findings.append(
                Finding(
                    id=f"agent-context.missing-{key}",
                    title=f"Agent context does not clearly document a {label}",
                    category="agent_context",
                    severity=severity,
                    status="suggestion" if optional_quality_gate else "missing",
                    source="agent context files",
                    evidence=[
                        "detected commands: " + (", ".join(detected_commands[:5]) if detected_commands else "none")
                    ],
                    missing=[label],
                    risk=(
                        f"AI agents may make changes without a reliable {category} path."
                        if not optional_quality_gate
                        else (
                            f"A documented {label} can improve agent workflow quality "
                            "when this repo chooses to support it."
                        )
                    ),
                    recommendation=(
                        f"Document the canonical {label} in AGENTS.md and generated agent context."
                        if not optional_quality_gate
                        else f"Add this {label} only if the repository claims or requires it."
                    ),
                    summary_only=(optional_quality_gate or educational_missing_project_command) and not has_detected,
                )
            )
    return findings


def _conflicting_commands(files: list[LoadedAgentContextFile], facts: RepoFacts) -> list[Finding]:
    command_map: dict[str, set[str]] = {
        "test": set(),
        "install": set(),
        "lint": set(),
        "typecheck": set(),
        "build": set(),
    }
    for item in files:
        for command in _extract_commands(item.text):
            kind = _classify_command(command)
            if kind:
                command_map[kind].add(command)
    findings: list[Finding] = []
    for kind, commands in command_map.items():
        normalized = {_normalize_command(command) for command in commands if command}
        families = {_command_family(command) for command in normalized}
        if len(families) <= 1:
            continue
        if normalized and all(command_supported_by_ecosystem(command, facts)[0] for command in normalized):
            # Polyglot repositories can legitimately document multiple ecosystem-specific commands.
            continue
        canonical = facts.commands.get(kind, "")
        findings.append(
            Finding(
                id=f"agent-context.conflicting-{kind}-commands",
                title=f"Conflicting {kind} commands found across agent context files",
                category="agent_context",
                severity="high" if kind == "test" else "medium",
                status="conflicting",
                source="agent context files",
                evidence=sorted(normalized)[:8],
                missing=[f"single canonical {kind} command"],
                risk="AI agents may run the wrong validation path or skip validation because instructions disagree.",
                recommendation=f"Keep one canonical {kind} command"
                + (f": `{canonical}`." if canonical else " and remove stale alternatives."),
            )
        )
    return findings


def _extract_commands(text: str) -> set[str]:
    commands: set[str] = set()
    text = re.sub(
        r"<!--\s*evagix:audit-ignore-start\s*-->.*?<!--\s*evagix:audit-ignore-end\s*-->",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = strip_command_documentation_examples(text)
    code_blocks = extract_shell_code_blocks(text)
    inline = re.findall(r"`([^`\n]{3,180})`", text)
    candidates: list[str] = []
    for block in code_blocks:
        candidates.extend(block.splitlines())
    candidates.extend(inline)
    for candidate in candidates:
        command = candidate.strip().lstrip("$> -").strip()
        lower = command.lower()
        if not command or ":" in command[:25]:
            continue
        if _looks_like_shell_command(lower):
            commands.add(command)
    return commands


def _looks_like_shell_command(lower: str) -> bool:
    prefix_checks = (
        "npm ",
        "pnpm ",
        "yarn ",
        "bun ",
        "pip ",
        "python -m pip ",
        "python -m pytest",
        "ruff ",
        "make ",
        "uv ",
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
        "docker ",
        "docker-compose ",
    )
    if lower.startswith(prefix_checks):
        return True
    exact_or_with_args = ("pytest", "mypy", "pyright", "printenv")
    return any(lower == item or lower.startswith(f"{item} ") for item in exact_or_with_args)


def _classify_command(command: str) -> str:
    lower = command.lower()
    if " install" in f" {lower}" or lower.startswith(("pip install", "python -m pip", "uv sync", "uv pip")):
        return "install"
    if (
        "test" in lower
        or "pytest" in lower
        or lower.startswith(("go test", "cargo test", "mvn test", "dotnet test", "composer test", "vendor/bin/phpunit"))
        or "rspec" in lower
    ):
        return "test"
    if (
        "ruff" in lower
        or "flake8" in lower
        or "eslint" in lower
        or "pylint" in lower
        or "clippy" in lower
        or lower.startswith(("go vet", "terraform validate"))
    ):
        return "lint"
    if any(
        token in lower
        for token in [
            "mypy",
            "pyright",
            "tsc",
            "typecheck",
            "type-check",
            "check-types",
            "test-types",
            "lint-typescript",
        ]
    ):
        return "typecheck"
    if re.search(r"(?:^|\s)(?:types|typescript)(?:\s|$)", lower):
        return "typecheck"
    if (
        "build" in lower
        or lower.startswith(("cargo build", "go build", "dotnet build", "gradle build", "./gradlew build"))
        or "mvn package" in lower
    ):
        return "build"
    return ""


def _command_family(command: str) -> str:
    lower = command.lower()
    if "pytest" in lower:
        return "pytest"
    if lower.startswith("python -m pip") or lower.startswith("pip ") or lower.startswith("uv "):
        return "python-packaging"
    if lower.startswith("npm "):
        return "npm"
    if lower.startswith("pnpm "):
        return "pnpm"
    if lower.startswith("yarn "):
        return "yarn"
    if lower.startswith("make "):
        return "make"

    if lower.startswith("go "):
        return "go"
    if lower.startswith("cargo "):
        return "cargo"
    if lower.startswith("mvn "):
        return "maven"
    if lower.startswith(("gradle ", "./gradlew ")):
        return "gradle"
    if lower.startswith("dotnet "):
        return "dotnet"
    if lower.startswith(("composer ", "vendor/bin/phpunit")):
        return "composer"
    if lower.startswith("bundle "):
        return "bundler"
    if lower.startswith("terraform "):
        return "terraform"
    if lower.startswith(("docker ", "docker-compose ")):
        return "docker"
    if "ruff" in lower:
        return "ruff"
    if "mypy" in lower or "pyright" in lower:
        return "typecheck"
    return lower.split()[0] if lower.split() else lower


def _normalize_command(command: str) -> str:
    return " ".join(command.strip().split())


def _commands_for_kind(facts: RepoFacts, kind: str) -> list[str]:
    values: list[str] = []
    for name, command in facts.commands.items():
        if name == kind or name.endswith(f"_{kind}"):
            values.append(_normalize_command(command))
    return sorted(set(item for item in values if item))
