from __future__ import annotations

from pathlib import Path

from evagix.core.io import safe_read_text
from evagix.core.paths import repo_relative
from evagix.model import RepoFacts
from evagix.scanner_utils import TraversalDiagnostics, _iter_repo_files

_TEXT_LIMIT = 120_000
_MAX_SCAN_ENTRIES = 20_000
_MAX_DOCS_LAYOUT_ENTRIES = 3_000


def is_docs_or_education_repo(root: Path, facts: RepoFacts) -> bool:
    """Return True for course, cookbook, tutorial, and docs-first repositories.

    This is intentionally evidence-based and conservative: examples/docs alone
    are not enough, because most production libraries also have examples. The
    repo needs a strong name/readme signal or multiple education/documentation
    layout signals.
    """
    name = facts.root_name.lower().replace("_", "-")
    readme = _readme_text(root).lower()
    folders = {item.lower().replace("\\", "/").split("/", 1)[0] for item in facts.folders}

    name_markers = {
        "beginner",
        "beginners",
        "cookbook",
        "course",
        "curriculum",
        "tutorial",
        "tutorials",
        "workshop",
        "handbook",
        "guide",
        "learn",
        "learning",
        "examples",
    }
    readme_markers = (
        "course",
        "curriculum",
        "tutorial",
        "tutorials",
        "workshop",
        "hands-on",
        "for beginners",
        "learning path",
        "learn how",
        "lessons",
        "notebooks",
        "cookbook",
        "examples for",
        "educational",
    )
    folder_markers = {
        "docs",
        "documentation",
        "examples",
        "notebooks",
        "lessons",
        "lesson",
        "tutorials",
        "tutorial",
        "samples",
        "sample",
        "chapters",
        "workshops",
        "workshop",
    }

    score = 0
    if any(marker in name for marker in name_markers):
        score += 2
    if sum(1 for marker in readme_markers if marker in readme) >= 2:
        score += 2
    elif any(marker in readme for marker in readme_markers):
        score += 1
    if len(folders.intersection(folder_markers)) >= 2:
        score += 1
    if _docs_heavy_layout(root, facts):
        score += 1

    strong_education_identity = _has_strong_education_identity(name, readme, folders)

    # A root package/service with strong application signals should not become
    # docs-first merely because it has examples or tutorials. However, course
    # repositories can include small lesson apps, notebooks, or quizzes without
    # being application repositories themselves.
    if score < 3 and not strong_education_identity:
        return False
    if strong_education_identity:
        return True
    return not _has_strong_root_application_evidence(root, facts)


def _has_strong_education_identity(name: str, readme: str, folders: set[str]) -> bool:
    course_name_markers = (
        "for-beginners",
        "beginners",
        "beginner",
        "course",
        "curriculum",
        "tutorial",
        "tutorials",
        "workshop",
        "learn",
        "learning",
    )
    course_readme_markers = (
        "curriculum",
        "course",
        "lessons",
        "lesson",
        "tutorial",
        "tutorials",
        "learning path",
        "for beginners",
        "hands-on",
        "notebooks",
        "education",
        "educational",
    )
    course_folder_markers = {
        "docs",
        "documentation",
        "translations",
        "translated_images",
        "sketchnotes",
        "notebooks",
        "lessons",
        "lesson",
        "chapters",
        "workshops",
        "workshop",
    }

    name_hit = any(marker in name for marker in course_name_markers)
    readme_hits = sum(1 for marker in course_readme_markers if marker in readme)
    folder_hits = len(folders.intersection(course_folder_markers))
    numbered_lesson_folders = sum(1 for folder in folders if _looks_like_numbered_lesson_folder(folder))

    if name_hit and (readme_hits >= 1 or folder_hits >= 1 or numbered_lesson_folders >= 2):
        return True
    return readme_hits >= 3 and (folder_hits >= 1 or numbered_lesson_folders >= 2)


def _looks_like_numbered_lesson_folder(folder: str) -> bool:
    prefix = folder.split("-", 1)[0].strip()
    return "-" in folder and prefix.isdigit()


def is_library_or_toolkit_repo(root: Path, facts: RepoFacts) -> bool:
    """Return True for package/library/toolkit repositories rather than apps."""
    if is_docs_or_education_repo(root, facts):
        return False
    if _is_app_or_service_like(root, facts):
        return False

    name = facts.root_name.lower().replace("_", "-")
    readme = _readme_text(root).lower()
    package_evidence, _ = python_package_evidence(root)
    package_like = bool(package_evidence) or bool(facts.package_managers)

    name_markers = (
        "sdk",
        "client",
        "library",
        "toolkit",
        "framework",
        "kernel",
        "agents",
        "agent",
        "langchain",
        "llama-index",
        "smolagents",
    )
    readme_markers = (
        "library",
        "sdk",
        "toolkit",
        "framework",
        "python package",
        "pip install",
        "client library",
        "package",
        "api reference",
    )
    has_library_marker = any(marker in name for marker in name_markers) or any(
        marker in readme for marker in readme_markers
    )
    return package_like and has_library_marker


def python_package_evidence(root: Path) -> tuple[list[str], list[str]]:
    """Find Python packaging/source evidence in root or common monorepo subprojects."""
    packaging_files: list[str] = []
    source_dirs: list[str] = []
    diagnostics = TraversalDiagnostics(max_visited_entries=_MAX_SCAN_ENTRIES)
    for path in _iter_repo_paths(root, diagnostics=diagnostics):
        if path.name in {"pyproject.toml", "setup.py", "setup.cfg"}:
            if path.name == "pyproject.toml" and not _looks_like_python_packaging_file(root, path):
                continue
            packaging_files.append(repo_relative(root, path))
            parent = path.parent
            if (parent / "src").is_dir():
                source_dirs.append(repo_relative(root, parent / "src"))
            for child in _safe_iterdir(parent):
                if child.is_dir() and (child / "__init__.py").is_file():
                    source_dirs.append(repo_relative(root, child))
        elif path.name == "__init__.py" and path.parent != root:
            parent_name = path.parent.name
            if parent_name not in {"tests", "test", "docs", "examples", "notebooks"}:
                source_dirs.append(repo_relative(root, path.parent))

    evidence: list[str] = []
    missing: list[str] = []
    if packaging_files:
        shown = ", ".join(sorted(set(packaging_files))[:4])
        evidence.append("Python packaging metadata detected" + (f": {shown}" if shown else ""))
    else:
        missing.append("Python packaging metadata")
    if source_dirs:
        shown = ", ".join(sorted(set(source_dirs))[:4])
        evidence.append("package/source directory detected" + (f": {shown}" if shown else ""))
    else:
        missing.append("package/source directory")
    if diagnostics.incomplete:
        missing.append(diagnostics.warning("Python package evidence discovery"))
    return evidence, missing


def python_cli_entrypoint_evidence(root: Path) -> tuple[list[str], list[str]]:
    evidence: list[str] = []
    missing: list[str] = []
    diagnostics = TraversalDiagnostics(max_visited_entries=_MAX_SCAN_ENTRIES)
    for path in _iter_repo_paths(root, diagnostics=diagnostics):
        if path.name != "pyproject.toml":
            continue
        try:
            text = safe_read_text(path, root=root, max_chars=200_000).lower()
        except (OSError, UnicodeError):
            continue
        if "[project.scripts]" in text or "[tool.poetry.scripts]" in text:
            evidence.append(f"console script entry point detected: {repo_relative(root, path)}")
            break
    if not evidence:
        missing.append("console script entry point in pyproject.toml")
        if diagnostics.incomplete:
            missing.append(diagnostics.warning("Python CLI entrypoint discovery"))
    return evidence, missing


def _is_app_or_service_like(root: Path, facts: RepoFacts) -> bool:
    if facts.is_backend_project or facts.is_dashboard_project:
        return True
    if facts.databases and ("docker-compose" in facts.container_platforms or facts.has_database_migrations):
        return True
    readme = _readme_text(root).lower()
    return any(marker in readme for marker in ("deploy", "self-host", "server", "backend api", "web app")) and any(
        marker in readme for marker in ("docker", "database", "postgres", "redis", "uvicorn", "gunicorn")
    )


def _has_strong_root_application_evidence(root: Path, facts: RepoFacts) -> bool:
    if facts.is_backend_project or facts.is_dashboard_project:
        return True
    return any((root / name).exists() for name in ("Dockerfile", "docker-compose.yml", "compose.yml")) and bool(
        facts.databases or facts.runtimes
    )


def _docs_heavy_layout(root: Path, facts: RepoFacts) -> bool:
    doc_count = 0
    code_count = 0
    diagnostics = TraversalDiagnostics(max_visited_entries=_MAX_DOCS_LAYOUT_ENTRIES)
    for path in _iter_repo_paths(root, max_entries=_MAX_DOCS_LAYOUT_ENTRIES, diagnostics=diagnostics):
        suffix = path.suffix.lower()
        if suffix in {".md", ".rst", ".ipynb"}:
            doc_count += 1
        elif suffix in {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".cs"}:
            code_count += 1
    if diagnostics.incomplete:
        warning = diagnostics.warning("Documentation-heavy layout detection")
        if warning not in facts.warnings:
            facts.warnings.append(warning)
    return doc_count >= 12 and doc_count >= code_count


def _readme_text(root: Path) -> str:
    for name in ("README.md", "readme.md", "README.rst", "README.txt"):
        path = root / name
        if path.exists():
            try:
                return safe_read_text(path, root=root, max_chars=_TEXT_LIMIT)
            except (OSError, UnicodeError):
                return ""
    return ""


def _looks_like_python_packaging_file(root: Path, path: Path) -> bool:
    try:
        text = safe_read_text(path, root=root, max_chars=200_000).lower()
    except (OSError, UnicodeError):
        return False
    markers = (
        "[project]",
        "[build-system]",
        "[tool.poetry]",
        "[tool.hatch",
        "[tool.pdm",
        "[tool.flit",
        "[tool.setuptools",
        "setup-tools",
        "setuptools",
        "poetry-core",
    )
    return any(marker in text for marker in markers)


def _iter_repo_paths(
    root: Path,
    *,
    max_entries: int | None = None,
    diagnostics: TraversalDiagnostics | None = None,
) -> list[Path]:
    effective_limit = _MAX_SCAN_ENTRIES if max_entries is None else max_entries
    state = diagnostics or TraversalDiagnostics(max_visited_entries=effective_limit)
    return list(
        _iter_repo_files(
            root,
            diagnostics=state,
            max_visited_entries=effective_limit,
        )
    )


def _safe_iterdir(path: Path) -> list[Path]:
    try:
        return sorted(path.iterdir(), key=lambda item: item.name)
    except (OSError, UnicodeError):
        return []
