from __future__ import annotations

import json
from pathlib import Path

from pytest import CaptureFixture

from evagix.classification import _iter_bounded_files, classify_project
from evagix.cli import main
from evagix.model import RepoFacts, Subproject
from evagix.profiles import infer_profiles
from evagix.scanner import scan_repo


def test_classification_detects_python_cli_without_readme_false_positives(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n\nMentions FastAPI, Docker, Streamlit, and Go as background text only.\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.1.0"
dependencies = ["pytest", "ruff", "mypy"]

[project.scripts]
demo = "demo.cli:main"
        """.strip(),
        encoding="utf-8",
    )
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "demo" / "cli.py").write_text("def main():\n    return 0\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()

    classification = classify_project(tmp_path, scan_repo(tmp_path))

    assert classification.primary is not None
    assert classification.primary.name == "python-cli"
    secondary_names = {item.name for item in classification.secondary}
    assert "fastapi-service" not in secondary_names
    assert "dockerized-app" not in secondary_names
    assert "ml-dashboard" not in secondary_names
    assert "polyglot-monorepo" not in secondary_names


def test_classify_cli_outputs_text_and_json(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["pytest", "ruff"]\n[project.scripts]\ndemo = "demo.cli:main"\n',
        encoding="utf-8",
    )
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "cli.py").write_text("def main():\n    return 0\n", encoding="utf-8")

    assert main(["classify", str(tmp_path)]) == 0
    assert "Primary project type" in capsys.readouterr().out

    assert main(["classify", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["classification"]["primary"]["name"] == "python-cli"


def test_classification_prefers_fullstack_ai_service_for_mixed_fixture(tmp_path: Path) -> None:
    root = tmp_path / "mixed-ai-service-repo"
    (root / "app").mkdir(parents=True)
    (root / "frontend").mkdir()
    (root / "tests").mkdir()
    (root / "README.md").write_text(
        "# Mixed AI service\n\nSmall polyglot fixture with a Python API, React frontend, Docker Compose, LangChain, and Qdrant.\n",
        encoding="utf-8",
    )
    (root / "app" / "main.py").write_text(
        "from fastapi import FastAPI\nfrom langchain_core.documents import Document\napp = FastAPI()\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        '[project]\nname = "mixed-ai-service"\ndependencies = ["fastapi", "langchain", "qdrant-client", "pytest", "black"]\n',
        encoding="utf-8",
    )
    (root / "frontend" / "package.json").write_text(
        '{"scripts":{"test":"vitest"},"dependencies":{"react":"latest"}}\n', encoding="utf-8"
    )
    (root / "docker-compose.yml").write_text("services:\n  api:\n    build: .\n", encoding="utf-8")
    (root / "tests" / "test_smoke.py").write_text("def test_smoke():\n    assert True\n", encoding="utf-8")

    classification = classify_project(root, scan_repo(root))

    assert classification.primary is not None
    assert classification.primary.name == "fullstack-ai-service"
    secondary_names = {item.name for item in classification.secondary}
    assert "react-frontend" in secondary_names
    assert "rag-service" in secondary_names


def test_classification_prunes_skipped_directories_before_collecting_paths(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["pytest"]\n[project.scripts]\ndemo = "demo.cli:main"\n',
        encoding="utf-8",
    )
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "cli.py").write_text("def main():\n    return 0\n", encoding="utf-8")
    (tmp_path / "node_modules" / "fake-framework").mkdir(parents=True)
    (tmp_path / "node_modules" / "fake-framework" / "package.json").write_text(
        '{"dependencies":{"react":"latest","next":"latest"}}', encoding="utf-8"
    )

    collected = {path.relative_to(tmp_path).as_posix() for path in _iter_bounded_files(tmp_path)}
    classification = classify_project(tmp_path, scan_repo(tmp_path))

    assert classification.primary is not None
    assert classification.primary.name == "python-cli"
    assert "node_modules/fake-framework/package.json" not in collected


def test_single_root_subproject_is_not_polyglot_monorepo() -> None:
    facts = RepoFacts(root_name="demo", languages=["python"], subprojects=[Subproject(path=".", kind="python")])
    assert "polyglot-monorepo" not in infer_profiles(facts)


def test_backend_pytest_and_frontend_npm_test_are_scoped_correctly(tmp_path: Path) -> None:
    (tmp_path / "backend" / "tests").mkdir(parents=True)
    (tmp_path / "backend" / "pyproject.toml").write_text(
        '[project]\nname="backend"\ndependencies=["pytest"]\n', encoding="utf-8"
    )
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text(
        '{"scripts":{"test":"vitest"},"devDependencies":{"vitest":"latest"}}', encoding="utf-8"
    )
    (tmp_path / "README.md").write_text(
        """# Demo\n\nBackend:\n```bash\npytest\n```\n\nFrontend:\n```bash\nnpm test\n```\n""", encoding="utf-8"
    )
    assert main(["readme-audit", str(tmp_path), "--strict", "--fail-on", "unsupported"]) == 0


def test_python_plus_ci_is_not_polyglot_monorepo() -> None:
    facts = RepoFacts(
        root_name="demo",
        languages=["python", "ci"],
        package_managers=["pip", "github-actions"],
        subprojects=[Subproject(path=".", kind="python")],
    )
    assert "polyglot-monorepo" not in infer_profiles(facts)


def test_node_typecheck_aliases_are_detected(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test-types":"tsc","lint-typescript":"turbo run typescript"},'
        '"devDependencies":{"typescript":"latest"}}',
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("", encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
    facts = scan_repo(tmp_path)
    assert facts.commands["typecheck"] == "pnpm test-types"
    assert "typescript" in facts.typecheck_tools


def test_curriculum_monorepo_with_lesson_apps_is_docs_education_repo(tmp_path) -> None:
    from evagix.repository_intent import is_docs_or_education_repo
    from evagix.scanning.repository import scan_repo
    from evagix.validation.doctor import doctor_repo

    (tmp_path / "README.md").write_text(
        "# ML For Beginners\n\n"
        "A curriculum with lessons, tutorials, notebooks, and a hands-on learning path for beginners.\n",
        encoding="utf-8",
    )

    for folder in [
        "1-Introduction",
        "2-Regression",
        "3-Web-App",
        "4-Classification",
        "docs",
        "translations",
        "notebooks",
    ]:
        (tmp_path / folder).mkdir(parents=True, exist_ok=True)

    (tmp_path / "3-Web-App" / "app.py").write_text(
        "from flask import Flask\n\napp = Flask(__name__)\n",
        encoding="utf-8",
    )

    (tmp_path / "package.json").write_text(
        '{"scripts":{"lint":"eslint ."},"devDependencies":{"eslint":"^9.0.0"}}',
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    quiz_app = tmp_path / "quiz-app"
    quiz_app.mkdir()
    (quiz_app / "package.json").write_text(
        '{"scripts":{"build":"vite build","lint":"eslint ."},"dependencies":{"vue":"^3.0.0"}}',
        encoding="utf-8",
    )

    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "stale.yml").write_text(
        "name: stale\non: workflow_dispatch\njobs: {}\n",
        encoding="utf-8",
    )

    facts = scan_repo(tmp_path)
    assert is_docs_or_education_repo(tmp_path, facts)

    report = doctor_repo(tmp_path, facts, strict=True)
    codes = {finding.code: finding for finding in report.findings}

    assert "missing-backend-tests" not in codes
    assert "missing-tests-folder" not in codes
    assert codes["missing-test"].severity == "info"
    assert codes["missing-test"].penalty == 0
    assert report.score >= 80


def test_scan_detects_azure_pipelines_ci(tmp_path) -> None:
    from evagix.scanning.repository import scan_repo
    from evagix.validation.doctor import doctor_repo

    (tmp_path / "README.md").write_text("# Azure CI Repo\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'azure-ci-repo'\nversion = '0.1.0'\n",
        encoding="utf-8",
    )

    azure_dir = tmp_path / ".azure-pipelines"
    azure_dir.mkdir()
    (azure_dir / "azure-pipelines.yml").write_text(
        "trigger:\n- main\n\npool:\n  vmImage: ubuntu-latest\n\nsteps:\n- script: echo CI\n",
        encoding="utf-8",
    )

    facts = scan_repo(tmp_path)

    assert ".azure-pipelines/azure-pipelines.yml" in facts.ci_workflows
    assert "azure-pipelines" in facts.dev_tools

    report = doctor_repo(tmp_path, facts, strict=True)
    codes = {finding.code for finding in report.findings}

    assert "missing-ci" not in codes


def test_node_package_bin_supports_cli_tool_claim(tmp_path) -> None:
    import json

    from evagix.readme.claim_checks import _check_cli_tool
    from evagix.scanning.repository import scan_repo

    (tmp_path / "README.md").write_text(
        "# Create Demo CLI\n\nA command-line tool for creating demo apps.\n",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "create-demo-app",
                "bin": {"create-demo-app": "./dist/index.js"},
                "scripts": {
                    "build": "tsup",
                    "lint": "eslint .",
                    "typecheck": "tsc --noEmit",
                },
                "devDependencies": {
                    "typescript": "^5.0.0",
                    "eslint": "^9.0.0",
                    "tsup": "^8.0.0",
                },
            }
        ),
        encoding="utf-8",
    )

    facts = scan_repo(tmp_path)
    evidence, missing = _check_cli_tool(tmp_path, facts)

    assert any("Node package.json bin entry detected" in item for item in evidence)
    assert missing == []


def test_node_check_script_counts_as_typecheck_evidence(tmp_path) -> None:
    import json

    from evagix.scanning.repository import scan_repo

    (tmp_path / "README.md").write_text("# Node Check Repo\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "node-check-repo",
                "scripts": {
                    "check": "tsc --noEmit",
                    "build": "vite build",
                    "lint": "eslint .",
                },
                "devDependencies": {
                    "typescript": "^5.0.0",
                    "vite": "^6.0.0",
                    "eslint": "^9.0.0",
                },
            }
        ),
        encoding="utf-8",
    )

    facts = scan_repo(tmp_path)

    assert "typecheck" in facts.commands
    assert "typescript" in facts.typecheck_tools


def test_starter_template_validation_commands_do_not_fail_missing_tests(tmp_path) -> None:
    import json

    from evagix.scanning.repository import scan_repo
    from evagix.validation.doctor import doctor_repo

    (tmp_path / "README.md").write_text(
        "# Create Demo App\n\nA starter template CLI for demo apps.\n",
        encoding="utf-8",
    )
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        "name: CI\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n",
        encoding="utf-8",
    )
    (tmp_path / "cli" / "template").mkdir(parents=True)
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "create-demo-root",
                "scripts": {
                    "lint": "eslint .",
                    "typecheck": "tsc --noEmit",
                    "build": "tsup",
                    "check": "npm run lint && npm run typecheck",
                },
                "devDependencies": {
                    "typescript": "^5.0.0",
                    "eslint": "^9.0.0",
                    "tsup": "^8.0.0",
                },
            }
        ),
        encoding="utf-8",
    )

    facts = scan_repo(tmp_path)
    report = doctor_repo(tmp_path, facts, strict=True)

    missing_test = [finding for finding in report.findings if finding.code == "missing-test"]

    assert missing_test
    assert missing_test[0].severity == "info"
    assert missing_test[0].penalty == 0
    assert report.score >= 80


def test_node_mastra_dependency_counts_as_llm_evidence(tmp_path):
    import json

    from evagix.scanning.repository import scan_repo

    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {
                    "@mastra/core": "^1.0.0",
                    "@mastra/memory": "^1.0.0",
                    "openai": "^5.0.0",
                }
            }
        ),
        encoding="utf-8",
    )

    facts = scan_repo(tmp_path)

    assert "mastra" in facts.llm_tools
    assert "openai" in facts.llm_tools
