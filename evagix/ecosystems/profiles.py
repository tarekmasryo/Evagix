from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class EcosystemProfile:
    id: str
    name: str
    language: str
    support: str
    marker_files: tuple[str, ...] = ()
    lockfiles: tuple[str, ...] = ()
    install_commands: tuple[str, ...] = ()
    test_commands: tuple[str, ...] = ()
    build_commands: tuple[str, ...] = ()
    lint_commands: tuple[str, ...] = ()
    typecheck_commands: tuple[str, ...] = ()
    framework_markers: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class EcosystemDetection:
    id: str
    name: str
    path: str
    language: str
    support: str
    confidence: str
    evidence: tuple[str, ...] = ()
    package_manager: str = ""
    frameworks: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    commands: dict[str, str] = field(default_factory=dict)
    command_evidence: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ECOSYSTEM_PROFILES: dict[str, EcosystemProfile] = {
    "python": EcosystemProfile(
        id="python",
        name="Python",
        language="python",
        support="deep",
        marker_files=("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "requirements-dev.txt"),
        lockfiles=("uv.lock", "poetry.lock", "pdm.lock"),
        install_commands=(
            "uv sync --all-extras --dev",
            'python -m pip install -e ".[dev]"',
            "python -m pip install -r requirements.txt",
        ),
        test_commands=("python -m pytest", "pytest"),
        build_commands=("python -m build",),
        lint_commands=("ruff check .", "flake8 .", "pylint ."),
        typecheck_commands=("mypy .", "pyright"),
        framework_markers={
            "fastapi": ("fastapi",),
            "django": ("django", "manage.py"),
            "flask": ("flask",),
            "typer": ("typer",),
            "click": ("click",),
            "streamlit": ("streamlit", "streamlit_app.py"),
            "langchain": ("langchain",),
            "llama-index": ("llama-index", "llama_index"),
            "pandas": ("pandas",),
            "scikit-learn": ("scikit-learn", "sklearn"),
            "torch": ("torch", "pytorch"),
        },
    ),
    "node": EcosystemProfile(
        id="node",
        name="Node.js / TypeScript",
        language="javascript/typescript",
        support="deep",
        marker_files=("package.json",),
        lockfiles=("pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb", "package-lock.json", "npm-shrinkwrap.json"),
        install_commands=(
            "npm ci",
            "pnpm install --frozen-lockfile",
            "yarn install --frozen-lockfile",
            "bun install --frozen-lockfile",
        ),
        test_commands=("npm test", "pnpm test", "yarn test", "bun test"),
        build_commands=("npm run build", "pnpm build", "yarn build", "bun run build"),
        lint_commands=("npm run lint", "pnpm lint", "yarn lint", "bun run lint"),
        typecheck_commands=("npm run typecheck", "pnpm typecheck", "yarn typecheck", "bun run typecheck"),
        framework_markers={
            "react": ("react",),
            "next.js": ("next", "next.config"),
            "vue": ("vue",),
            "svelte": ("svelte",),
            "vite": ("vite", "vite.config"),
            "express": ("express",),
            "nestjs": ("@nestjs/",),
            "jest": ("jest",),
            "vitest": ("vitest",),
            "playwright": ("playwright",),
            "cypress": ("cypress",),
            "typescript": ("typescript", "tsconfig.json"),
            "eslint": ("eslint",),
        },
    ),
    "go": EcosystemProfile(
        "go",
        "Go",
        "go",
        "basic",
        ("go.mod",),
        ("go.sum",),
        ("go mod download",),
        ("go test ./...",),
        ("go build ./...",),
        ("go vet ./...", "golangci-lint run"),
        (),
        {
            "gin": ("github.com/gin-gonic/gin",),
            "fiber": ("github.com/gofiber/fiber",),
            "echo": ("github.com/labstack/echo",),
            "cobra": ("github.com/spf13/cobra",),
        },
    ),
    "rust": EcosystemProfile(
        "rust",
        "Rust",
        "rust",
        "basic",
        ("Cargo.toml",),
        ("Cargo.lock",),
        (),
        ("cargo test",),
        ("cargo build",),
        ("cargo clippy --all-targets --all-features",),
        (),
        {"axum": ("axum",), "actix": ("actix-web",), "tokio": ("tokio",), "clap": ("clap",)},
    ),
    "java_maven": EcosystemProfile(
        "java_maven",
        "Java / Maven",
        "java",
        "basic",
        ("pom.xml",),
        (),
        (),
        ("mvn test",),
        ("mvn package",),
        (),
        (),
        {"spring boot": ("spring-boot",), "junit": ("junit",)},
    ),
    "java_gradle": EcosystemProfile(
        "java_gradle",
        "Java/Kotlin / Gradle",
        "java/kotlin",
        "basic",
        ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"),
        ("gradle.lockfile",),
        (),
        ("./gradlew test", "gradle test"),
        ("./gradlew build", "gradle build"),
        (),
        (),
        {"spring boot": ("org.springframework.boot", "spring-boot"), "junit": ("junit",)},
    ),
    "dotnet": EcosystemProfile(
        "dotnet",
        ".NET",
        "csharp",
        "basic",
        ("*.csproj", "*.sln"),
        (),
        ("dotnet restore",),
        ("dotnet test",),
        ("dotnet build",),
        (),
        (),
        {"asp.net": ("Microsoft.AspNetCore",), "xunit": ("xunit",), "nunit": ("nunit",), "mstest": ("mstest",)},
    ),
    "php": EcosystemProfile(
        "php",
        "PHP / Composer",
        "php",
        "basic",
        ("composer.json",),
        ("composer.lock",),
        ("composer install",),
        ("composer test", "vendor/bin/phpunit"),
        (),
        (),
        (),
        {"laravel": ("laravel/framework",), "symfony": ("symfony/",), "phpunit": ("phpunit",)},
    ),
    "ruby": EcosystemProfile(
        "ruby",
        "Ruby / Bundler",
        "ruby",
        "basic",
        ("Gemfile", "Rakefile"),
        ("Gemfile.lock",),
        ("bundle install",),
        ("bundle exec rake test", "bundle exec rspec"),
        (),
        (),
        (),
        {"rails": ("rails",), "rspec": ("rspec",), "minitest": ("minitest",)},
    ),
    "docker": EcosystemProfile(
        "docker",
        "Docker",
        "docker",
        "basic",
        ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"),
        (),
        (),
        (),
        ("docker build .",),
        (),
        (),
        {},
    ),
    "terraform": EcosystemProfile(
        "terraform",
        "Terraform",
        "terraform",
        "basic",
        ("*.tf",),
        (".terraform.lock.hcl",),
        ("terraform init",),
        (),
        (),
        ("terraform validate", "terraform plan"),
        (),
        {},
    ),
    "github_actions": EcosystemProfile(
        "github_actions",
        "GitHub Actions",
        "ci",
        "basic",
        (".github/workflows/*.yml", ".github/workflows/*.yaml"),
        (),
        (),
        (),
        (),
        (),
        (),
        {},
    ),
}
