from __future__ import annotations

from typing import cast

from evagix.core.models import CommandEvidence, Confidence
from evagix.model import RepoFacts


def command_evidence(facts: RepoFacts) -> tuple[CommandEvidence, ...]:
    items: list[CommandEvidence] = []
    for name, command in sorted(facts.commands.items()):
        source = facts.command_sources.get(name)
        items.append(
            CommandEvidence(
                name=name,
                command=command,
                source_file=source.source if source else "",
                confidence=cast(Confidence, source.confidence if source else "medium"),
            )
        )
    return tuple(items)
