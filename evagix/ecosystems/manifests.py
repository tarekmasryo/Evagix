from __future__ import annotations

from pathlib import Path

from evagix.ecosystems.profiles import EcosystemDetection
from evagix.ecosystems.utils import (
    _detect_frameworks,
    _find_glob_markers,
    _find_marker_files,
    _ignored,
    _read_json,
    _rel,
    _safe_child,
    _safe_read,
    _scope,
)


def _detect_simple_manifests(
    root: Path,
    ignored: set[str],
    warnings: list[str] | None = None,
) -> list[EcosystemDetection]:
    detections: list[EcosystemDetection] = []
    simple = [
        ("go", {"go.mod"}, _go_detection),
        ("rust", {"Cargo.toml"}, _rust_detection),
        ("java_maven", {"pom.xml"}, _maven_detection),
        (
            "java_gradle",
            {"build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"},
            _gradle_detection,
        ),
        ("php", {"composer.json"}, _php_detection),
        ("ruby", {"Gemfile"}, _ruby_detection),
    ]
    for _, markers, builder in simple:
        for marker in _find_marker_files(root, markers, ignored, warnings):
            detections.append(builder(root, marker))
    for marker in _find_glob_markers(root, "*.csproj", ignored, warnings) + _find_glob_markers(
        root, "*.sln", ignored, warnings
    ):
        detections.append(_dotnet_detection(root, marker))
    docker_markers = _find_marker_files(
        root,
        {"Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"},
        ignored,
        warnings,
    )
    if docker_markers:
        detections.append(
            EcosystemDetection(
                id="docker",
                name="Docker",
                path=".",
                language="",
                support="basic",
                confidence="high",
                evidence=tuple(sorted(_rel(path, root) for path in docker_markers)),
                package_manager="",
                commands={"build": "docker build ."}
                if any(path.name == "Dockerfile" for path in docker_markers)
                else {},
                metadata={"category": "container_platform", "platform": "docker"},
            )
        )
    tf_markers = _find_glob_markers(root, "*.tf", ignored, warnings)
    if tf_markers:
        detections.append(
            EcosystemDetection(
                id="terraform",
                name="Terraform",
                path=".",
                language="",
                support="basic",
                confidence="high",
                evidence=tuple(sorted(_rel(path, root) for path in tf_markers[:8])),
                package_manager="",
                tools=("terraform",),
                commands={"infra_validate": "terraform validate", "infra_plan": "terraform plan"},
                command_evidence={"infra_validate": _rel(tf_markers[0], root), "infra_plan": _rel(tf_markers[0], root)},
                metadata={"category": "infrastructure_tool", "tool": "terraform"},
            )
        )
    workflow_dir = root / ".github" / "workflows"
    if workflow_dir.exists():
        workflows = [
            path
            for path in workflow_dir.glob("*.y*ml")
            if _safe_child(root, path) and not _ignored(root, path, ignored)
        ]
        if workflows:
            detections.append(
                EcosystemDetection(
                    id="github_actions",
                    name="GitHub Actions",
                    path=".",
                    language="",
                    support="basic",
                    confidence="high",
                    evidence=tuple(sorted(_rel(path, root) for path in workflows[:12])),
                    package_manager="",
                    tools=("github-actions",),
                    metadata={"category": "ci_platform", "platform": "github-actions"},
                )
            )
    return detections


def _go_detection(root: Path, marker: Path) -> EcosystemDetection:
    rel = _rel(marker.parent, root)
    text = _safe_read(marker).lower()
    frameworks = _detect_frameworks("go", text, marker.parent)
    return EcosystemDetection(
        "go",
        "Go",
        rel,
        "go",
        "basic",
        "high",
        (_rel(marker, root),),
        "go modules",
        tuple(frameworks),
        (),
        {
            "install": _scope(rel, "go mod download"),
            "test": _scope(rel, "go test ./..."),
            "build": _scope(rel, "go build ./..."),
            "lint": _scope(rel, "go vet ./..."),
        },
        {
            "install": _rel(marker, root),
            "test": _rel(marker, root),
            "build": _rel(marker, root),
            "lint": _rel(marker, root),
        },
    )


def _rust_detection(root: Path, marker: Path) -> EcosystemDetection:
    rel = _rel(marker.parent, root)
    text = _safe_read(marker).lower()
    frameworks = _detect_frameworks("rust", text, marker.parent)
    return EcosystemDetection(
        "rust",
        "Rust",
        rel,
        "rust",
        "basic",
        "high",
        (_rel(marker, root),),
        "cargo",
        tuple(frameworks),
        ("cargo",),
        {
            "test": _scope(rel, "cargo test"),
            "build": _scope(rel, "cargo build"),
            "lint": _scope(rel, "cargo clippy --all-targets --all-features"),
            "format": _scope(rel, "cargo fmt"),
        },
        {
            "test": _rel(marker, root),
            "build": _rel(marker, root),
            "lint": _rel(marker, root),
            "format": _rel(marker, root),
        },
    )


def _maven_detection(root: Path, marker: Path) -> EcosystemDetection:
    rel = _rel(marker.parent, root)
    text = _safe_read(marker).lower()
    frameworks = _detect_frameworks("java_maven", text, marker.parent)
    return EcosystemDetection(
        "java_maven",
        "Java / Maven",
        rel,
        "java",
        "basic",
        "high",
        (_rel(marker, root),),
        "maven",
        tuple(frameworks),
        (),
        {"test": _scope(rel, "mvn test"), "build": _scope(rel, "mvn package")},
        {"test": _rel(marker, root), "build": _rel(marker, root)},
    )


def _gradle_detection(root: Path, marker: Path) -> EcosystemDetection:
    directory = marker.parent
    rel = _rel(directory, root)
    runner = "./gradlew" if (directory / "gradlew").exists() else "gradle"
    text = _safe_read(marker).lower()
    frameworks = _detect_frameworks("java_gradle", text, directory)
    return EcosystemDetection(
        "java_gradle",
        "Java/Kotlin / Gradle",
        rel,
        "java/kotlin",
        "basic",
        "high",
        (_rel(marker, root),),
        "gradle",
        tuple(frameworks),
        (),
        {"test": _scope(rel, f"{runner} test"), "build": _scope(rel, f"{runner} build")},
        {"test": _rel(marker, root), "build": _rel(marker, root)},
    )


def _dotnet_detection(root: Path, marker: Path) -> EcosystemDetection:
    rel = _rel(marker.parent, root)
    text = _safe_read(marker).lower()
    frameworks = _detect_frameworks("dotnet", text, marker.parent)
    return EcosystemDetection(
        "dotnet",
        ".NET",
        rel,
        "csharp",
        "basic",
        "high",
        (_rel(marker, root),),
        "dotnet",
        tuple(frameworks),
        (),
        {
            "install": _scope(rel, "dotnet restore"),
            "test": _scope(rel, "dotnet test"),
            "build": _scope(rel, "dotnet build"),
        },
        {"install": _rel(marker, root), "test": _rel(marker, root), "build": _rel(marker, root)},
    )


def _php_detection(root: Path, marker: Path) -> EcosystemDetection:
    rel = _rel(marker.parent, root)
    data = _read_json(marker)
    deps = (
        "\n".join(list((data.get("require") or {}).keys()) + list((data.get("require-dev") or {}).keys())).lower()
        if data
        else ""
    )
    frameworks = _detect_frameworks("php", deps, marker.parent)
    scripts = data.get("scripts", {}) if isinstance(data.get("scripts"), dict) else {}
    commands = {"install": _scope(rel, "composer install")}
    if "test" in scripts:
        commands["test"] = _scope(rel, "composer test")
    elif "phpunit" in deps:
        commands["test"] = _scope(rel, "vendor/bin/phpunit")
    return EcosystemDetection(
        "php",
        "PHP / Composer",
        rel,
        "php",
        "basic",
        "high",
        (_rel(marker, root),),
        "composer",
        tuple(frameworks),
        tuple(sorted({"phpunit"} if "phpunit" in deps else set())),
        commands,
        {key: _rel(marker, root) for key in commands},
    )


def _ruby_detection(root: Path, marker: Path) -> EcosystemDetection:
    rel = _rel(marker.parent, root)
    text = _safe_read(marker).lower()
    frameworks = _detect_frameworks("ruby", text, marker.parent)
    commands = {"install": _scope(rel, "bundle install")}
    rakefile = marker.parent / "Rakefile"
    if rakefile.exists():
        commands["test"] = _scope(rel, "bundle exec rake test")
    elif "rspec" in text:
        commands["test"] = _scope(rel, "bundle exec rspec")
    return EcosystemDetection(
        "ruby",
        "Ruby / Bundler",
        rel,
        "ruby",
        "basic",
        "high",
        (_rel(marker, root),),
        "bundler",
        tuple(frameworks),
        tuple(sorted({"rspec"} if "rspec" in text else set())),
        commands,
        {key: _rel(marker, root) for key in commands},
    )
