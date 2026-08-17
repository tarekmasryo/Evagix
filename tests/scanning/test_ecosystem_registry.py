from __future__ import annotations

import json
from pathlib import Path

from evagix.ecosystems import command_supported_by_ecosystem
from evagix.scanner import scan_repo
from evagix.strict_scoring import build_evidence_ledger


def test_ecosystem_registry_detects_python_node_and_polyglot_commands(tmp_path: Path) -> None:
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "pyproject.toml").write_text(
        """
[project]
name = "api"
version = "0.1.0"
dependencies = ["fastapi", "pytest", "ruff"]
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "backend" / "tests").mkdir()
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text(
        json.dumps(
            {
                "scripts": {"test": "vitest", "build": "vite build", "lint": "eslint .", "typecheck": "tsc --noEmit"},
                "dependencies": {"next": "latest", "react": "latest", "vite": "latest"},
                "devDependencies": {"typescript": "latest", "vitest": "latest", "eslint": "latest"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "frontend" / "pnpm-lock.yaml").write_text("lockfileVersion: '9'\n", encoding="utf-8")

    facts = scan_repo(tmp_path)

    ecosystems = {(item.id, item.path): item for item in facts.ecosystems}
    assert ("python", "backend") in ecosystems
    assert ("node", "frontend") in ecosystems
    assert "fastapi" in ecosystems[("python", "backend")].frameworks
    assert "next.js" in ecosystems[("node", "frontend")].frameworks
    assert facts.commands["backend_test"] == "cd backend && python -m pytest"
    assert facts.commands["frontend_test"] == "cd frontend && pnpm test"
    assert command_supported_by_ecosystem("npm install", facts)[0] is True
    assert command_supported_by_ecosystem("pnpm test", facts)[0] is True
    assert command_supported_by_ecosystem("pytest", facts)[0] is True


def test_ecosystem_registry_detects_common_backend_ecosystems(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text(
        "module example.com/api\nrequire github.com/gin-gonic/gin v1.10.0\n", encoding="utf-8"
    )
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname="svc"\nversion="0.1.0"\n[dependencies]\naxum="0.7"\n', encoding="utf-8"
    )
    (tmp_path / "pom.xml").write_text(
        "<project><dependencies><dependency><artifactId>spring-boot</artifactId></dependency></dependencies></project>",
        encoding="utf-8",
    )
    (tmp_path / "service.csproj").write_text(
        '<Project><ItemGroup><PackageReference Include="Microsoft.AspNetCore.App" /></ItemGroup></Project>',
        encoding="utf-8",
    )
    (tmp_path / "composer.json").write_text(
        json.dumps({"require": {"laravel/framework": "*"}, "require-dev": {"phpunit/phpunit": "*"}}), encoding="utf-8"
    )
    (tmp_path / "Gemfile").write_text("gem 'rails'\ngem 'rspec'\n", encoding="utf-8")
    (tmp_path / "main.tf").write_text('resource "null_resource" "x" {}\n', encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM alpine\n", encoding="utf-8")

    facts = scan_repo(tmp_path)
    ids = {item.id for item in facts.ecosystems}

    assert {"go", "rust", "java_maven", "dotnet", "php", "ruby", "terraform", "docker"}.issubset(ids)
    assert "gin" in facts.frameworks
    assert "axum" in facts.frameworks
    assert "spring boot" in facts.frameworks
    assert "laravel" in facts.frameworks
    assert facts.commands["test"] in {
        "go test ./...",
        "cargo test",
        "mvn test",
        "dotnet test",
        "vendor/bin/phpunit",
        "bundle exec rspec",
    }
    assert command_supported_by_ecosystem("cargo test", facts)[0] is True
    assert command_supported_by_ecosystem("mvn test", facts)[0] is True
    assert command_supported_by_ecosystem("dotnet test", facts)[0] is True
    assert command_supported_by_ecosystem("terraform validate", facts)[0] is True


def test_evidence_ledger_includes_ecosystems(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\nRun `npm test`.\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest"}, "devDependencies": {"vitest": "latest"}}), encoding="utf-8"
    )

    facts = scan_repo(tmp_path)
    ledger = build_evidence_ledger(tmp_path, facts)

    assert ledger["ecosystems"]
    assert ledger["ecosystems"][0]["id"] == "node"
    assert any(command["name"] == "test" for command in ledger["commands"])


def test_ecosystem_scanner_ignores_deep_markers_beyond_documented_depth(tmp_path: Path) -> None:
    deep = tmp_path / "a" / "b" / "c" / "d" / "e" / "f"
    deep.mkdir(parents=True)
    (deep / "package.json").write_text(json.dumps({"scripts": {"test": "vitest"}}), encoding="utf-8")
    facts = scan_repo(tmp_path)
    assert not any(item.path.endswith("a/b/c/d/e/f") for item in facts.ecosystems)


def test_ecosystem_scanner_rejects_symlinked_workspace(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "package.json").write_text(json.dumps({"scripts": {"test": "vitest"}}), encoding="utf-8")
    link = tmp_path / "linked"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        return
    facts = scan_repo(tmp_path)
    assert not any(item.path == "linked" for item in facts.ecosystems)


def test_ecosystem_scanner_handles_large_irrelevant_tree(tmp_path: Path) -> None:
    big = tmp_path / "big"
    big.mkdir()
    for index in range(300):
        (big / f"file_{index}.txt").write_text("ignore\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "vitest"}}), encoding="utf-8")
    facts = scan_repo(tmp_path)
    assert any(item.id == "node" for item in facts.ecosystems)
