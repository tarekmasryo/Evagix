"""Measure repository scanning on a deterministic, disposable local fixture."""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import io
import json
import platform
import pstats
import statistics
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from evagix.scanner import scan_repo
from evagix.validators import doctor_repo


def _create_fixture(root: Path, file_count: int) -> None:
    root.mkdir()
    (root / "README.md").write_text("# Synthetic service\n\nLocal deterministic benchmark fixture.\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname="scan-benchmark"\nversion="0.0.0"\ndependencies=[]\n', encoding="utf-8"
    )
    for index in range(file_count - 2):
        path = root / "src" / f"package_{index // 100:02d}" / f"module_{index:04d}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("VALUE = 1\n", encoding="utf-8")


def _digest(payload: object) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _measure(root: Path) -> dict[str, Any]:
    start = time.perf_counter()
    facts = scan_repo(root)
    scanned = time.perf_counter()
    report = doctor_repo(root, facts)
    finished = time.perf_counter()
    return {
        "scan_repo_seconds": scanned - start,
        "doctor_repo_seconds": finished - scanned,
        "scan_plus_doctor_seconds": finished - start,
        "facts_sha256": _digest(asdict(facts)),
        "doctor_sha256": _digest(asdict(report)),
    }


def _profile(root: Path) -> dict[str, str]:
    scan_profile = cProfile.Profile()
    facts = scan_profile.runcall(scan_repo, root)
    doctor_profile = cProfile.Profile()
    doctor_profile.runcall(doctor_repo, root, facts)
    results: dict[str, str] = {}
    for name, profiler in (("scan_repo", scan_profile), ("doctor_repo", doctor_profile)):
        stream = io.StringIO()
        pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats("cumulative").print_stats(25)
        results[name] = stream.getvalue()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=int, default=2000, help="Total fixture files, including two metadata files.")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--profile", action="store_true", help="Run a separate profile after the timed samples.")
    parser.add_argument("--output", type=Path, help="Create a new JSON report; existing files are never overwritten.")
    args = parser.parse_args()
    if args.files < 3 or args.repeats < 1 or args.warmups < 0:
        parser.error("files must be >= 3, repeats >= 1, and warmups >= 0")
    if args.output is not None and args.output.exists():
        parser.error("output already exists; select a new report path")
    with tempfile.TemporaryDirectory(prefix="evagix-scan-benchmark-") as temporary:
        root = Path(temporary) / "repo"
        _create_fixture(root, args.files)
        for _ in range(args.warmups):
            _measure(root)
        samples = [_measure(root) for _ in range(args.repeats)]
        result = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
            "fixture_files": args.files,
            "warmups": args.warmups,
            "samples": samples,
            "median_seconds": {
                key: statistics.median(sample[key] for sample in samples)
                for key in ("scan_repo_seconds", "doctor_repo_seconds", "scan_plus_doctor_seconds")
            },
            "profiles": _profile(root) if args.profile else {},
            "notes": [
                "Fixture creation and hashing are outside the measured intervals.",
                "doctor_repo uses the immediately preceding scan_repo facts; it does not include another scan.",
                "Profile samples are separate from timing samples and include profiler overhead.",
                "Profiler call counts for generators include resumes, not only new traversals.",
                "No project commands are executed, and no network access is required.",
                "This synthetic Python fixture is not evidence of performance on arbitrary repositories.",
            ],
        }
    content = json.dumps(result, indent=2) + "\n"
    if args.output is None:
        print(content, end="")
    else:
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(content)
        print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
