from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

from scripts import verify_testpypi
from scripts.verify_testpypi import _download_and_verify, _expected_distributions, _verify_checksum_manifest


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def test_checksum_manifest_must_exactly_match_built_distributions(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = dist / "evagix-0.1.0-py3-none-any.whl"
    sdist = dist / "evagix-0.1.0.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")
    manifest = tmp_path / "SHA256SUMS"
    manifest.write_text(
        f"{_sha256(b'wheel')}  dist/{wheel.name}\n{_sha256(b'sdist')}  dist/{sdist.name}\n",
        encoding="utf-8",
    )

    expected = _expected_distributions(dist)
    _verify_checksum_manifest(manifest, expected)

    manifest.write_text(f"{_sha256(b'wheel')}  dist/{wheel.name}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not exactly match"):
        _verify_checksum_manifest(manifest, expected)


def test_testpypi_download_rejects_unexpected_file_host_before_network_access(tmp_path: Path) -> None:
    wheel = tmp_path / "evagix-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    metadata = {
        "urls": [
            {
                "filename": wheel.name,
                "url": f"https://example.invalid/{wheel.name}",
                "digests": {"sha256": _sha256(b"wheel")},
            }
        ]
    }

    with pytest.raises(ValueError, match="Unexpected TestPyPI file URL"):
        _download_and_verify(metadata, {wheel.name: wheel}, tmp_path / "download")


def test_production_pypi_download_accepts_only_the_production_file_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wheel = tmp_path / "evagix-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    metadata = {
        "urls": [
            {
                "filename": wheel.name,
                "url": f"https://files.pythonhosted.org/packages/{wheel.name}",
                "digests": {"sha256": _sha256(b"wheel")},
            }
        ]
    }
    monkeypatch.setattr(verify_testpypi.urllib.request, "urlopen", lambda request, timeout: io.BytesIO(b"wheel"))

    destination = tmp_path / "download"
    _download_and_verify(metadata, {wheel.name: wheel}, destination, index="pypi")

    assert (destination / wheel.name).read_bytes() == b"wheel"
