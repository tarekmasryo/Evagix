from __future__ import annotations

from pathlib import Path

import pytest

from evagix.command_text import extract_shell_code_blocks
from evagix.model import RepoFacts
from evagix.readme import audit_engine
from evagix.readme.audit_engine import audit_readme
from evagix.readme.command_extractor import _extract_readme_commands
from evagix.readme.text_utils import _active_markdown_headings, _claim_occurrences
from evagix.scanner import scan_repo


def _claims(tmp_path: Path, text: str) -> dict[str, object]:
    (tmp_path / "README.md").write_text(f"# Demo\n\n{text}\n", encoding="utf-8")
    report = audit_readme(tmp_path, scan_repo(tmp_path), strict=True)
    return {item.claim: item for item in report.claims}


def _claims_from_file(tmp_path: Path, filename: str, text: str) -> dict[str, object]:
    (tmp_path / filename).write_text(f"{text}\n", encoding="utf-8")
    report = audit_readme(tmp_path, scan_repo(tmp_path), strict=True)
    return {item.claim: item for item in report.claims}


@pytest.mark.parametrize(
    "text",
    [
        "Used by FastAPI.",
        "Projects using this tool include FastAPI.",
        "FastAPI uses this tool.",
        "For example, FastAPI provides a useful comparison.",
        "Unlike FastAPI, this tool is a command-line linter.",
    ],
)
def test_downstream_or_reference_technology_mentions_are_not_project_claims(tmp_path: Path, text: str) -> None:
    assert "fastapi" not in _claims(tmp_path, text)


def test_direct_project_technology_claim_is_still_audited(tmp_path: Path) -> None:
    claims = _claims(tmp_path, "This project uses FastAPI.")

    assert claims["fastapi"].verdict == "unsupported"  # type: ignore[union-attr]


def test_downstream_lead_in_applies_to_following_markdown_list(tmp_path: Path) -> None:
    claims = _claims(
        tmp_path,
        """This tool is used in major open-source projects like:

- Apache Airflow
- FastAPI
- Pandas""",
    )

    assert "fastapi" not in claims


def test_direct_passive_project_claim_is_still_audited(tmp_path: Path) -> None:
    claims = _claims(tmp_path, "FastAPI is used by this project.")

    assert claims["fastapi"].verdict == "unsupported"  # type: ignore[union-attr]


def test_multiline_testimonial_byline_does_not_become_project_capability(tmp_path: Path) -> None:
    claims = _claims(
        tmp_path,
        """## Testimonials

[**Jane Doe**](https://example.invalid/jane), creator
of [FastAPI](https://github.com/example-org/fastapi):

> This tool is exceptionally fast.""",
    )

    assert "fastapi" not in claims


def test_visible_markdown_link_label_remains_an_audited_claim(tmp_path: Path) -> None:
    text = "# Demo\n\nThis project uses [FastAPI](https://fastapi.example.invalid/).\n"
    (tmp_path / "README.md").write_text(text, encoding="utf-8")

    report = audit_readme(tmp_path, scan_repo(tmp_path), strict=True)
    claims = [item for item in report.claims if item.claim == "fastapi"]
    occurrences = _claim_occurrences(r"\bfastapi\b", text, root_name="demo")

    assert occurrences == [("FastAPI", 3)]
    assert len(claims) == 1
    assert claims[0].verdict == "unsupported"
    assert claims[0].source_line == 3


@pytest.mark.parametrize("role", ["creator", "founder", "maintainer", "co-creator"])
def test_single_line_attribution_roles_do_not_become_project_capabilities(tmp_path: Path, role: str) -> None:
    assert "fastapi" not in _claims(tmp_path, f"Jane Doe, {role} of FastAPI:")


@pytest.mark.parametrize(
    "text",
    [
        "This tool integrates with FastAPI.",
        "This package is compatible with FastAPI.",
        "## Framework integrations\n\n- FastAPI",
    ],
)
def test_integration_or_compatibility_mentions_do_not_imply_direct_dependency(tmp_path: Path, text: str) -> None:
    assert "fastapi" not in _claims(tmp_path, text)


def test_direct_framework_implementation_claim_is_still_checked(tmp_path: Path) -> None:
    claims = _claims(
        tmp_path,
        """## Framework integrations

This repository implements its API with FastAPI.""",
    )

    assert claims["fastapi"].verdict == "unsupported"  # type: ignore[union-attr]


def test_rst_integration_heading_and_list_do_not_imply_direct_dependency(tmp_path: Path) -> None:
    text = """Framework Integration
=====================

This tool integrates with web frameworks:

- Django
- FastAPI"""
    claims = _claims_from_file(
        tmp_path,
        "README.rst",
        text,
    )

    assert _active_markdown_headings(text, text.index("FastAPI")) == ["framework integration"]
    assert "fastapi" not in claims


def test_educational_curriculum_topics_are_not_repository_capability_claims(tmp_path: Path) -> None:
    claims = _claims(
        tmp_path,
        """## Course syllabus

| Module | Topics taught |
| --- | --- |
| 1 | RAG and observability |
| 2 | Production-ready agents |""",
    )

    assert not {"ai/llm", "monitoring", "production-ready"}.intersection(claims)


def test_direct_root_capabilities_in_educational_repository_are_still_audited(tmp_path: Path) -> None:
    claims = _claims(
        tmp_path,
        """## Course syllabus

The lessons teach prompt design.

This repository implements RAG and observability.""",
    )

    assert {"ai/llm", "monitoring"}.issubset(claims)


def test_related_component_property_is_not_attributed_to_root_project(tmp_path: Path) -> None:
    claims = _claims(
        tmp_path,
        """## Related projects

`helper-core` is a dependency-free package used by this project.""",
    )

    assert "zero-dependencies" not in claims


def test_named_ecosystem_component_capability_is_not_attributed_to_root(tmp_path: Path) -> None:
    claims = _claims(
        tmp_path,
        """## Ecosystem

- **[Trace Suite](https://example.invalid/trace)** — Tracing and observability for applications.""",
    )

    assert "monitoring" not in claims


def test_direct_root_dependency_free_claim_is_still_audited(tmp_path: Path) -> None:
    claims = _claims(
        tmp_path,
        """## Related projects

This project is dependency-free.""",
    )

    assert claims["zero-dependencies"].verdict == "unsupported"  # type: ignore[union-attr]


def test_explicit_root_name_property_is_still_audited(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("demo-tool is dependency-free.\n", encoding="utf-8")
    facts = RepoFacts(root_name="owner__demo-tool")

    claims = {item.claim: item for item in audit_readme(tmp_path, facts, strict=True).claims}

    assert claims["zero-dependencies"].verdict == "unsupported"


def test_external_registry_install_does_not_require_local_package_metadata(tmp_path: Path) -> None:
    claims = _claims(tmp_path, "```bash\nnpm install -g some-package\n```")

    assert "readme-command" not in claims


def test_repository_development_install_still_requires_local_package_metadata(tmp_path: Path) -> None:
    claims = _claims(tmp_path, "```bash\nnpm install\n```")

    assert claims["readme-command"].verdict == "unsupported"  # type: ignore[union-attr]


def test_documented_bootstrap_flow_can_generate_makefile_for_make_install(tmp_path: Path) -> None:
    claims = _claims(
        tmp_path,
        """```bash
./bootstrap
make
make install
```""",
    )

    assert "readme-command" not in claims


def test_chained_bootstrap_flow_can_generate_makefile_for_sudo_make_install(tmp_path: Path) -> None:
    text = "\x60\x60\x60bash\n./bootstrap && make && sudo make install\n\x60\x60\x60"

    commands = _extract_readme_commands(text)
    claims = _claims(tmp_path, text)

    assert "make install" in commands
    assert "readme-command" not in claims


def test_fallback_make_install_does_not_use_failed_bootstrap_as_generation_evidence(tmp_path: Path) -> None:
    text = "\x60\x60\x60bash\n./bootstrap || make install\n\x60\x60\x60"

    commands = _extract_readme_commands(text)
    claims = _claims(tmp_path, text)

    assert "make install" in commands
    assert claims["readme-command"].verdict == "unsupported"  # type: ignore[union-attr]


def test_semicolon_bootstrap_sequence_supports_later_make_install(tmp_path: Path) -> None:
    text = "\x60\x60\x60bash\n./bootstrap; make install\n\x60\x60\x60"

    assert "readme-command" not in _claims(tmp_path, text)


def test_rst_literal_block_exposes_bootstrap_make_install_sequence(tmp_path: Path) -> None:
    text = """Building from source
====================

Run the \x60bootstrap\x60 script you find in the source directory of CMake.

Once this has finished successfully,
run \x60make\x60 and \x60make install\x60.

For example, if you simply want to build and install CMake from source,
you can build directly in the source tree::

  $ ./bootstrap && make && sudo make install"""

    blocks = extract_shell_code_blocks(text)
    claims = _claims_from_file(tmp_path, "README.rst", text)

    assert any("./bootstrap && make && sudo make install" in block for block in blocks)
    assert "readme-command" not in claims


def test_completed_bootstrap_prose_supports_later_make_install(tmp_path: Path) -> None:
    text = """After ./bootstrap completes, run the generated build flow:

\x60\x60\x60bash
make
sudo make install
\x60\x60\x60"""

    assert "readme-command" not in _claims(tmp_path, text)


def test_isolated_make_install_without_generation_evidence_remains_unsupported(tmp_path: Path) -> None:
    claims = _claims(tmp_path, "```bash\nmake install\n```")

    assert claims["readme-command"].verdict == "unsupported"  # type: ignore[union-attr]


def test_relevant_truncated_absence_cannot_be_unsupported_with_high_confidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    warning = (
        "Python package evidence discovery was truncated because the 2-entry traversal budget was reached "
        "after 2 filesystem entries (1 directories, 1 files); results may be incomplete."
    )
    monkeypatch.setattr(
        audit_engine,
        "claim_rules",
        lambda: [
            (
                "package-installable",
                r"\binstallable package\b",
                lambda _root, _facts: ([], ["Python packaging metadata", warning]),
                "Add package evidence.",
            )
        ],
    )

    claims = _claims(tmp_path, "This is an installable package.")

    assert claims["package-installable"].verdict == "manual_review_required"  # type: ignore[union-attr]
    assert claims["package-installable"].confidence != "high"  # type: ignore[union-attr]


def test_unrelated_truncation_does_not_weaken_decisive_claim_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        audit_engine,
        "claim_rules",
        lambda: [
            (
                "package-installable",
                r"\binstallable package\b",
                lambda _root, _facts: (["decisive package metadata"], []),
                "Add package evidence.",
            )
        ],
    )
    facts = RepoFacts(
        root_name="demo",
        warnings=["Unrelated monitoring search was truncated; results may be incomplete."],
    )
    (tmp_path / "README.md").write_text("This is an installable package.\n", encoding="utf-8")

    claim = audit_readme(tmp_path, facts, strict=True).claims[0]

    assert claim.verdict == "supported"
    assert claim.confidence == "high"
