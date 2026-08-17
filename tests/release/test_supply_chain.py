from __future__ import annotations

import re
import tomllib
from pathlib import Path

from evagix.templates import evagix_ci_workflow

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
ACTION_LINE = re.compile(r"^\s*-\s*uses:\s+([^\s@]+)@([0-9a-f]{40})\s+#\s+(v[^\s]+)\s*$", re.MULTILINE)
ANY_ACTION = re.compile(r"^\s*-\s*uses:\s+([^\s#]+)", re.MULTILINE)
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
HTML_LINK = re.compile(r"<(?:a|img)\b[^>]*\b(?:href|src)=[\"']([^\"']+)[\"']", re.IGNORECASE)
PORTABLE_PREFIXES = ("https://", "http://", "#", "mailto:")
EXPECTED_ACTIONS = {
    "actions/checkout": ("3d3c42e5aac5ba805825da76410c181273ba90b1", "v7.0.1"),
    "actions/setup-python": ("5fda3b95a4ea91299a34e894583c3862153e4b97", "v7.0.0"),
    "actions/upload-artifact": ("043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", "v7.0.1"),
    "actions/download-artifact": ("3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c", "v8.0.1"),
    "github/codeql-action/upload-sarif": ("7211b7c8077ea37d8641b6271f6a365a22a5fbfa", "v4.36.0"),
    "pypa/gh-action-pypi-publish": ("dc37677b2e1c63e2034f94d8a5b11f265b73ba33", "v1.14.2"),
}


def _workflow_texts() -> dict[str, str]:
    paths = sorted({*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")})
    return {path.name: path.read_text(encoding="utf-8") for path in paths}


def _assert_known_immutable_actions(text: str, source: str) -> None:
    action_refs = ANY_ACTION.findall(text)
    parsed = ACTION_LINE.findall(text)
    assert len(parsed) == len(action_refs), f"{source} contains a mutable or malformed action ref"
    for action, sha, version in parsed:
        assert action in EXPECTED_ACTIONS, f"{source} uses unreviewed action {action}"
        assert (sha, version) == EXPECTED_ACTIONS[action], f"{source} has a mismatched SHA/version for {action}"


def test_checked_in_workflows_pin_reviewed_actions_to_full_shas() -> None:
    for name, text in _workflow_texts().items():
        _assert_known_immutable_actions(text, name)


def test_shell_only_workflows_are_allowed(tmp_path: Path) -> None:
    workflow = tmp_path / "shell-only.yaml"
    workflow.write_text("name: Shell only\njobs: {}\n", encoding="utf-8")
    _assert_known_immutable_actions(workflow.read_text(encoding="utf-8"), workflow.name)


def test_generated_governance_workflow_pins_reviewed_actions() -> None:
    workflow = evagix_ci_workflow("python -m pip install evagix", 80)
    _assert_known_immutable_actions(workflow, "generated Evagix workflow")


def test_publish_workflow_requires_full_quality_security_and_platform_gates() -> None:
    workflow = (WORKFLOWS / "publish-pypi.yml").read_text(encoding="utf-8")

    unprivileged, privileged = workflow.split("\n  publish-testpypi:\n", maxsplit=1)
    testpypi, publish_and_verify = privileged.split("\n  publish:\n", maxsplit=1)
    publish, production_verify = publish_and_verify.split("\n  verify-pypi:\n", maxsplit=1)
    assert "id-token: write" not in unprivileged
    assert "id-token: write" in testpypi
    assert "id-token: write" in publish
    assert "id-token: write" not in production_verify
    assert "needs: build" in testpypi
    assert "needs: [publish-testpypi, verify]" in testpypi
    assert testpypi.count("if: ${{ inputs.rehearse_testpypi }}") == 2
    assert "needs: [build, verify-testpypi]" in publish
    assert "needs.build.result == 'success'" in publish
    assert "inputs.rehearse_testpypi == false" in publish
    assert "needs.verify-testpypi.result == 'success'" in publish
    assert "needs: [publish, verify]" in production_verify
    assert "needs: [verify, platform-test]" in workflow
    assert "python -m ruff check ." in workflow
    assert "python -m ruff format --check ." in workflow
    assert "python -m mypy evagix" in workflow
    assert "python -m pytest --cov=evagix --cov-branch" in workflow
    assert "python -m pip_audit" in workflow
    assert "python -m build --no-isolation" in workflow
    assert "python -m evagix sync . --plan" in workflow
    assert "os: [ubuntu-latest, windows-latest, macos-latest]" in workflow
    assert 'python-version: ["3.11", "3.12", "3.13", "3.14"]' in workflow
    assert "workflow_dispatch:" in workflow
    assert workflow.count("ref: refs/tags/${{ inputs.tag }}") == 1
    assert workflow.count("ref: ${{ needs.verify.outputs.release_commit }}") == 4
    assert "fetch-depth: 0" in workflow
    assert "release_commit: ${{ steps.release_ref.outputs.commit }}" in workflow
    assert 'echo "commit=$head_commit" >> "$GITHUB_OUTPUT"' in workflow
    assert 'git show-ref --verify --quiet "refs/tags/$RELEASE_TAG"' in workflow
    assert 'git rev-parse "refs/tags/$RELEASE_TAG^{commit}"' in workflow
    assert "git rev-parse HEAD" in workflow
    assert "repository-url: https://test.pypi.org/legacy/" in testpypi
    assert "skip-existing: true" in testpypi
    assert "release:" not in workflow
    assert "scripts/verify_testpypi.py" in testpypi
    assert "Downloaded TestPyPI artifact differs" not in workflow
    assert "testpypi-dist/*.whl" in testpypi
    assert "--index pypi" in production_verify
    assert "pypi-dist/*.whl" in production_verify
    assert "scripts/verify_testpypi.py" in production_verify
    assert "scan-facts.schema.json" in production_verify
    assert "sha256sum dist/* > SHA256SUMS" in workflow
    assert "git archive --format=zip" in workflow
    assert "scripts/verify_source_archive.py" in workflow
    assert '--repository . --revision HEAD --prefix "$source_prefix"' in workflow
    assert "SOURCE_SHA256SUMS" in workflow
    assert "evagix-source-zip" in workflow
    assert "evagix-pypi-checksums" in workflow
    assert "password:" not in workflow
    assert "api-token" not in workflow
    assert "secrets." not in workflow


def test_readme_links_are_portable_to_pypi() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    targets = [*MARKDOWN_LINK.findall(readme), *HTML_LINK.findall(readme)]
    relative = [target for target in targets if not target.startswith(PORTABLE_PREFIXES)]
    assert relative == []


def test_release_build_backend_is_compatible_and_ci_toolchain_is_exact() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires = ["setuptools>=83,<85", "wheel>=0.47,<1"]' in pyproject

    constraints = (ROOT / "constraints-release.txt").read_text(encoding="utf-8").splitlines()
    assert "pip==26.2" in constraints
    assert "setuptools==83.0.0" in constraints
    assert "wheel==0.47.0" in constraints
    assert "build==1.5.0" in constraints
    assert "twine==6.2.0" in constraints
    assert "pip-audit==2.10.1" in constraints

    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    assert "recursive-include evagix/schemas *.json" in manifest
    assert "include constraints-release.txt" not in manifest
    for name, text in _workflow_texts().items():
        if "pip install" in text:
            assert "constraints-release.txt" in text, name

    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    assert "sha256sum dist/* > SHA256SUMS" in ci
    assert "scripts/verify_source_archive.py" in ci
    assert '--repository . --revision HEAD --prefix "$source_prefix"' in ci
    assert "SOURCE_SHA256SUMS" in ci
    assert "evagix-release-checksums" in ci


def test_dev_extra_includes_the_constrained_artifact_verification_toolchain() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dev_dependencies = set(metadata["project"]["optional-dependencies"]["dev"])
    constraints = (ROOT / "constraints-release.txt").read_text(encoding="utf-8").splitlines()

    for package in ("setuptools", "wheel"):
        constrained = next(item for item in constraints if item.startswith(f"{package}=="))
        assert constrained in dev_dependencies


def test_pre_commit_tools_use_local_exact_dependencies() -> None:
    config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "repo: local" in config
    assert "https://github.com/" not in config
    assert "ruff==0.15.20" in config
    assert "mypy==2.1.0" in config


def test_ruff_cache_is_disabled_in_automation_and_manifest_stays_minimal() -> None:
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    publish = (WORKFLOWS / "publish-pypi.yml").read_text(encoding="utf-8")
    pre_commit = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    assert 'RUFF_NO_CACHE: "true"' in ci
    assert 'RUFF_NO_CACHE: "true"' in publish
    assert "ruff check --fix --no-cache" in pre_commit
    assert "ruff format --no-cache" in pre_commit
    assert ".ruff_cache/" in gitignore
    assert "recursive-include tests" not in manifest
    assert "recursive-include docs" not in manifest
    assert "prune tests" in manifest
    assert "global-exclude *.py[cod]" in manifest


def test_security_audit_covers_release_supply_chain_changes() -> None:
    workflow = (WORKFLOWS / "security-audit.yml").read_text(encoding="utf-8")
    assert "branches:\n      - main" in workflow
    for path in (
        "evagix/**",
        "scripts/**",
        "tests/**",
        "constraints-release.txt",
        "MANIFEST.in",
        ".github/workflows/ci.yml",
        ".github/workflows/publish-pypi.yml",
        ".github/workflows/security-audit.yml",
    ):
        assert f'- "{path}"' in workflow


def test_supported_python_matrix_matches_metadata_and_documentation() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    publish = (WORKFLOWS / "publish-pypi.yml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    expected_matrix = 'python-version: ["3.11", "3.12", "3.13", "3.14"]'
    assert expected_matrix in ci
    assert expected_matrix in publish
    assert '"Programming Language :: Python :: 3.14"' in pyproject
    assert "Python 3.11, 3.12, 3.13, and 3.14" in readme
    assert "Evagix v0.1.0 provides conservative local evidence checks" in readme
