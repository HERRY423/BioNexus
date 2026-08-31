"""Regression tests for pinned public flagship data acquisition."""

from __future__ import annotations

import hashlib
import io
import urllib.request

from evals.datasets import download_flagship_datasets as downloader


def test_download_uses_identified_request_and_verifies_bytes(tmp_path, monkeypatch):
    payload = b"pinned-public-benchmark"
    expected = hashlib.sha256(payload).hexdigest()
    observed = {}

    def _open(request, **kwargs):
        observed["request"] = request
        observed["kwargs"] = kwargs
        return io.BytesIO(payload)

    monkeypatch.setattr(downloader, "guarded_urlopen", _open)
    destination = tmp_path / "fixture.bin"
    downloader._download_verified("https://example.org/fixture.bin", destination, expected)

    request = observed["request"]
    assert isinstance(request, urllib.request.Request)
    assert request.get_header("User-agent") == "BioNexus/1.0 flagship-validation"
    assert observed["kwargs"]["data_classification"].value == "PUBLIC_BENCHMARK"
    assert destination.read_bytes() == payload
