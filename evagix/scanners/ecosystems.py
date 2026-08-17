from __future__ import annotations

from pathlib import Path

from evagix.ecosystems import EcosystemDetection, ecosystem_payload
from evagix.ecosystems import detect_ecosystems as _detect_ecosystems


def detect_ecosystem_facts(root: Path) -> list[EcosystemDetection]:
    return _detect_ecosystems(root)


def detect_ecosystem_payload(root: Path) -> list[dict[str, object]]:
    return ecosystem_payload(_detect_ecosystems(root))
