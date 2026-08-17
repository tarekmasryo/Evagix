from __future__ import annotations

import re
import shlex
import tomllib
from pathlib import Path

from evagix.command_text import extract_shell_code_blocks, split_shell_command_sequence
from evagix.core.io import safe_read_text
from evagix.model import RepoFacts
from evagix.scanning.shared import has_python_package_metadata, setup_cfg_has_package_metadata


def _has_node_evidence(root: Path, facts: RepoFacts) -> bool:
    return (
        (root / "package.json").exists()
        or any(path.endswith("package.json") for path in facts.config_files)
        or any(pm in facts.package_managers for pm in ["npm", "pnpm", "yarn", "bun"])
    )


def _has_python_evidence(root: Path, facts: RepoFacts) -> bool:
    if (root / "setup.py").exists() or "python" in facts.languages or "pip" in facts.package_managers:
        return True
    setup_cfg = root / "setup.cfg"
    if setup_cfg.is_file():
        try:
            if setup_cfg_has_package_metadata(safe_read_text(setup_cfg, root=root)):
                return True
        except OSError:
            pass
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            return has_python_package_metadata(tomllib.loads(safe_read_text(pyproject, root=root)))
        except (OSError, tomllib.TOMLDecodeError):
            return False
    return False


def _command_supported_by_stack(root: Path, command: str, facts: RepoFacts, *, readme_text: str = "") -> bool:
    lower = command.lower()
    if _is_external_registry_install(lower):
        return True
    if lower.startswith(("npm ", "pnpm ", "yarn ", "bun ")):
        return lower.startswith(
            ("npm install", "npm ci", "pnpm install", "yarn install", "bun install")
        ) and _has_node_evidence(root, facts)
    if lower.startswith(("pip install", "python -m pip", "uv sync", "uv pip")):
        return _has_python_evidence(root, facts)
    if lower.startswith(("docker ", "docker-compose ")):
        normalized = " ".join(lower.split())
        if normalized == "docker build .":
            return "docker" in facts.container_platforms or (root / "Dockerfile").exists()
        if normalized in {"docker compose up", "docker-compose up"}:
            return "docker-compose" in facts.container_platforms or any(
                (root / name).exists()
                for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
            )
        return False
    if lower.startswith("make "):
        return (
            (root / "Makefile").exists()
            or (root / "makefile").exists()
            or _documented_makefile_generation_precedes(readme_text, lower)
        )
    return False


def _is_external_registry_install(command: str) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if len(tokens) < 4 or tokens[0] not in {"npm", "pnpm", "yarn", "bun"}:
        return False
    if tokens[1] not in {"install", "add"} or not any(token in {"-g", "--global"} for token in tokens[2:]):
        return False
    return any(not token.startswith("-") for token in tokens[2:])


def _documented_makefile_generation_precedes(text: str, command: str) -> bool:
    normalized_command = " ".join(command.split())
    for block in extract_shell_code_blocks(text):
        commands = [
            (" ".join(segment.split()).casefold(), operator)
            for line in block.splitlines()
            for segment, operator in split_shell_command_sequence(line)
        ]
        for index, (documented_command, _operator) in enumerate(commands):
            if documented_command != normalized_command:
                continue
            for generator_index, (previous, _previous_operator) in enumerate(commands[:index]):
                if not _is_makefile_generation_command(previous):
                    continue
                path_operators = (operator for _item, operator in commands[generator_index + 1 : index + 1])
                if all(operator != "||" for operator in path_operators):
                    return True
    return _documented_generation_prose_precedes(text, normalized_command)


def _is_makefile_generation_command(command: str) -> bool:
    if command.startswith(("./bootstrap", "bootstrap", "./configure", "configure")):
        return True
    return command.startswith("cmake ") and not command.startswith(("cmake --build", "cmake --install", "cmake -e"))


def _documented_generation_prose_precedes(text: str, command: str) -> bool:
    normalized = " ".join(text.casefold().split())
    command_index = normalized.find(command)
    if command_index < 0:
        return False
    preceding = normalized[max(0, command_index - 500) : command_index]
    generator = r"(?:\./)?(?:bootstrap|configure)"
    ordered_flow = (
        rf"\b(?:after|once)\s+(?:running\s+)?{generator}\b",
        rf"\b{generator}\b.{{0,160}}\b(?:completes?|finishes?|generates?|creates?|then|before)\b",
        rf"\b(?:run|execute)\s+{generator}\b.{{0,160}}\b(?:then|before)\b",
    )
    return any(re.search(pattern, preceding) for pattern in ordered_flow)
