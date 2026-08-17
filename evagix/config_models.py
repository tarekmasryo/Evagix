from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class CustomTarget:
    name: str
    path: str
    output_format: str = "markdown"
    include: list[str] = field(default_factory=list)


@dataclass
class EvagixConfig:
    path: Path | None = None
    profiles: list[str] = field(default_factory=list)
    enabled_targets: dict[str, bool] = field(default_factory=dict)
    custom_targets: list[CustomTarget] = field(default_factory=list)
    fail_under: int = 80
    fail_on_stale: bool = True
    require_onboarding_pack: bool = False
    ignored_findings: set[str] = field(default_factory=set)
    severity_overrides: dict[str, str] = field(default_factory=dict)
    custom_rules: list[str] = field(default_factory=list)
    custom_forbidden_actions: list[str] = field(default_factory=list)
    custom_validation_commands: dict[str, str] = field(default_factory=dict)
    ignored_paths: list[str] = field(default_factory=list)
    readme_ignore_claims: set[str] = field(default_factory=set)
    parse_error: str = ""

    @property
    def exists(self) -> bool:
        return self.path is not None

    @property
    def valid(self) -> bool:
        return not self.parse_error
