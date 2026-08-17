from __future__ import annotations

from collections.abc import Iterable

from evagix.report_models import DoctorFinding


def section(title: str) -> str:
    return f"{title}\n" + "-" * len(title) + "\n"


def format_findings(findings: Iterable[DoctorFinding]) -> list[str]:
    return [f"- **{item.severity}** `{item.code}`: {item.message}" for item in findings]


def status_label(ok: bool) -> str:
    return "pass" if ok else "needs-attention"
