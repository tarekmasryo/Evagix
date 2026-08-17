from __future__ import annotations

from pathlib import Path

from pytest import CaptureFixture

from evagix.cli import main


def test_init_ci_defaults_to_github_install_for_external_repos(tmp_path: Path) -> None:
    assert main(["init-ci", str(tmp_path), "--fail-under", "80"]) == 0
    workflow = (tmp_path / ".github" / "workflows" / "evagix.yml").read_text(encoding="utf-8")
    assert "git+https://github.com/tarekmasryo/Evagix.git@v0.1.0" in workflow
    assert "python -m pip install -e ." not in workflow


def test_init_ci_supports_pypi_and_editable_modes(tmp_path: Path) -> None:
    pypi_repo = tmp_path / "pypi"
    editable_repo = tmp_path / "editable"
    pypi_repo.mkdir()
    editable_repo.mkdir()

    assert main(["init-ci", str(pypi_repo), "--install-mode", "pypi", "--package-version", "0.1.0"]) == 0
    pypi_workflow = (pypi_repo / ".github" / "workflows" / "evagix.yml").read_text(encoding="utf-8")
    assert "python -m pip install evagix==0.1.0" in pypi_workflow

    assert main(["init-ci", str(editable_repo), "--install-mode", "editable"]) == 0
    editable_workflow = (editable_repo / ".github" / "workflows" / "evagix.yml").read_text(encoding="utf-8")
    assert "python -m pip install -e ." in editable_workflow


def test_init_ci_keeps_analysis_but_skips_sarif_upload_for_fork_prs(tmp_path: Path) -> None:
    assert main(["init-ci", str(tmp_path)]) == 0
    workflow = (tmp_path / ".github" / "workflows" / "evagix.yml").read_text(encoding="utf-8")

    assert "on:\n  pull_request:" in workflow
    assert "evagix check ." in workflow
    assert "evagix doctor . --strict" in workflow
    assert "evagix readme-audit . --strict" in workflow
    assert "evagix eval-context . --strict" in workflow
    assert "evagix report . --format sarif" in workflow
    assert "github/codeql-action/upload-sarif@" in workflow
    assert (
        "if: always() && (github.event_name != 'pull_request' || "
        "github.event.pull_request.head.repo.full_name == github.repository)" in workflow
    )
    assert "pull_request_target" not in workflow


def test_onboard_reports_existing_files_and_force_overwrites(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    assert main(["onboard", str(tmp_path)]) == 0
    assert main(["onboard", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "onboarding file(s) already exist" in err
    assert "evagix onboard . --force" in err
    assert main(["onboard", str(tmp_path), "--force"]) == 0


def test_init_ci_template_uses_selected_github_ref(tmp_path: Path) -> None:
    assert (
        main(
            [
                "init-ci",
                str(tmp_path),
                "--install-mode",
                "github",
                "--repo",
                "example/evagix",
                "--ref",
                "v9.9.9",
            ]
        )
        == 0
    )
    workflow = (tmp_path / ".github" / "workflows" / "evagix.yml").read_text(encoding="utf-8")
    assert "git+https://github.com/example/evagix.git@v9.9.9" in workflow
