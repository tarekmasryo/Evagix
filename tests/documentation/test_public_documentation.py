from __future__ import annotations

from pathlib import Path


def test_architecture_documents_skipped_demo_and_fixture_directories() -> None:
    architecture = Path("docs/architecture.md").read_text(encoding="utf-8")

    for directory in ["examples/", "fixtures/", "demo/", "samples/"]:
        assert directory.removesuffix("/") in architecture


def test_readme_documents_advanced_commands() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "### Advanced commands" in readme
    for command in [
        "evagix audit .",
        "evagix report .",
        "evagix baseline .",
        "evagix diff .",
        "evagix scoped .",
    ]:
        assert command in readme


def test_rule_reference_document_exists() -> None:
    overview = Path("docs/rules.md").read_text(encoding="utf-8")
    reference = Path("docs/rules-reference.md").read_text(encoding="utf-8")
    assert "Verify what the repository claims" in overview
    assert "Full reference" in overview
    assert "EVAGIX_GENERATED_TARGET_TAMPERED" in reference
    assert "MISSING_OPTIONAL_AGENT_FILE" in reference
