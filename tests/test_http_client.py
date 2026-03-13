from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from wayback_export.http_client import UrlLibHttpClient


class _FakeResponse:
    def __init__(self, chunks: list[bytes], fail_after: int | None = None) -> None:
        self._chunks = chunks
        self._index = 0
        self._fail_after = fail_after

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, _size: int) -> bytes:
        if self._fail_after is not None and self._index >= self._fail_after:
            raise urllib.error.URLError("network dropped")
        if self._index >= len(self._chunks):
            return b""
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk


def test_download_file_success_uses_atomic_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"hello world"
    destination = tmp_path / "data.bin"

    def fake_urlopen(_request, timeout, context=None):
        assert timeout == 10
        return _FakeResponse([payload])

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = UrlLibHttpClient()
    size, checksum = client.download_file(
        "https://example.com/file.bin",
        destination=destination,
        timeout=10,
        user_agent="test-agent",
    )

    assert size == len(payload)
    assert checksum == hashlib.sha256(payload).hexdigest()
    assert destination.read_bytes() == payload
    assert not destination.with_name("data.bin.part").exists()


def test_download_file_failure_cleans_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "broken.bin"

    def fake_urlopen(_request, timeout, context=None):
        assert timeout == 10
        return _FakeResponse([b"partial"], fail_after=1)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = UrlLibHttpClient()

    with pytest.raises(RuntimeError, match="Download failed"):
        client.download_file(
            "https://example.com/file.bin",
            destination=destination,
            timeout=10,
            user_agent="test-agent",
        )

    assert not destination.exists()
    assert not destination.with_name("broken.bin.part").exists()
