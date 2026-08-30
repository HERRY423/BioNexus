"""
Verified data ingress for BioNexus.

Closes the data-egress gap of researcher workflows: research data rarely lives on the
machine where the agent/plugin runs. This module brings external data *into* a verified,
hash-audited local workspace (optionally directly into a Run Capsule input manifest) or
deterministically refuses.

Supported sources:
- Local paths and ``file://`` URIs (copy + re-hash)
- ``http(s)://`` URLs (stdlib streaming download; no extra dependency)
- ``s3://`` and ``gs://`` URIs only when the corresponding optional SDK (boto3 /
  google-cloud-storage) is importable; otherwise a structured, actionable refusal.
  BioNexus never silently pretends a cloud URI was fetched.

Honesty invariants:
- Every ingested artifact is SHA-256 hashed while streaming; an optional
  ``expected_sha256`` is enforced fail-closed (mismatch => refusal, no artifact kept).
- Empty downloads (0 bytes) are refused: an empty file is not a dataset.
- The returned payload is a standard BioNexus contract payload; failures always carry
  ``refused=True`` and an actionable reason.
"""

from __future__ import annotations

import hashlib
import shutil
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Union
from urllib.parse import urlparse

from bionexus.contracts import GRADE_A, attach_meta, refuse

PathLike = Union[str, Path]

DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MAX_BYTES = 512 * 1024**3  # 512 GiB guardrail against runaway downloads
_CHUNK = 1024 * 1024

LOCAL_PROTOCOLS = ("file", "local")
CLOUD_PROTOCOLS = {
    "s3": "boto3",
    "gs": "google-cloud-storage (google.cloud.storage)",
}


@dataclass
class IngressResult:
    """Verified outcome of a single ingress operation."""

    source: str
    destination: str
    protocol: str
    sha256: str
    size_bytes: int
    verified: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "destination": self.destination,
            "protocol": self.protocol,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "verified": self.verified,
            "metadata": self.metadata,
        }


def _sha256_stream(handle) -> tuple[str, int]:
    """Hash a readable binary stream while counting bytes."""
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = handle.read(_CHUNK)
        if not chunk:
            break
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _dest_path(dest_dir: Path, source: str, filename: Optional[str]) -> Path:
    if filename:
        return dest_dir / filename
    parsed = urlparse(source)
    if parsed.scheme in ("http", "https", "file"):
        name = Path(urllib.parse.unquote(parsed.path)).name
        if name:
            return dest_dir / name
        return dest_dir / "ingested_dataset"
    return dest_dir / Path(source).name


def _check_optional_sdk(scheme: str, source: str) -> Optional[Dict[str, Any]]:
    """Return a refusal payload when a cloud scheme lacks its optional SDK."""
    sdk = {"s3": "boto3", "gs": "google-cloud-storage"}.get(scheme)
    if sdk is None:
        return None
    module = "boto3" if sdk == "boto3" else "google.cloud.storage"
    try:
        __import__(module)
        return None
    except ImportError:
        return refuse(
            method="bionexus.ingress.ingest",
            reason=(
                f"Scheme '{scheme}://' requires the optional '{sdk}' SDK, which is not installed. "
                f"BioNexus refuses to pretend the dataset was fetched. Install '{sdk}' or stage the "
                f"file locally (or over HTTPS) and re-run ingest."
            ),
            extra={"source": source, "scheme": scheme, "required_sdk": sdk},
        )


def _looks_like_windows_drive_path(source: str) -> bool:
    """True for 'C:\\...' / 'C:/...' paths that urlparse would misread as scheme 'c'."""
    return len(source) >= 2 and source[0].isalpha() and source[1] == ":"


def ingest(
    source: str,
    dest_dir: PathLike,
    *,
    filename: Optional[str] = None,
    expected_sha256: Optional[str] = None,
    expected_size_bytes: Optional[int] = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """
    Fetch one dataset from a local path, file://, http(s)://, s3:// or gs:// source into
    ``dest_dir`` with streaming SHA-256 verification.

    Returns an ``attach_meta`` payload whose ``ingress`` key holds an ``IngressResult``.
    Success payloads always carry ``refused: False``. Deterministic refusals
    (``refused=True``) are returned for unsupported schemes, missing optional cloud SDKs,
    network errors, empty payloads, size-limit violations, and checksum mismatches.
    """
    dest_root = Path(dest_dir)
    parsed = None
    if _looks_like_windows_drive_path(source):
        scheme = "local"
    else:
        parsed = urlparse(source)
        scheme = (parsed.scheme or "local").lower()

    if scheme in ("http", "https"):
        return _ingest_http(
            source,
            dest_root,
            filename=filename,
            expected_sha256=expected_sha256,
            expected_size_bytes=expected_size_bytes,
            max_bytes=max_bytes,
            timeout_seconds=timeout_seconds,
            overwrite=overwrite,
        )

    if scheme in ("s3", "gs"):
        refusal = _check_optional_sdk(scheme, source)
        if refusal is not None:
            return refusal
        return refuse(
            method="bionexus.ingress.ingest",
            reason=(
                f"Cloud SDK for '{scheme}://' is installed but direct cloud ingress is not enabled in this "
                "BioNexus version. Stage the object to a local path or presigned HTTPS URL first; "
                "ingest will then verify it."
            ),
            extra={"source": source, "scheme": scheme},
        )

    if scheme not in LOCAL_PROTOCOLS and scheme not in ("", "local"):
        return refuse(
            method="bionexus.ingress.ingest",
            reason=(
                f"Unsupported ingress scheme '{scheme}'. Supported: local path, file://, "
                "http(s)://, s3:// (with boto3 staged), gs:// (with google-cloud-storage staged)."
            ),
            extra={"source": source, "scheme": scheme},
        )

    src_path = Path(parsed.path if (scheme == "file" and parsed is not None) else source)
    if not src_path.is_file():
        return refuse(
            method="bionexus.ingress.ingest",
            reason=f"Source dataset not found or is not a regular file: {src_path}",
            extra={"source": source},
        )

    return _finalize_local_copy(
        src_path,
        source,
        dest_root,
        protocol="file" if scheme == "file" else "local",
        filename=filename,
        expected_sha256=expected_sha256,
        expected_size_bytes=expected_size_bytes,
        max_bytes=max_bytes,
        overwrite=overwrite,
    )


def _finalize_local_copy(
    src_path: Path,
    source: str,
    dest_root: Path,
    *,
    protocol: str,
    filename: Optional[str],
    expected_sha256: Optional[str],
    expected_size_bytes: Optional[int],
    max_bytes: int,
    overwrite: bool,
) -> Dict[str, Any]:
    """Copy a local file into dest_dir with streaming hash verification."""
    size_bytes = src_path.stat().st_size
    if size_bytes == 0:
        return refuse(
            method="bionexus.ingress.ingest",
            reason=f"Refusing to ingest an empty file (0 bytes): {src_path}",
            extra={"source": source},
        )
    if size_bytes > max_bytes:
        return refuse(
            method="bionexus.ingress.ingest",
            reason=f"Source size {size_bytes} bytes exceeds the ingress guardrail of {max_bytes} bytes.",
            extra={"source": source, "size_bytes": size_bytes},
        )
    if expected_size_bytes is not None and size_bytes != expected_size_bytes:
        return refuse(
            method="bionexus.ingress.ingest",
            reason=(
                f"Size verification failed: expected {expected_size_bytes} bytes, got {size_bytes} bytes."
            ),
            extra={"source": source, "size_bytes": size_bytes},
        )

    dest_root.mkdir(parents=True, exist_ok=True)
    dest = _dest_path(dest_root, source, filename)
    if dest.exists() and not overwrite:
        return refuse(
            method="bionexus.ingress.ingest",
            reason=f"Destination already exists (set overwrite=True to replace): {dest}",
            extra={"source": source, "destination": str(dest)},
        )

    sha256 = _stream_copy_with_hash(src_path, dest)

    if expected_sha256 and sha256.lower() != expected_sha256.lower():
        dest.unlink(missing_ok=True)
        return refuse(
            method="bionexus.ingress.ingest",
            reason=(
                f"SHA-256 verification failed for {source}: expected {expected_sha256}, got {sha256}. "
                "The partially staged artifact was deleted (fail-closed)."
            ),
            extra={"source": source, "expected_sha256": expected_sha256, "actual_sha256": sha256},
        )

    result = IngressResult(
        source=source,
        destination=str(dest),
        protocol=protocol,
        sha256=sha256,
        size_bytes=size_bytes,
        verified=True,
        metadata={"verified_against_expected": bool(expected_sha256)},
    )
    return attach_meta(
        {"refused": False, "ingress": result.to_dict()},
        method="bionexus.ingress.ingest",
        backend="stdlib (shutil/hashlib/urllib)",
        evidence_grade=GRADE_A,
        limitations=[
            "Ingress verifies transport integrity (checksum), not biological data semantics.",
            "Run 'bionexus audit' on expression matrices before analysis.",
        ],
    )


def _stream_copy_with_hash(src_path: Path, dest: Path) -> str:
    """Copy src to dest while hashing; fall back to a temp file on cross-device links."""
    digest = hashlib.sha256()
    tmp_dest = dest.with_suffix(dest.suffix + ".part")
    with src_path.open("rb") as src, tmp_dest.open("wb") as out:
        while True:
            chunk = src.read(_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
            out.write(chunk)
    shutil.move(str(tmp_dest), str(dest))
    return digest.hexdigest()


def _ingest_http(
    source: str,
    dest_root: Path,
    *,
    filename: Optional[str],
    expected_sha256: Optional[str],
    expected_size_bytes: Optional[int],
    max_bytes: int,
    timeout_seconds: int,
    overwrite: bool,
) -> Dict[str, Any]:
    """Stream an http(s) download to disk while hashing, enforcing the size guardrail."""
    request = urllib.request.Request(source, headers={"User-Agent": "BioNexus-Ingress/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            content_length = response.headers.get("Content-Length")
            declared_size = int(content_length) if content_length and content_length.isdigit() else None
            if declared_size is not None and declared_size > max_bytes:
                return refuse(
                    method="bionexus.ingress.ingest",
                    reason=(
                        f"Content-Length {declared_size} bytes exceeds the ingress guardrail of "
                        f"{max_bytes} bytes. Download aborted before transfer."
                    ),
                    extra={"source": source, "size_bytes": declared_size},
                )

            dest_root.mkdir(parents=True, exist_ok=True)
            dest = _dest_path(dest_root, source, filename)
            if dest.exists() and not overwrite:
                return refuse(
                    method="bionexus.ingress.ingest",
                    reason=f"Destination already exists (set overwrite=True to replace): {dest}",
                    extra={"source": source, "destination": str(dest)},
                )

            tmp_dest = dest.with_suffix(dest.suffix + ".part")
            digest = hashlib.sha256()
            size = 0
            with tmp_dest.open("wb") as out:
                while True:
                    chunk = response.read(_CHUNK)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        out.close()
                        tmp_dest.unlink(missing_ok=True)
                        return refuse(
                            method="bionexus.ingress.ingest",
                            reason=(
                                f"Download exceeded the ingress guardrail of {max_bytes} bytes mid-stream. "
                                "Partial artifact deleted (fail-closed)."
                            ),
                            extra={"source": source, "max_bytes": max_bytes},
                        )
                    digest.update(chunk)
                    out.write(chunk)
    except urllib.error.HTTPError as e:
        return refuse(
            method="bionexus.ingress.ingest",
            reason=f"HTTP {e.code} while fetching {source}: {e.reason}",
            extra={"source": source, "http_status": e.code},
        )
    except urllib.error.URLError as e:
        return refuse(
            method="bionexus.ingress.ingest",
            reason=f"Network error while fetching {source}: {e.reason}",
            extra={"source": source},
        )
    except TimeoutError:
        return refuse(
            method="bionexus.ingress.ingest",
            reason=f"Download timed out after {timeout_seconds}s: {source}",
            extra={"source": source},
        )

    try:
        if size == 0:
            tmp_dest.unlink(missing_ok=True)
            return refuse(
                method="bionexus.ingress.ingest",
                reason=f"Refusing to ingest an empty payload (0 bytes) from {source}.",
                extra={"source": source},
            )
        if expected_size_bytes is not None and size != expected_size_bytes:
            tmp_dest.unlink(missing_ok=True)
            return refuse(
                method="bionexus.ingress.ingest",
                reason=f"Size verification failed: expected {expected_size_bytes} bytes, got {size} bytes.",
                extra={"source": source, "size_bytes": size},
            )
        if expected_sha256 and digest.hexdigest().lower() != expected_sha256.lower():
            tmp_dest.unlink(missing_ok=True)
            return refuse(
                method="bionexus.ingress.ingest",
                reason=(
                    f"SHA-256 verification failed for {source}: expected {expected_sha256}, "
                    f"got {digest.hexdigest()}. Partial artifact deleted (fail-closed)."
                ),
                extra={"source": source, "expected_sha256": expected_sha256, "actual_sha256": digest.hexdigest()},
            )
        shutil.move(str(tmp_dest), str(dest))
    finally:
        # Cleanup any leftover .part file on refusal paths that did not move it.
        if not dest.exists() and tmp_dest.exists():  # pragma: no branch - defensive
            tmp_dest.unlink(missing_ok=True)

    result = IngressResult(
        source=source,
        destination=str(dest),
        protocol="https" if source.lower().startswith("https") else "http",
        sha256=digest.hexdigest(),
        size_bytes=size,
        verified=True,
        metadata={"verified_against_expected": bool(expected_sha256)},
    )
    return attach_meta(
        {"refused": False, "ingress": result.to_dict()},
        method="bionexus.ingress.ingest",
        backend="stdlib (urllib)",
        evidence_grade=GRADE_A,
        limitations=[
            "Ingress verifies transport integrity (checksum), not biological data semantics.",
            "Cloud object stores (s3://, gs://) require staging or their optional SDKs.",
        ],
    )


def ingest_into_capsule(
    source: str,
    bundle,  # bionexus.artifacts.RunBundle (typed loosely to avoid a circular import)
    *,
    name: str,
    semantic_type: str = "unspecified",
    expected_sha256: Optional[str] = None,
    overwrite: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """
    Ingest a dataset directly into a Run Capsule's inputs manifest.

    The artifact is stored under ``<capsule>/inputs/`` and registered via
    ``RunBundle.record_input`` so downstream agents receive the hash-audited path.
    """
    dest_dir = Path(bundle.run_dir) / "inputs"
    payload = ingest(
        source,
        dest_dir,
        expected_sha256=expected_sha256,
        overwrite=overwrite,
        timeout_seconds=timeout_seconds,
    )
    if payload.get("refused"):
        return payload

    ingress = payload["ingress"]
    bundle.record_input(
        name,
        ingress["destination"],
        semantic_type=semantic_type,
        metadata={
            "ingress_source": ingress["source"],
            "ingress_protocol": ingress["protocol"],
            "ingress_verified": ingress["verified"],
        },
    )
    return payload
