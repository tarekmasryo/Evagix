from __future__ import annotations

from pathlib import Path

from evagix.config import CustomTarget
from evagix.core.io import TextReadResult, UnsafePathError, safe_read_text_result
from evagix.generated_integrity import (
    INTEGRITY_MANIFEST_PATH,
    content_digest_matches,
    generated_content_digest,
    parse_integrity_manifest,
)
from evagix.model import RepoFacts
from evagix.renderers import DEFAULT_TARGETS, TARGETS, render_all
from evagix.report_models import CheckResult
from evagix.utils import (
    extract_fingerprint,
    facts_fingerprint,
    is_generated,
    normalize_generated_content,
    resolve_output_path,
)
from evagix.utils import (
    has_any_command as _has_any_command,
)

MAX_GENERATED_TARGET_CHARS = 1_000_000


def _read_generated_target(root: Path, path: Path) -> TextReadResult:
    return safe_read_text_result(
        path,
        root=root,
        max_chars=MAX_GENERATED_TARGET_CHARS,
    )


def _record_unverifiable_target(result: CheckResult, relative_path: str, *, unsafe: bool) -> None:
    if relative_path not in result.unmanaged_targets:
        result.unmanaged_targets.append(relative_path)
    warning = (
        f"Generated target path is unsafe and was not followed: {relative_path}"
        if unsafe
        else f"Generated target could not be read safely as a regular file and was not inspected: {relative_path}"
    )
    if warning not in result.warnings:
        result.warnings.append(warning)


def _resolve_generated_target(root: Path, relative_path: str, result: CheckResult) -> Path | None:
    try:
        return resolve_output_path(root, relative_path)
    except ValueError:
        _record_unverifiable_target(result, relative_path, unsafe=True)
        return None


def _read_generated_target_with_diagnostics(
    root: Path,
    path: Path,
    relative_path: str,
    result: CheckResult,
) -> TextReadResult | None:
    try:
        return _read_generated_target(root, path)
    except UnsafePathError:
        _record_unverifiable_target(result, relative_path, unsafe=True)
    except OSError:
        _record_unverifiable_target(result, relative_path, unsafe=False)
    except UnicodeError:
        _record_invalid_encoding_target(result, relative_path)
    return None


def _has_existing_managed_target(root: Path, expected: dict[str, str], result: CheckResult) -> bool:
    for relative_path in expected:
        path = _resolve_generated_target(root, relative_path, result)
        if path is None:
            continue
        if not path.exists():
            continue
        read_result = _read_generated_target_with_diagnostics(root, path, relative_path, result)
        if read_result is None:
            continue
        if is_generated(read_result.text):
            return True
    return False


def _record_truncated_target(result: CheckResult, relative_path: str) -> None:
    if relative_path not in result.truncated_targets:
        result.truncated_targets.append(relative_path)
    result.warnings.append(
        f"Generated target exceeds the {MAX_GENERATED_TARGET_CHARS}-character verification limit: {relative_path}"
    )


def _record_invalid_encoding_target(result: CheckResult, relative_path: str) -> None:
    if relative_path in result.invalid_encoding_targets:
        return
    result.invalid_encoding_targets.append(relative_path)
    result.warnings.append(f"Generated target is not valid UTF-8 and was not inspected: {relative_path}")


def check_repo(
    root: Path,
    facts: RepoFacts,
    target_keys: list[str] | None = None,
    custom_targets: list[CustomTarget] | None = None,
    *,
    fail_on_stale: bool = True,
) -> CheckResult:
    result = CheckResult(ok=True)
    current_fingerprint = facts_fingerprint(facts.to_dict())
    effective_target_keys = target_keys
    if effective_target_keys is None:
        existing_generated_keys = []
        for key, relative_path in TARGETS.items():
            path = _resolve_generated_target(root, relative_path, result)
            if path is None:
                continue
            if not path.exists():
                continue
            read_result = _read_generated_target_with_diagnostics(root, path, relative_path, result)
            if read_result is None:
                continue
            if is_generated(read_result.text):
                existing_generated_keys.append(key)
        if existing_generated_keys:
            effective_target_keys = list(dict.fromkeys([*DEFAULT_TARGETS.keys(), *existing_generated_keys]))

    expected = render_all(facts, effective_target_keys, custom_targets)
    missing_targets_are_required = target_keys is not None or bool(custom_targets)
    integrity_manifest = None
    manifest_path = _resolve_generated_target(root, INTEGRITY_MANIFEST_PATH, result)
    if manifest_path is not None and manifest_path.exists():
        manifest_read = _read_generated_target_with_diagnostics(
            root,
            manifest_path,
            INTEGRITY_MANIFEST_PATH,
            result,
        )
        if manifest_read is not None:
            if manifest_read.truncated:
                _record_truncated_target(result, INTEGRITY_MANIFEST_PATH)
            elif content_digest_matches(manifest_read.text) is not True:
                result.tampered_targets.append(INTEGRITY_MANIFEST_PATH)
                result.warnings.append(f"Generated integrity manifest is invalid: {INTEGRITY_MANIFEST_PATH}")
            else:
                integrity_manifest = parse_integrity_manifest(manifest_read.text)
                if integrity_manifest is None:
                    result.tampered_targets.append(INTEGRITY_MANIFEST_PATH)
                    result.warnings.append(f"Generated integrity manifest is malformed: {INTEGRITY_MANIFEST_PATH}")
    elif manifest_path is not None and _has_existing_managed_target(root, expected, result):
        result.ok = False
        result.errors.append(
            f"Generated integrity manifest is missing: {INTEGRITY_MANIFEST_PATH}. Run `evagix compile`."
        )

    for relative_path, expected_content in expected.items():
        path = _resolve_generated_target(root, relative_path, result)
        if path is None:
            continue
        if not path.exists():
            if missing_targets_are_required:
                result.missing_targets.append(relative_path)
                result.warnings.append(f"Requested generated target is missing: {relative_path}")
            continue

        read_result = _read_generated_target_with_diagnostics(root, path, relative_path, result)
        if read_result is None:
            continue
        if read_result.truncated:
            _record_truncated_target(result, relative_path)
            continue
        content = read_result.text
        if not is_generated(content):
            result.warnings.append(f"External/user-owned context file is not Evagix-managed: {relative_path}")
            if missing_targets_are_required:
                result.unmanaged_targets.append(relative_path)
            continue

        existing_fingerprint = extract_fingerprint(content)
        digest_status = content_digest_matches(content)
        recorded_digest = (
            integrity_manifest.target_digests.get(relative_path) if integrity_manifest is not None else None
        )
        actual_digest = generated_content_digest(content)

        integrity_reason = ""
        if digest_status is not True:
            integrity_reason = "content digest is missing" if digest_status is None else "content digest does not match"
        elif integrity_manifest is not None and recorded_digest is None:
            integrity_reason = "target is missing from the last-generation integrity manifest"
        elif recorded_digest is not None and actual_digest != recorded_digest:
            integrity_reason = "content differs from the last successful generation"
        if integrity_reason:
            result.tampered_targets.append(relative_path)
            result.warnings.append(
                f"Generated target integrity metadata is invalid ({integrity_reason}): {relative_path}"
            )

        if existing_fingerprint != current_fingerprint:
            result.stale_targets.append(relative_path)
            result.warnings.append(f"Stale generated target: {relative_path}")
        elif normalize_generated_content(content) != normalize_generated_content(expected_content):
            if relative_path not in result.tampered_targets:
                result.tampered_targets.append(relative_path)
            result.warnings.append(
                f"Generated target does not match the canonical output for its current fingerprint: {relative_path}"
            )

    if not _has_any_command(facts.commands, "test"):
        result.warnings.append("No test command detected; generated instructions cannot guide validation confidently.")
    if not _has_any_command(facts.commands, "lint"):
        result.warnings.append("No lint command detected; style validation may be underspecified.")
    if not facts.ci_workflows:
        result.warnings.append("No CI workflow detected; drift checking is not enforced automatically.")

    if result.missing_targets and missing_targets_are_required:
        result.ok = False
        result.errors.append(
            "Requested generated context exports are missing. Run `evagix compile` for the configured targets."
        )
    if result.stale_targets and fail_on_stale:
        result.ok = False
        result.errors.append("Generated context exports are stale. Run `evagix compile`.")
    if result.tampered_targets:
        result.ok = False
        result.errors.append(
            "Generated context exports were modified manually. Run `evagix compile` or keep intentional custom "
            "instructions outside generated files."
        )
    if result.unmanaged_targets:
        result.ok = False
        result.errors.append(
            "Configured or discovered context targets are not Evagix-managed regular files or could not be read "
            "safely. Move or repair the files, choose different target paths, or re-run `evagix compile --force` "
            "after reviewing them."
        )
    if result.truncated_targets:
        result.ok = False
        result.errors.append(
            "Generated context verification was truncated by the configured read limit. Reduce the target size or "
            "split the generated context before relying on the result."
        )
    if result.invalid_encoding_targets:
        result.ok = False
        result.errors.append(
            "Generated context contains files that are not valid UTF-8. Convert and review them before relying on "
            "Evagix verification."
        )
    return result
