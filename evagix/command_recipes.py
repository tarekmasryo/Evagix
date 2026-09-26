from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from evagix.command_analysis import analyze_command
from evagix.command_shell import basename, executable_index, split_shell_segments, tokenize, wrapper_payload
from evagix.core.io import is_safe_repo_path, safe_read_text_result
from evagix.core.paths import repo_relative as _safe_relative
from evagix.evidence import Finding
from evagix.scanner_utils import TraversalDiagnostics, _iter_named_files
from evagix.text_diagnostics import invalid_utf8_finding

MAX_MANIFEST_CHARS = 400_000
MAX_SCRIPT_REFERENCES = 100


def scan_package_script_dangers(root: Path) -> list[Finding]:
    """Detect dangerous shell fragments hidden behind package-manager scripts."""

    findings: list[Finding] = []
    inspected: set[str] = set()
    package_files, diagnostics = _iter_package_json_files(root)
    for package_json in package_files:
        relative = _safe_relative(root, package_json)
        try:
            read_result = safe_read_text_result(
                package_json,
                root=root,
                max_chars=MAX_MANIFEST_CHARS,
            )
        except UnicodeError:
            findings.append(
                invalid_utf8_finding(
                    root,
                    package_json,
                    scanner="Package script scan",
                    category="command_safety",
                )
            )
            continue
        except OSError:
            findings.append(_manifest_read_error_finding(relative))
            continue
        if read_result.truncated:
            findings.append(_manifest_truncated_finding(relative))
            continue
        raw = read_result.text
        try:
            data: Any = json.loads(raw)
        except json.JSONDecodeError:
            continue
        scripts = data.get("scripts") if isinstance(data, dict) else None
        if not isinstance(scripts, dict):
            continue
        for script_name, script_value in sorted(scripts.items()):
            if not isinstance(script_value, str):
                continue
            findings.extend(
                _recipe_findings(
                    relative=relative,
                    recipe_name=str(script_name),
                    recipe_value=script_value,
                    source_line=_line_number_for_script(raw, str(script_name)),
                    recipe_kind="package.json script",
                )
            )
        findings.extend(
            scan_referenced_script_dangers(
                root,
                {name: value for name, value in scripts.items() if isinstance(value, str)},
                sources={name: relative for name in scripts},
                cwd=package_json.parent,
                _inspected=inspected,
            )
        )
    if diagnostics.incomplete:
        findings.append(_manifest_discovery_truncated_finding(diagnostics))
    return findings


def scan_task_recipe_dangers(root: Path) -> list[Finding]:
    """Detect dangerous commands hidden behind supported Makefile and justfile targets."""

    findings: list[Finding] = []
    inspected: set[str] = set()
    for filename, parser, kind in (
        ("Makefile", _parse_makefile_recipes, "Makefile target"),
        ("justfile", _parse_justfile_recipes, "justfile recipe"),
    ):
        path = root / filename
        if not path.exists() or not path.is_file():
            continue
        try:
            read_result = safe_read_text_result(
                path,
                root=root,
                max_chars=MAX_MANIFEST_CHARS,
            )
        except UnicodeError:
            findings.append(
                invalid_utf8_finding(
                    root,
                    path,
                    scanner=f"{kind} scan",
                    category="command_safety",
                )
            )
            continue
        except OSError:
            findings.append(_manifest_read_error_finding(filename))
            continue
        if read_result.truncated:
            findings.append(_manifest_truncated_finding(filename))
            continue
        try:
            recipes = parser(read_result.text)
        except ValueError:
            findings.append(_reference_incomplete_finding(filename, "Unsupported Make recipe syntax."))
            continue
        uncertain_cwd = bool(
            filename == "Makefile"
            and re.search(r"(?m)^\s*\.ONESHELL\s*:", read_result.text)
            and any(
                re.search(r"(?:^|[\s;&|])(?:cd|pushd|popd|source|eval|\.)(?:\s|$)", " ".join(tokenize(value)))
                or "$" in value
                or "`" in value
                for _, value, _ in recipes
            )
        )
        if uncertain_cwd:
            findings.append(_reference_incomplete_finding(filename, ".ONESHELL directory changes are not modeled."))
        for recipe_name, recipe_value, source_line in recipes:
            findings.extend(
                _recipe_findings(
                    relative=filename,
                    recipe_name=recipe_name,
                    recipe_value=recipe_value,
                    source_line=source_line,
                    recipe_kind=kind,
                )
            )
            if filename == "Makefile" and not uncertain_cwd:
                findings.extend(
                    scan_referenced_script_dangers(
                        root,
                        {recipe_name: recipe_value},
                        sources={recipe_name: filename},
                        _inspected=inspected,
                    )
                )
    return findings


def scan_referenced_script_dangers(
    root: Path,
    commands: dict[str, str],
    *,
    sources: dict[str, str] | None = None,
    cwd: Path | None = None,
    _inspected: set[str] | None = None,
) -> list[Finding]:
    """Inspect local shell scripts referenced by commands emitted to agents."""

    findings: list[Finding] = []
    source_map = sources or {}
    inspected = _inspected if _inspected is not None else set()
    for command_name, command in sorted(commands.items()):
        source = source_map.get(command_name, "detected command")
        try:
            reference = _referenced_shell_script(command)
        except ValueError:
            findings.append(_reference_incomplete_finding(source, "Complex or unresolved local script reference."))
            continue
        if reference is None:
            continue
        path = (cwd if cwd is not None else root) / reference
        relative = _safe_relative(root, path)
        if relative in inspected:
            continue
        if len(inspected) >= MAX_SCRIPT_REFERENCES:
            findings.append(_reference_incomplete_finding(source, "Local script inspection budget exhausted."))
            break
        inspected.add(relative)
        try:
            if not is_safe_repo_path(root, path) or not path.is_file():
                findings.append(
                    _reference_incomplete_finding(source, "Local script is missing or outside path policy.")
                )
                continue
            read_result = safe_read_text_result(
                path,
                root=root,
                max_chars=MAX_MANIFEST_CHARS,
            )
        except UnicodeError:
            findings.append(
                invalid_utf8_finding(
                    root,
                    path,
                    scanner="Referenced script scan",
                    category="command_safety",
                )
            )
            continue
        except OSError:
            findings.append(_manifest_read_error_finding(relative))
            continue
        if read_result.truncated:
            findings.append(_manifest_truncated_finding(relative))
            continue
        for line_number, line in enumerate(read_result.text.splitlines(), start=1):
            candidate = line.strip()
            if not candidate or candidate.startswith(("#", "::", "rem ")):
                continue
            try:
                nested_reference = _referenced_shell_script(candidate)
            except ValueError:
                nested_reference = candidate
            if nested_reference is not None:
                findings.append(
                    _reference_incomplete_finding(relative, "Nested local script references are not modeled.")
                )
            for risk in analyze_command(candidate):
                source = source_map.get(command_name, relative)
                findings.append(
                    Finding(
                        id="dangerous-command.local-script",
                        title="Dangerous local validation script detected",
                        category="command_safety",
                        severity="high",
                        status="unsafe",
                        source=relative,
                        source_file=relative,
                        source_line=line_number,
                        evidence=[f"{command_name}: {candidate}"[:240]],
                        evidence_files=[relative],
                        confidence="high",
                        root_cause=f"local-script:{relative}:{line_number}",
                        risk=(
                            f"The command from {source} executes a local script containing unsafe shell behavior. "
                            f"{risk.risk}"
                        ),
                        recommendation="Remove the unsafe operation before publishing this script as an agent command.",
                        metadata={"command_name": command_name, "matched_rule": risk.rule_id},
                    )
                )
    return findings


def _referenced_shell_script(command: str, *, _depth: int = 0) -> str | None:
    # Deliberately support only direct invocations, never interpret shell flow.
    if _depth > 3 or len(command) > 65_536:
        raise ValueError("Reference command exceeds the analysis limit")
    if "\x00" in command:
        raise ValueError("NUL in a script reference")
    tokens = tokenize(command, strict=True)
    index = executable_index(tokens)
    if index is None:
        return None
    executable = basename(tokens[index])
    if executable == "exec":
        raise ValueError("exec wrappers are not modeled")
    args = tokens[index + 1 :]
    shells = {"bash", "sh", "zsh", "pwsh", "powershell", "cmd", "source"}
    suffixes = (".sh", ".ps1", ".cmd", ".bat")
    cmd_script = (
        executable == "cmd"
        and len(args) == 2
        and args[0].casefold() == "/c"
        and args[1].lower().endswith((".cmd", ".bat"))
    )
    payload = wrapper_payload(tokens)
    if payload is not None and not cmd_script:
        if _referenced_shell_script(payload, _depth=_depth + 1) is not None or any(
            basename(token) in shells or token.lower().endswith(suffixes) for token in args if token != payload
        ):
            raise ValueError("Wrapped local references are unsupported")
        return None
    reference_tokens: list[str] = []
    for segment in split_shell_segments(command):
        segment_tokens = tokenize(segment)
        segment_index = executable_index(segment_tokens)
        if segment_index is not None and basename(segment_tokens[segment_index]) in {"echo", "printf"}:
            # Printing arguments are data; later command segments still need inspection.
            continue
        reference_tokens.extend(segment_tokens)
    looks_local = executable == "." or any(
        basename(token) in shells or token.lower().endswith(suffixes) or token.startswith(("./", "../"))
        for token in reference_tokens
    )
    if looks_local and (re.search(r"[\r\n;&|<>\x60^()]|(?:^|\s)#", command) or "\\" in command):
        raise ValueError("Compound script references are unsupported")
    candidate: str | None = None
    if executable in {"bash", "sh", "zsh", "source", "."}:
        if args and args[0] == "--":
            args = args[1:]
        if args and args[0].startswith(("-", "+")):
            raise ValueError("Unsupported shell option before a script reference")
        candidate = args[0] if args else None
    elif executable in {"pwsh", "powershell"}:
        for position, arg in enumerate(args):
            if arg.casefold() in {"-file", "/file"} and position + 1 < len(args):
                candidate = args[position + 1]
                break
        if candidate is None:
            candidate = next((arg for arg in args if arg.lower().endswith(".ps1")), None)
    elif cmd_script:
        candidate = args[1]
    elif tokens[index].lower().endswith(suffixes):
        if "/" not in tokens[index] and "\\" not in tokens[index]:
            raise ValueError("PATH-based script resolution is unsupported")
        candidate = tokens[index]
    elif tokens[index].startswith(("./", "../", "$", "%")):
        raise ValueError("Unresolved local executable")
    if candidate is None:
        return None
    if any(marker in candidate for marker in ("$", "%", "`", "*", "?", "~")):
        raise ValueError("Dynamic script path")
    normalized = candidate.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized) or ".." in Path(normalized).parts:
        raise ValueError("Non-local script path")
    return Path(normalized).as_posix()


def _reference_incomplete_finding(source: str, reason: str) -> Finding:
    return Finding(
        id="command-safety.scan-truncated",
        title="Local recipe analysis was incomplete",
        category="command_safety",
        severity="high",
        status="incomplete",
        source=source,
        source_file=source,
        evidence=[reason],
        risk="A local recipe or script reference could not be inspected confidently.",
        recommendation="Use a direct, repository-local script reference with a fixed invoking directory.",
        confidence="high",
        root_cause=f"local-reference-incomplete:{source}:{reason}",
    )


def _recipe_findings(
    *,
    relative: str,
    recipe_name: str,
    recipe_value: str,
    source_line: int | None,
    recipe_kind: str,
) -> list[Finding]:
    findings: list[Finding] = []
    for risk in analyze_command(recipe_value):
        findings.append(
            Finding(
                id="dangerous-command.package-script",
                title=f"Dangerous {recipe_kind} detected",
                category="command_safety",
                severity="high",
                status="unsafe",
                source=relative,
                source_file=relative,
                source_line=source_line,
                evidence=[f'{recipe_kind} "{recipe_name}": {recipe_value}'[:240]],
                evidence_files=[relative],
                missing=[],
                confidence="high",
                root_cause=f"task-recipe:{relative}:{recipe_name}",
                risk=f"The `{recipe_name}` recipe expands to unsafe shell behavior. {risk.risk}",
                recommendation="Do not surface this task as an agent validation command until the recipe is safe.",
                metadata={"script": recipe_name, "matched_rule": risk.rule_id, "recipe_kind": recipe_kind},
            )
        )
    return findings


def _parse_makefile_recipes(raw: str) -> list[tuple[str, str, int]]:
    recipes: list[tuple[str, str, int]] = []
    current_target: str | None = None
    for line_number, line in enumerate(raw.splitlines(), start=1):
        line = line.lstrip(" ")
        if line.startswith(".RECIPEPREFIX"):
            raise ValueError("Custom Make recipe prefixes are unsupported")
        target_match = re.match(r"^((?:\\.|[A-Za-z0-9_.%/-])+)\s*::?(?![:=])", line)
        if target_match:
            current_target = target_match.group(1)
            remainder = line[target_match.end() :].lstrip()
            assignment = re.match(
                r"(?:(?:private|override|export|unexport)\s+)*[^\s:=+?!]+\s*(:::=|::?=|[?+!]?=)", remainder
            )
            if assignment:
                if assignment.group(1) == "!=" or re.search(r"\$[({]\s*(?:shell|eval)\b", remainder):
                    raise ValueError("Executable Make variable assignment")
                continue
            header, separator, command = remainder.partition(";")
            if re.search(r"(?<!\\)(?:\\\\)*#", header):
                continue
            if header.rstrip().endswith("\\"):
                raise ValueError("Continued Make prerequisite headers are unsupported")
            if separator:
                if re.search(r"\\(?!#)", header) or "$" in header:
                    raise ValueError("Ambiguous Make prerequisite separator")
                command = command.strip().lstrip("@-+").strip()
                if command:
                    recipes.append((current_target, command, line_number))
            continue
        if current_target and line.startswith("\t"):
            command = line.lstrip("\t@-+").strip()
            if command:
                recipes.append((current_target, command, line_number))
            continue
        if line and not line[0].isspace() and not line.lstrip().startswith("#"):
            if ":" in line and ";" in line and not re.match(r"^[^:=]+(?:::?=|:::=|[?+!]?=)", line):
                raise ValueError("Unsupported inline Make target")
            current_target = None
    return recipes


def _parse_justfile_recipes(raw: str) -> list[tuple[str, str, int]]:
    recipes: list[tuple[str, str, int]] = []
    current_target: str | None = None
    for line_number, line in enumerate(raw.splitlines(), start=1):
        target_match = re.match(r"^([A-Za-z0-9_.-]+)(?:\s+[^:]*)?\s*:\s*(?:#.*)?$", line)
        if target_match:
            current_target = target_match.group(1)
            continue
        if current_target and (line.startswith(" ") or line.startswith("\t")):
            command = line.strip().lstrip("@-").strip()
            if command and not command.startswith("#"):
                recipes.append((current_target, command, line_number))
            continue
        if line and not line[0].isspace() and not line.lstrip().startswith(("#", "set ", "import ")):
            current_target = None
    return recipes


def _iter_package_json_files(root: Path) -> tuple[list[Path], TraversalDiagnostics]:
    diagnostics = TraversalDiagnostics()
    files = _iter_named_files(root, {"package.json"}, limit=200, diagnostics=diagnostics)
    return files, diagnostics


def _line_number_for_script(raw: str, script_name: str) -> int | None:
    pattern = re.compile(r'"' + re.escape(str(script_name)) + r'"\s*:')
    match = pattern.search(raw)
    return raw.count("\n", 0, match.start()) + 1 if match else None


def _manifest_truncated_finding(relative: str) -> Finding:
    return Finding(
        id="command-safety.scan-truncated",
        title="Command manifest safety scan was truncated",
        category="command_safety",
        severity="high",
        status="incomplete",
        source=relative,
        source_file=relative,
        evidence=[f"read limit: {MAX_MANIFEST_CHARS} characters"],
        risk="Task definitions beyond the read limit were not inspected for dangerous commands.",
        recommendation="Reduce or split the manifest before relying on generated agent commands.",
        confidence="high",
        root_cause=f"command-manifest-truncated:{relative}",
    )


def _manifest_read_error_finding(relative: str) -> Finding:
    return Finding(
        id="command-safety.scan-truncated",
        title="Command manifest safety scan was incomplete",
        category="command_safety",
        severity="high",
        status="incomplete",
        source=relative,
        source_file=relative,
        evidence=["file could not be read"],
        risk="Task definitions could not be inspected for dangerous commands.",
        recommendation="Restore read access before relying on generated agent commands.",
        confidence="high",
        root_cause=f"command-manifest-read-error:{relative}",
    )


def _manifest_discovery_truncated_finding(diagnostics: TraversalDiagnostics) -> Finding:
    return Finding(
        id="command-safety.discovery-truncated",
        title="Command manifest discovery was truncated",
        category="command_safety",
        severity="high",
        status="incomplete",
        source="repository task manifests",
        evidence=[diagnostics.warning("Command manifest discovery")],
        risk="Some task manifests may not have been inspected for dangerous recipes.",
        recommendation="Reduce the scan scope or increase the traversal budget before relying on the result.",
        confidence="high",
        root_cause="command-manifest-discovery-truncated",
    )
