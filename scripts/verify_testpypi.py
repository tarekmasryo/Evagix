from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

INDEXES = {
    "testpypi": (
        "https://test.pypi.org/pypi",
        frozenset({"test-files.pythonhosted.org"}),
        "TestPyPI",
    ),
    "pypi": (
        "https://pypi.org/pypi",
        frozenset({"files.pythonhosted.org"}),
        "PyPI",
    ),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _expected_distributions(directory: Path) -> dict[str, Path]:
    paths = sorted([*directory.glob("*.whl"), *directory.glob("*.tar.gz")])
    if not paths:
        raise ValueError(f"No wheel or source distribution found in {directory}")
    return {path.name: path for path in paths}


def _verify_checksum_manifest(path: Path, expected: dict[str, Path]) -> None:
    manifest: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        digest, separator, raw_name = line.partition("  ")
        if not separator:
            raise ValueError(f"Malformed checksum line: {line!r}")
        manifest[Path(raw_name.strip()).name] = digest.strip().lower()
    local = {name: _sha256(file_path) for name, file_path in expected.items()}
    if manifest != local:
        raise ValueError("SHA256SUMS does not exactly match the built release distributions")


def _release_metadata(
    package: str,
    version: str,
    *,
    attempts: int,
    retry_seconds: float,
    index: str = "testpypi",
) -> dict[str, Any]:
    metadata_base, _, label = INDEXES[index]
    package_name = urllib.parse.quote(package, safe="")
    package_version = urllib.parse.quote(version, safe="")
    url = f"{metadata_base}/{package_name}/{package_version}/json"
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "evagix-release-verifier/0.1"})
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
            if isinstance(payload, dict) and payload.get("urls"):
                return payload
            last_error = ValueError(f"{label} metadata did not contain release files")
        except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
            last_error = exc
        if attempt < attempts:
            time.sleep(retry_seconds)
    raise RuntimeError(f"{label} release metadata was unavailable after {attempts} attempts") from last_error


def _download_and_verify(
    metadata: dict[str, Any],
    expected: dict[str, Path],
    destination: Path,
    *,
    index: str = "testpypi",
) -> None:
    _, allowed_file_hosts, label = INDEXES[index]
    rows = metadata.get("urls")
    if not isinstance(rows, list):
        raise ValueError(f"{label} metadata has an invalid urls field")
    uploaded = {str(row.get("filename", "")): row for row in rows if isinstance(row, dict)}
    if set(uploaded) != set(expected):
        raise ValueError(f"{label} filenames do not exactly match the built release distributions")

    destination.mkdir(parents=True, exist_ok=True)
    for name, source in expected.items():
        row = uploaded[name]
        url = str(row.get("url", ""))
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in allowed_file_hosts:
            raise ValueError(f"Unexpected {label} file URL for {name}")
        expected_digest = _sha256(source)
        declared_digest = str(row.get("digests", {}).get("sha256", "")).lower()
        if declared_digest != expected_digest:
            raise ValueError(f"{label} SHA-256 does not match the built artifact: {name}")
        request = urllib.request.Request(url, headers={"User-Agent": "evagix-release-verifier/0.1"})
        with urllib.request.urlopen(request, timeout=60) as response:
            content = response.read(source.stat().st_size + 1)
        if len(content) != source.stat().st_size or hashlib.sha256(content).hexdigest() != expected_digest:
            raise ValueError(f"Downloaded {label} artifact differs from the built artifact: {name}")
        (destination / name).write_bytes(content)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a Python package index against one locally built artifact set."
    )
    parser.add_argument("--index", choices=sorted(INDEXES), default="testpypi")
    parser.add_argument("--package", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--expected-dir", type=Path, required=True)
    parser.add_argument("--checksums", type=Path, required=True)
    parser.add_argument("--download-dir", type=Path, required=True)
    parser.add_argument("--attempts", type=int, default=18)
    parser.add_argument("--retry-seconds", type=float, default=10.0)
    args = parser.parse_args()

    if args.attempts < 1 or args.retry_seconds < 0:
        parser.error("attempts must be positive and retry-seconds must be non-negative")
    expected = _expected_distributions(args.expected_dir)
    _verify_checksum_manifest(args.checksums, expected)
    metadata = _release_metadata(
        args.package,
        args.version,
        attempts=args.attempts,
        retry_seconds=args.retry_seconds,
        index=args.index,
    )
    _download_and_verify(metadata, expected, args.download_dir, index=args.index)
    label = INDEXES[args.index][2]
    print(f"Verified {len(expected)} exact {label} distribution(s) for {args.package} {args.version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
