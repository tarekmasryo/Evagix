from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from evagix.ecosystems.profiles import ECOSYSTEM_PROFILES, EcosystemDetection
from evagix.ecosystems.utils import _detections_for, _strip_cd, _strip_shell_prefix, _support_summary
from evagix.model import RepoFacts


def command_supported_by_ecosystem(command: str, facts: RepoFacts) -> tuple[bool, str]:
    lower = _normalize_evidence_command(_strip_shell_prefix(command))
    command_values = {_normalize_evidence_command(value) for value in facts.commands.values()}
    if lower in command_values:
        return True, "documented command matches detected repository command"

    detections = list(getattr(facts, "ecosystems", []) or [])
    if lower.startswith(("npm ", "pnpm ", "yarn ", "bun ")):
        return _node_command_supported(lower, detections)
    if lower.startswith(
        ("pip ", "python -m pip", "uv ", "pytest", "python -m pytest", "ruff ", "mypy", "pyright", "python -m build")
    ):
        return _python_command_supported(lower, detections, facts)
    if lower.startswith("go "):
        return _ecosystem_command_supported(lower, detections, "go")
    if lower.startswith("cargo "):
        return _ecosystem_command_supported(lower, detections, "rust")
    if lower.startswith("mvn "):
        return _ecosystem_command_supported(lower, detections, "java_maven")
    if lower.startswith(("gradle ", "./gradlew ")):
        return _ecosystem_command_supported(lower, detections, "java_gradle")
    if lower.startswith("dotnet "):
        return _ecosystem_command_supported(lower, detections, "dotnet")
    if lower.startswith(("composer ", "vendor/bin/phpunit")):
        return _ecosystem_command_supported(lower, detections, "php")
    if lower.startswith(("bundle ", "rake ")):
        return _ecosystem_command_supported(lower, detections, "ruby")
    if lower.startswith(("docker ", "docker-compose ")):
        return _docker_command_supported(lower, detections)
    if lower.startswith("terraform "):
        return _ecosystem_command_supported(lower, detections, "terraform")
    if lower.startswith("make "):
        return any("Makefile" in item for item in facts.config_files), "Makefile detected"
    return False, "no matching ecosystem evidence"


def ecosystem_payload(detections: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in detections:
        if hasattr(item, "to_dict"):
            rows.append(item.to_dict())
        else:
            rows.append(asdict(item))
    return rows


def support_matrix_rows() -> list[dict[str, str]]:
    rows = []
    for profile in ECOSYSTEM_PROFILES.values():
        rows.append(
            {
                "ecosystem": profile.name,
                "support": profile.support,
                "checks": _support_summary(profile),
            }
        )
    rows.append(
        {
            "ecosystem": "Unknown / unsupported ecosystems",
            "support": "general",
            "checks": "README evidence, docs drift, agent-context quality, safety, CI/workflow evidence",
        }
    )
    return rows


def _ecosystem_command_supported(
    lower: str, detections: list[EcosystemDetection], ecosystem_id: str
) -> tuple[bool, str]:
    matches = _detections_for(detections, ecosystem_id)
    if not matches:
        return False, f"no {ecosystem_id} ecosystem evidence"
    for detection in matches:
        values = {_normalize_evidence_command(value) for value in detection.commands.values()}
        if lower in values:
            return True, f"{detection.name} command evidence from {', '.join(detection.evidence[:2])}"
    return False, f"no {matches[0].name} command evidence matches the documented command"


def _docker_command_supported(lower: str, detections: list[EcosystemDetection]) -> tuple[bool, str]:
    supported, reason = _ecosystem_command_supported(lower, detections, "docker")
    if supported:
        return supported, reason
    matches = _detections_for(detections, "docker")
    compose_evidence = any(
        evidence.rsplit("/", 1)[-1] in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}
        for detection in matches
        for evidence in detection.evidence
    )
    if compose_evidence and lower in {"docker compose up", "docker-compose up"}:
        return True, "Docker Compose command evidence detected"
    return False, reason


def _node_command_supported(lower: str, detections: list[EcosystemDetection]) -> tuple[bool, str]:
    matches = _detections_for(detections, "node")
    if not matches:
        return False, "no package.json evidence"
    kind = _command_kind(lower)
    if kind in {"install", "dev", "run"}:
        return True, "Node package evidence detected"
    for detection in matches:
        stripped_values = {_strip_cd(value).lower() for value in detection.commands.values()}
        if lower in stripped_values or lower in {value.lower() for value in detection.commands.values()}:
            return True, f"package.json script evidence from {', '.join(detection.evidence[:2])}"
        if kind and kind in detection.commands:
            detected_command = _strip_cd(detection.commands[kind]).lower()
            detected_script = detected_command.split()[-1]
            tokens = lower.split()
            requested_script = tokens[-1] if tokens else lower

            # Support README commands that pass extra arguments to a known package script,
            # for example: `yarn run test --watch` when package.json has `test`.
            if requested_script == detected_script or detected_script in tokens:
                return True, f"package.json script evidence for {kind}"
    return False, f"no package.json script evidence for {kind or lower}"


def _python_command_supported(lower: str, detections: list[EcosystemDetection], facts: RepoFacts) -> tuple[bool, str]:
    matches = _detections_for(detections, "python")
    if not matches:
        return False, "no Python packaging evidence"
    if lower.startswith(("pip ", "python -m pip", "uv ")):
        return True, "Python packaging evidence detected"
    if "pytest" in lower:
        requested = _normalize_python_test_command(lower)
        detected = {
            _normalize_python_test_command(_normalize_evidence_command(command))
            for detection in matches
            for command in detection.commands.values()
        }
        if requested in detected:
            return True, "Python test command matches detected command evidence"
        if requested == "pytest" and (any("test" in detection.commands for detection in matches) or facts.test_paths):
            return True, "Python test command evidence detected"
        return False, "pytest command does not match detected test command evidence"
    if lower.startswith("ruff "):
        return any("ruff" in detection.tools for detection in matches), "ruff evidence detected"
    if lower.startswith(("mypy", "pyright")):
        return any("typecheck" in detection.commands for detection in matches), "typecheck evidence detected"
    if lower == "python -m build":
        return any("build" in detection.commands for detection in matches), "Python build evidence detected"
    return True, "Python ecosystem detected"


def _normalize_evidence_command(command: str) -> str:
    return " ".join(_strip_cd(command).lower().split())


def _normalize_python_test_command(command: str) -> str:
    return re.sub(r"^python\s+-m\s+pytest\b", "pytest", command)


def _command_kind(lower: str) -> str:
    if "install" in lower or lower.startswith(
        ("npm ci", "go mod download", "dotnet restore", "bundle install", "composer install", "terraform init")
    ):
        return "install"
    if "test" in lower or "pytest" in lower or "phpunit" in lower or "rspec" in lower:
        return "test"
    if "build" in lower or "package" in lower:
        return "build"
    if "lint" in lower or "clippy" in lower or "vet" in lower or "validate" in lower:
        return "lint"
    if any(
        token in lower
        for token in [
            "typecheck",
            "type-check",
            "check",
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
    if "start" in lower or "dev" in lower:
        return "dev"
    return ""
