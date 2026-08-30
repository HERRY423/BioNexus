"""Unit tests for verified data ingress (bionexus.ingress)."""

from __future__ import annotations

import hashlib
import http.server
import socketserver
import sys
import threading
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bionexus.artifacts import RunBundle
from bionexus.ingress import ingest, ingest_into_capsule


@pytest.fixture()
def dataset(tmp_path: Path) -> Path:
    data = b"GCTAAGTTCGGACCATTG" * 512
    p = tmp_path / "reads.fa"
    p.write_bytes(data)
    return p


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_local_ingest_with_checksum_verification(tmp_path: Path, dataset: Path):
    payload = ingest(str(dataset), tmp_path / "staging", expected_sha256=_sha(dataset))
    assert payload["refused"] is False
    ing = payload["ingress"]
    assert ing["verified"] is True
    assert ing["size_bytes"] == dataset.stat().st_size
    staged = Path(ing["destination"])
    assert staged.is_file()
    assert staged.read_bytes() == dataset.read_bytes()
    assert payload["evidence_grade"] == "A"


def test_ingest_refuses_checksum_mismatch_fail_closed(tmp_path: Path, dataset: Path):
    dest = tmp_path / "staging"
    payload = ingest(str(dataset), dest, expected_sha256="0" * 64)
    assert payload["refused"] is True
    assert "SHA-256 verification failed" in payload["abstain_reason"]
    # No partial artifact may survive a failed verification.
    assert not any(dest.glob("reads*"))


def test_ingest_rejects_empty_file(tmp_path: Path):
    empty = tmp_path / "empty.csv"
    empty.write_bytes(b"")
    payload = ingest(str(empty), tmp_path / "staging")
    assert payload["refused"] is True
    assert "empty" in payload["abstain_reason"].lower()


def test_ingest_rejects_unknown_scheme(tmp_path: Path):
    payload = ingest("ftp://example.org/reads.fa", tmp_path / "staging")
    assert payload["refused"] is True
    assert "Unsupported ingress scheme" in payload["abstain_reason"]


def test_ingest_rejects_missing_source(tmp_path: Path):
    payload = ingest(str(tmp_path / "missing.fa"), tmp_path / "staging")
    assert payload["refused"] is True


def test_cloud_uri_refuses_without_enabled_ingress(tmp_path: Path):
    # Deterministic in both environments: without the optional SDK the refusal names it;
    # with the SDK installed cloud ingress is still explicitly not enabled.
    for uri in ("s3://bucket/reads.fa", "gs://bucket/reads.fa"):
        payload = ingest(uri, tmp_path / "staging")
        assert payload["refused"] is True, uri


def test_http_ingest_roundtrip(tmp_path: Path, dataset: Path):
    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(dataset.parent), **kwargs)

        def log_message(self, *args):  # silence test output
            pass

    with socketserver.TCPServer(("127.0.0.1", 0), _Handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{port}/{dataset.name}"
            payload = ingest(url, tmp_path / "staging", expected_sha256=_sha(dataset))
        finally:
            httpd.shutdown()
    assert payload["refused"] is False, payload
    ing = payload["ingress"]
    assert ing["protocol"] == "http"
    assert Path(ing["destination"]).read_bytes() == dataset.read_bytes()
    assert ing["sha256"] == _sha(dataset)


def test_http_ingest_404_refuses(tmp_path: Path):
    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_error(404)

        def log_message(self, *args):
            pass

    with socketserver.TCPServer(("127.0.0.1", 0), _Handler) as httpd:
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            payload = ingest(f"http://127.0.0.1:{port}/nope.fa", tmp_path / "staging")
        finally:
            httpd.shutdown()
    assert payload["refused"] is True
    assert "HTTP 404" in payload["abstain_reason"]


def test_ingest_into_capsule_records_verified_input(tmp_path: Path, dataset: Path):
    bundle = RunBundle.create(tmp_path / "capsule", capability_id="ingress.test", skill_name="test")
    payload = ingest_into_capsule(
        str(dataset), bundle, name="reads", semantic_type="fasta", expected_sha256=_sha(dataset)
    )
    assert payload["refused"] is False
    bundle.finalize()
    inputs = (tmp_path / "capsule" / "inputs.json").read_text(encoding="utf-8")
    assert '"reads"' in inputs
    assert "ingress_source" in inputs
