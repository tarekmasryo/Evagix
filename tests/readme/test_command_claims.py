from __future__ import annotations

import json
from pathlib import Path

from evagix.cli import main
from evagix.readme_audit import audit_readme
from evagix.scanner import scan_repo
from evagix.validators import doctor_repo


def test_ml_readme_metrics_are_not_treated_as_monitoring_claim(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# ML Dashboard\n\nReports model metrics including accuracy, precision, recall, and F1-score.\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("streamlit\npandas\nscikit-learn\nplotly\n", encoding="utf-8")
    facts = scan_repo(tmp_path)
    report = audit_readme(tmp_path, facts)
    assert "monitoring" not in {claim.claim for claim in report.claims}


def test_readme_command_gap_accepts_documented_make_command(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n\n## Local commands\n\n```bash\nmake test\nmake lint\nmake run\n```\n",
        encoding="utf-8",
    )
    (tmp_path / "Makefile").write_text(
        "test:\n\tpytest\nlint:\n\truff check .\nrun:\n\tpython app.py\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("pytest\nruff\n", encoding="utf-8")
    facts = scan_repo(tmp_path)
    report = doctor_repo(tmp_path, facts)
    assert "readme-command-gap" not in {finding.code for finding in report.findings}


def test_readme_claim_examples_are_not_self_audited(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        """# Demo

Evagix checks claims such as tested, Docker support, CI/CD, secure, and production-ready.

This is an example claim list, not a claim about this project.
""",
        encoding="utf-8",
    )
    facts = scan_repo(tmp_path)
    report = audit_readme(tmp_path, facts, strict=True)
    assert report.claims == []


def test_readme_schema_accepts_new_evidence_verdicts() -> None:
    schema = json.loads(Path("evagix/schemas/readme-audit.schema.json").read_text(encoding="utf-8"))
    verdicts = set(schema["properties"]["claims"]["items"]["properties"]["verdict"]["enum"])
    assert {"supported", "partially_supported", "weak_evidence", "unsupported", "manual_review_required"}.issubset(
        verdicts
    )


def test_readme_negated_and_planned_claims_are_not_audited(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        """# Demo

Docker support is planned, not currently available.
This is not production-ready.
This is not a CLI tool.
""",
        encoding="utf-8",
    )
    facts = scan_repo(tmp_path)
    claims = audit_readme(tmp_path, facts, strict=True).claims
    assert claims == []


def test_readme_audit_preserves_source_line_after_code_fence(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        """# Demo

```bash
echo one
echo two
```

This project is production-ready and Docker supported.
""",
        encoding="utf-8",
    )
    facts = scan_repo(tmp_path)

    report = audit_readme(tmp_path, facts, strict=True)
    claim = next(item for item in report.claims if item.claim in {"production-ready", "dockerized"})

    assert claim.source_line == 8


def test_readme_command_drift_flags_missing_npm_test_script(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\nRun tests with `npm test`.\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"build": "vite build"}}), encoding="utf-8")
    facts = scan_repo(tmp_path)
    claims = audit_readme(tmp_path, facts, strict=True).claims
    assert any(
        item.claim == "readme-command" and item.phrase == "npm test" and item.verdict == "unsupported"
        for item in claims
    )


def test_readme_command_drift_flags_missing_pytest_evidence(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\nRun `pytest`.\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.0.0"\n', encoding="utf-8")
    facts = scan_repo(tmp_path)
    claims = audit_readme(tmp_path, facts, strict=True).claims
    assert any(
        item.claim == "readme-command" and item.phrase == "pytest" and item.verdict == "unsupported" for item in claims
    )


def test_readme_command_drift_rejects_substring_of_detected_pytest_command(tmp_path: Path) -> None:
    from evagix.ecosystems.profiles import EcosystemDetection
    from evagix.model import RepoFacts

    (tmp_path / "README.md").write_text("# Demo\n\nRun `pytest tests_extra`.\n", encoding="utf-8")
    facts = RepoFacts(
        root_name="demo",
        commands={"test": "pytest tests"},
        test_paths=["tests"],
        ecosystems=[
            EcosystemDetection(
                id="python",
                name="Python",
                path=".",
                language="python",
                support="deep",
                confidence="high",
                evidence=("pyproject.toml", "tests"),
                commands={"test": "pytest tests"},
            )
        ],
    )

    claims = audit_readme(tmp_path, facts, strict=True).claims

    assert any(
        item.claim == "readme-command" and item.phrase == "pytest tests_extra" and item.verdict == "partial"
        for item in claims
    )


def test_readme_command_matching_preserves_exact_whitespace_normalization() -> None:
    from evagix.readme.command_extractor import _command_supported

    assert _command_supported("pytest   tests", {"pytest tests"}) is True


def test_maven_marker_does_not_validate_arbitrary_maven_command(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\nRun `mvn testtt`.\n", encoding="utf-8")
    (tmp_path / "pom.xml").write_text("<project></project>\n", encoding="utf-8")

    claims = audit_readme(tmp_path, scan_repo(tmp_path), strict=True).claims

    assert any(
        item.claim == "readme-command" and item.phrase == "mvn testtt" and item.verdict == "partial" for item in claims
    )


def test_maven_marker_preserves_evidenced_test_command(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\nRun `mvn test`.\n", encoding="utf-8")
    (tmp_path / "pom.xml").write_text("<project></project>\n", encoding="utf-8")

    claims = audit_readme(tmp_path, scan_repo(tmp_path), strict=True).claims

    assert not any(item.claim == "readme-command" for item in claims)


def test_polyglot_readme_scopes_backend_pytest_and_frontend_npm_test(tmp_path: Path) -> None:
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "tests").mkdir()
    (tmp_path / "frontend").mkdir()
    (tmp_path / "README.md").write_text(
        """# Demo

Backend validation:

```bash
pytest
```

Frontend validation:

```bash
npm test
```
""",
        encoding="utf-8",
    )
    (tmp_path / "backend" / "pyproject.toml").write_text(
        '[project]\nname = "backend"\nversion = "0.0.0"\n[project.optional-dependencies]\ndev = ["pytest"]\n',
        encoding="utf-8",
    )
    (tmp_path / "backend" / "tests" / "test_backend.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "frontend" / "package.json").write_text('{"scripts":{"test":"vitest run"}}\n', encoding="utf-8")
    facts = scan_repo(tmp_path)
    claims = audit_readme(tmp_path, facts, strict=True).claims
    command_claims = [item for item in claims if item.claim == "readme-command"]
    assert not command_claims


def test_typescript_typed_readme_claim_does_not_require_py_typed(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\nFully typed APIs.\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test-types":"tsc"},"devDependencies":{"typescript":"latest"}}', encoding="utf-8"
    )
    (tmp_path / "pnpm-lock.yaml").write_text("", encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
    assert main(["readme-audit", str(tmp_path), "--strict", "--fail-on", "weak-evidence"]) == 0


def test_readme_package_installable_claim_uses_nested_python_package_evidence(tmp_path: Path) -> None:
    from evagix.readme_audit import audit_readme
    from evagix.scanning.repository import scan_repo

    (tmp_path / "README.md").write_text("# Semantic Kernel\n\nPython package for AI orchestration.\n", encoding="utf-8")
    package_root = tmp_path / "python"
    package_root.mkdir()
    (package_root / "pyproject.toml").write_text(
        '[project]\nname = "semantic-kernel"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    source = package_root / "semantic_kernel"
    source.mkdir()
    (source / "__init__.py").write_text("", encoding="utf-8")

    report = audit_readme(tmp_path, scan_repo(tmp_path), strict=True)
    package_claims = [item for item in report.claims if item.claim == "package-installable"]
    assert package_claims
    assert package_claims[0].verdict == "supported"
    assert any("python/pyproject.toml" in item for item in package_claims[0].evidence)


def test_markdown_prompt_fence_is_not_readme_command():
    from evagix.readme.command_extractor import _extract_readme_commands

    readme = "\n".join(
        [
            "```md",
            "Make new Mastra project. Mastra = framework for AI apps + agents on modern TypeScript stack.",
            "```",
            "",
            "```shell",
            "npm create mastra@latest",
            "```",
        ]
    )

    commands = _extract_readme_commands(readme)

    assert "npm create mastra@latest" in commands
    assert not any(command.startswith("Make new Mastra project") for command in commands)
    assert not any(command.startswith("md\\nMake new Mastra project") for command in commands)
