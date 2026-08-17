from __future__ import annotations

from pathlib import Path

from evagix.ecosystems.commands import command_supported_by_ecosystem, ecosystem_payload, support_matrix_rows
from evagix.ecosystems.manifests import _detect_simple_manifests
from evagix.ecosystems.node import _detect_node
from evagix.ecosystems.profiles import EcosystemDetection
from evagix.ecosystems.python import _detect_python
from evagix.ecosystems.utils import _dedupe_detections


def detect_ecosystems(
    root: Path,
    ignored_paths: set[str] | None = None,
    *,
    warnings: list[str] | None = None,
) -> list[EcosystemDetection]:
    root = root.resolve()
    ignored = ignored_paths or set()
    detections: list[EcosystemDetection] = []
    detections.extend(_detect_python(root, ignored, warnings))
    detections.extend(_detect_node(root, ignored, warnings))
    detections.extend(_detect_simple_manifests(root, ignored, warnings))
    return _dedupe_detections(detections)


__all__ = [
    "detect_ecosystems",
    "command_supported_by_ecosystem",
    "ecosystem_payload",
    "support_matrix_rows",
    "EcosystemDetection",
]
