from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

from evagix.commands.common import (
    _doctor,
    _facts,
    _normalize_existing_root,
    _normalize_root,
    _resolve_cli_output_path,
    _targets,
)
from evagix.commands.generation_safety import (
    GeneratedTargetInvalidEncoding,
    GeneratedTargetTooLarge,
    read_existing_generated_target,
    reject_unsafe_generated_commands,
)
from evagix.constants import DEFAULT_GITHUB_REF, DEFAULT_GITHUB_REPO
from evagix.core.io import apply_write_plan, build_write_plan
from evagix.generated_integrity import with_integrity_manifest
from evagix.onboard import render_onboarding_outputs
from evagix.profiles import normalize_profiles
from evagix.renderers import DEFAULT_TARGETS, TARGETS, render_all
from evagix.safety import WORKFLOW_INPUT_POLICY, EvagixSafetyError
from evagix.scanner import scan_repo
from evagix.scoped import scoped_outputs
from evagix.templates import BASELINE_CONFIG_TEMPLATE, EVAGIX_CONFIG_TEMPLATE, evagix_ci_workflow
from evagix.utils import facts_fingerprint, is_generated, normalize_generated_content
from evagix.validators import check_repo


def _cmd_compile(
    root: Path,
    target: list[str] | None,
    dry_run: bool,
    force: bool,
    profiles: list[str] | None = None,
) -> int:
    root = _normalize_root(root)
    facts, config = _facts(root, profiles)
    if reject_unsafe_generated_commands(root, facts):
        return 1
    target_keys = _targets(config, target)
    if target_keys is None:
        existing_generated = []
        for key, relative_path in TARGETS.items():
            path = _resolve_cli_output_path(root, relative_path)
            if not path.exists():
                continue
            try:
                if is_generated(read_existing_generated_target(root, path)):
                    existing_generated.append(key)
            except (GeneratedTargetTooLarge, GeneratedTargetInvalidEncoding) as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 1
            except OSError:
                continue
        if existing_generated:
            target_keys = list(dict.fromkeys([*DEFAULT_TARGETS.keys(), *existing_generated]))
    outputs = with_integrity_manifest(
        render_all(facts, target_keys, config.custom_targets),
        facts_fingerprint(facts.to_dict()),
    )

    planned: list[tuple[str, str]] = []
    skipped: list[str] = []
    for relative_path, content in outputs.items():
        path = _resolve_cli_output_path(root, relative_path)
        if path.exists() and not force:
            try:
                existing = read_existing_generated_target(root, path)
            except (GeneratedTargetTooLarge, GeneratedTargetInvalidEncoding) as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 1
            if not is_generated(existing):
                skipped.append(relative_path)
                continue
        planned.append((relative_path, content))

    if skipped:
        print("Planned writes:")
        for relative_path, _ in planned:
            print(f"  - {relative_path}")
        print("Skipped existing non-evagix files. Re-run with --force to overwrite:", file=sys.stderr)
        for relative_path in skipped:
            print(f"  - {relative_path}", file=sys.stderr)
        return 1

    if not dry_run:
        try:
            apply_write_plan(build_write_plan(root, dict(planned), force=True))
        except OSError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    print("Planned writes:" if dry_run else "Written:")
    for relative_path, _ in planned:
        print(f"  - {relative_path}")

    if facts.warnings:
        print("Warnings:")
        for warning in facts.warnings:
            print(f"  - {warning}")
    return 0


def _cmd_sync(root: Path, plan: bool = False, profiles: list[str] | None = None) -> int:
    root = _normalize_root(root)
    if plan:
        return _cmd_sync_plan(root, profiles=profiles)
    compile_code = _cmd_compile(root, target=None, dry_run=False, force=False, profiles=profiles)
    if compile_code != 0:
        return compile_code
    return _cmd_check(root, profiles=profiles)


def _cmd_sync_plan(root: Path, profiles: list[str] | None = None) -> int:
    facts, config = _facts(root, profiles)
    if reject_unsafe_generated_commands(root, facts):
        return 1
    outputs = with_integrity_manifest(
        render_all(facts, _targets(config, None), config.custom_targets),
        facts_fingerprint(facts.to_dict()),
    )
    will_create: list[str] = []
    will_update: list[str] = []
    fingerprint_only: list[str] = []
    will_skip: list[str] = []
    for relative_path, generated in sorted(outputs.items()):
        path = _resolve_cli_output_path(root, relative_path)
        if not path.exists():
            will_create.append(relative_path)
            continue
        try:
            existing = read_existing_generated_target(root, path)
        except (GeneratedTargetTooLarge, GeneratedTargetInvalidEncoding) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if not is_generated(existing):
            will_skip.append(relative_path)
            continue
        if normalize_generated_content(existing) == normalize_generated_content(generated):
            continue
        if _without_generated_fingerprint(existing) == _without_generated_fingerprint(generated):
            fingerprint_only.append(relative_path)
        else:
            will_update.append(relative_path)

    protected = [".env", "secrets/", "migrations/", ".git/", "node_modules/"]
    print("Evagix sync plan")
    if not will_create and not will_update and not fingerprint_only and not will_skip:
        print("No changes needed.")
        print("Will not touch:")
        for item in protected:
            print(f"  - {item}")
        return 0
    if fingerprint_only and not will_create and not will_update:
        print("Would refresh generated fingerprints only. No semantic context changes detected.")
        for item in fingerprint_only:
            print(f"  - {item}")
    print("Will create:")
    for item in will_create or ["None"]:
        print(f"  - {item}")
    print("Will update:")
    for item in will_update or ["None"]:
        print(f"  - {item}")
    print("Will not touch:")
    for item in protected:
        print(f"  - {item}")
    if will_skip:
        print("Existing non-Evagix files that would be skipped:")
        for item in will_skip:
            print(f"  - {item}")
    print("Apply with: evagix sync .")
    return 0


def _without_generated_fingerprint(content: str) -> str:
    normalized = normalize_generated_content(content)
    normalized = re.sub(r"evagix:fingerprint=[A-Za-z0-9_-]+", "evagix:fingerprint=<ignored>", normalized)
    normalized = re.sub(
        r"evagix:content-digest=[a-f0-9]{64}",
        "evagix:content-digest=<ignored>",
        normalized,
    )
    normalized = re.sub(
        r'"_evagix_content_digest": "[a-f0-9]{64}"',
        '"_evagix_content_digest": "<ignored>"',
        normalized,
    )
    normalized = re.sub(
        r'"content_digest": "[a-f0-9]{64}"',
        '"content_digest": "<ignored>"',
        normalized,
    )
    return normalized


def _cmd_check(root: Path, profiles: list[str] | None = None) -> int:
    root = _normalize_root(root)
    facts, config = _facts(root, profiles)
    result = check_repo(
        root,
        facts,
        target_keys=_targets(config, None),
        custom_targets=config.custom_targets,
        fail_on_stale=config.fail_on_stale,
    )
    print(
        "Evagix check passed." if result.ok else "Evagix check failed.",
        file=sys.stdout if result.ok else sys.stderr,
    )
    print(
        "Scope: generated context freshness and Evagix self-governance only. "
        "For full readiness, run doctor, readme-audit, and eval-context.",
        file=sys.stdout if result.ok else sys.stderr,
    )
    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 0 if result.ok else 1


def _cmd_onboard(root: Path, dry_run: bool, force: bool, profiles: list[str] | None = None) -> int:
    root = _normalize_root(root)
    facts, _ = _facts(root, profiles)
    if reject_unsafe_generated_commands(root, facts):
        return 1
    outputs = render_onboarding_outputs(root, facts)
    plan = build_write_plan(root, outputs, force=force)
    if plan.conflicts:
        print(
            f"{len(plan.conflicts)} onboarding file(s) already exist. Re-run with `evagix onboard . --force` to overwrite.",
            file=sys.stderr,
        )
        for relative_path in plan.conflicts:
            print(f"  - {relative_path}", file=sys.stderr)
        return 1
    if not dry_run:
        apply_write_plan(plan)
    print("Planned onboarding writes:" if dry_run else "Created onboarding pack:")
    for relative_path in plan.relative_paths:
        print(f"  - {relative_path}")
    return 0


def _cmd_diff(root: Path, target: list[str] | None) -> int:
    root = _normalize_root(root)
    facts, config = _facts(root)
    outputs = with_integrity_manifest(
        render_all(facts, _targets(config, target), config.custom_targets),
        facts_fingerprint(facts.to_dict()),
    )
    changed = False
    for relative_path, generated in outputs.items():
        path = _resolve_cli_output_path(root, relative_path)
        try:
            current = read_existing_generated_target(root, path) if path.exists() else ""
        except (GeneratedTargetTooLarge, GeneratedTargetInvalidEncoding) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        normalized_current = normalize_generated_content(current)
        normalized_generated = normalize_generated_content(generated)
        if normalized_current != normalized_generated:
            changed = True
            diff = difflib.unified_diff(
                normalized_current.splitlines(keepends=True),
                normalized_generated.splitlines(keepends=True),
                fromfile=f"current/{relative_path}",
                tofile=f"generated/{relative_path}",
            )
            print("".join(diff), end="")
    if not changed:
        print("No diffs.")
    return 1 if changed else 0


def _cmd_init(root: Path, force: bool, profiles: list[str] | None = None) -> int:
    root = _normalize_existing_root(root)
    path = root / "evagix.toml"
    if path.exists() and not force:
        print("evagix.toml already exists. Re-run with --force to overwrite.", file=sys.stderr)
        return 1
    try:
        selected_profiles = normalize_profiles(profiles) if profiles else scan_repo(root).active_profiles
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    profile_lines = "profiles = [" + ", ".join(repr(item) for item in selected_profiles) + "]"
    content = EVAGIX_CONFIG_TEMPLATE.format(profile_lines=profile_lines)
    try:
        apply_write_plan(build_write_plan(root, {"evagix.toml": content}, force=force))
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("Created evagix.toml")
    return 0


def _cmd_baseline(root: Path, force: bool, profiles: list[str] | None = None) -> int:
    root = _normalize_root(root)
    path = root / "evagix.toml"
    if path.exists() and not force:
        print("evagix.toml already exists. Re-run with --force to overwrite.", file=sys.stderr)
        return 1
    facts, _, report = _doctor(root, profiles)
    ignore_codes = sorted({item.code for item in report.findings if item.severity != "error"})
    try:
        selected_profiles = normalize_profiles(profiles) or facts.active_profiles or ["python-backend"]
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    content = BASELINE_CONFIG_TEMPLATE.format(
        profiles=", ".join(repr(item) for item in selected_profiles),
        ignore_codes=", ".join(repr(item) for item in ignore_codes),
    )
    try:
        apply_write_plan(build_write_plan(root, {"evagix.toml": content}, force=force))
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Created evagix.toml with {len(ignore_codes)} ignored finding code(s).")
    return 0


def _ci_install_command(
    install_mode: str,
    repo: str = DEFAULT_GITHUB_REPO,
    ref: str = DEFAULT_GITHUB_REF,
    package_version: str | None = None,
) -> str:
    return WORKFLOW_INPUT_POLICY.install_command(
        install_mode=install_mode,
        repo=repo,
        ref=ref,
        package_version=package_version,
    )


def _cmd_init_ci(
    root: Path,
    force: bool,
    fail_under: int = 80,
    install_mode: str = "github",
    repo: str = DEFAULT_GITHUB_REPO,
    ref: str = DEFAULT_GITHUB_REF,
    package_version: str | None = None,
) -> int:
    root = _normalize_existing_root(root)
    path = root / ".github" / "workflows" / "evagix.yml"
    if path.exists() and not force:
        print(".github/workflows/evagix.yml already exists. Re-run with --force to overwrite.", file=sys.stderr)
        return 1
    try:
        install_command = _ci_install_command(
            install_mode,
            repo=repo,
            ref=ref,
            package_version=package_version,
        )
    except EvagixSafetyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    content = evagix_ci_workflow(install_command=install_command, fail_under=fail_under)
    try:
        apply_write_plan(build_write_plan(root, {".github/workflows/evagix.yml": content}, force=force))
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("Created .github/workflows/evagix.yml")
    return 0


def _cmd_scoped(root: Path, dry_run: bool, force: bool) -> int:
    root = _normalize_root(root)
    facts, _ = _facts(root)
    if reject_unsafe_generated_commands(root, facts):
        return 1
    outputs = scoped_outputs(facts)
    if not outputs:
        print("No scoped AGENTS.md files were suggested for this repository.")
        return 0
    plan = build_write_plan(root, outputs, force=force)
    if plan.conflicts:
        for relative_path in plan.conflicts:
            print(f"ERROR: {relative_path} already exists. Re-run with --force to overwrite.", file=sys.stderr)
        return 1
    if not dry_run:
        apply_write_plan(plan)
    print("Planned scoped writes:" if dry_run else "Written scoped files:")
    for relative_path in plan.relative_paths:
        print(f"  - {relative_path}")
    return 0
