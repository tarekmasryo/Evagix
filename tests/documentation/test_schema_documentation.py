from __future__ import annotations

import json
import re
from pathlib import Path

from evagix.targets import TARGET_ADAPTERS


def test_documented_schema_paths_exist() -> None:
    docs = Path("docs/schemas.md").read_text(encoding="utf-8")
    schema_paths = sorted(set(re.findall(r"`(evagix/schemas/[^`]+\.schema\.json)`", docs)))

    assert schema_paths
    assert all(Path(path).is_file() for path in schema_paths)

    actual_schema_paths = sorted(path.as_posix() for path in Path("evagix/schemas").glob("*.schema.json"))
    assert schema_paths == actual_schema_paths


def test_packaged_schema_files_are_valid_json() -> None:
    schema_paths = sorted(Path("evagix/schemas").glob("*.schema.json"))

    assert schema_paths
    for path in schema_paths:
        json.loads(path.read_text(encoding="utf-8"))


def test_configuration_documents_all_supported_targets() -> None:
    docs = Path("docs/configuration.md").read_text(encoding="utf-8")

    for name, adapter in TARGET_ADAPTERS.items():
        assert f"| `{name}` | `{adapter.path}` |" in docs
