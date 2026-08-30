from __future__ import annotations

import tomllib
from pathlib import Path


def test_manifest_has_minimal_package_contract() -> None:
    manifest_lines = [line for line in Path("MANIFEST.in").read_text(encoding="utf-8").splitlines() if line]
    assert manifest_lines == [
        "include README.md",
        "include LICENSE",
        "include CHANGELOG.md",
        "include SECURITY.md",
        "include evagix/py.typed",
        "recursive-include evagix/schemas *.json",
        "prune tests",
        "global-exclude *.py[cod]",
        "global-exclude CACHEDIR.TAG",
    ]


def test_changelog_has_stable_release_heading() -> None:
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    assert "\n## [0.1.1]\n" in changelog
    assert "## [0.1.1] -" not in changelog
    assert "\n## [0.1.0]\n" in changelog
    assert "## [0.1.0] -" not in changelog
    assert "### Verified" not in changelog
    assert "[0.1.1]: https://github.com/tarekmasryo/Evagix/releases/tag/v0.1.1" in changelog
    assert "[0.1.0]: https://github.com/tarekmasryo/Evagix/releases/tag/v0.1.0" in changelog


def test_package_version_matches_project_metadata() -> None:
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    namespace: dict[str, str] = {}
    exec(Path("evagix/__init__.py").read_text(encoding="utf-8"), namespace)
    assert metadata["project"]["version"] == "0.1.1"
    assert namespace["__version__"] == metadata["project"]["version"]
