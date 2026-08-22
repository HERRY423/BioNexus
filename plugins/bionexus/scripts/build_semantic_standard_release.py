#!/usr/bin/env python3
"""Verify and build the language-neutral BNS-019 release artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STANDARD_ROOT = REPOSITORY_ROOT / "standards" / "scientific-semantic-conventions"
MANIFEST_NAME = "release-manifest.json"
MANIFEST_SCHEMA = "urn:bionexus:scientific-semantic-release-manifest:1"
ARTIFACT_NAME = "bionexus-scientific-semantic-conventions"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class ReleaseBuildError(RuntimeError):
    """Raised when a semantic standard release is incomplete or inconsistent."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative_path(raw: str) -> PurePosixPath:
    path = PurePosixPath(raw)
    if path.is_absolute() or not path.parts or ".." in path.parts or "." in path.parts:
        raise ReleaseBuildError(f"unsafe manifest path: {raw!r}")
    return path


def _distributed_paths(root: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() and path.name != MANIFEST_NAME and "__pycache__" not in path.parts
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def build_manifest(root: Path) -> dict[str, Any]:
    version_path = root / "VERSION"
    if not version_path.is_file():
        raise ReleaseBuildError("VERSION is missing")
    version = version_path.read_text(encoding="utf-8").strip()
    records = [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": _sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in _distributed_paths(root)
    ]
    release_digest = _sha256_bytes(_canonical_json(records))
    return {
        "schema": MANIFEST_SCHEMA,
        "standard_id": "BNS-019",
        "artifact_name": ARTIFACT_NAME,
        "version": version,
        "status": "development",
        "digest_algorithm": "sha256",
        "files": records,
        "release_digest_sha256": release_digest,
        "attestation_profile": {
            "schema_version": "bionexus.evidence-attestation.v1",
            "predicate_type": "standard-release",
            "subject_type": "scientific-semantic-conventions-release",
            "subject_id": "BNS-019",
            "subject_version": version,
            "required_claims": {"release_digest_sha256": release_digest},
        },
        "claim_boundary": (
            "Software-contract release only; not evidence of biological validity, "
            "empirical calibration, external endorsement, or community adoption."
        ),
    }


def write_manifest(root: Path) -> Path:
    manifest_path = root / MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(build_manifest(root), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest_path


def verify_manifest(root: Path) -> dict[str, Any]:
    manifest_path = root / MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseBuildError(f"cannot read {MANIFEST_NAME}: {exc}") from exc
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ReleaseBuildError("unsupported release manifest schema")
    if manifest.get("standard_id") != "BNS-019" or manifest.get("artifact_name") != ARTIFACT_NAME:
        raise ReleaseBuildError("release identity mismatch")
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if manifest.get("version") != version:
        raise ReleaseBuildError("release manifest version does not match VERSION")

    listed = manifest.get("files")
    if not isinstance(listed, list) or not listed:
        raise ReleaseBuildError("release manifest files must be a non-empty array")
    expected_paths = {path.relative_to(root).as_posix() for path in _distributed_paths(root)}
    actual_paths: set[str] = set()
    for record in listed:
        if not isinstance(record, dict):
            raise ReleaseBuildError("release manifest file record must be an object")
        relative = _safe_relative_path(str(record.get("path", "")))
        relative_text = relative.as_posix()
        if relative_text in actual_paths:
            raise ReleaseBuildError(f"duplicate manifest path: {relative_text}")
        actual_paths.add(relative_text)
        path = root.joinpath(*relative.parts)
        if not path.is_file():
            raise ReleaseBuildError(f"manifest file is missing: {relative_text}")
        if record.get("sha256") != _sha256_file(path):
            raise ReleaseBuildError(f"SHA-256 mismatch: {relative_text}")
        if record.get("size_bytes") != path.stat().st_size:
            raise ReleaseBuildError(f"size mismatch: {relative_text}")
    if actual_paths != expected_paths:
        missing = sorted(expected_paths - actual_paths)
        extra = sorted(actual_paths - expected_paths)
        raise ReleaseBuildError(f"manifest inventory mismatch; unlisted={missing}, absent={extra}")
    expected_release_digest = _sha256_bytes(_canonical_json(listed))
    if manifest.get("release_digest_sha256") != expected_release_digest:
        raise ReleaseBuildError("release_digest_sha256 mismatch")
    return manifest


def build_zip(root: Path, output_dir: Path) -> tuple[Path, Path]:
    manifest = verify_manifest(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"{ARTIFACT_NAME}-{manifest['version']}.zip"
    archive_root = f"{ARTIFACT_NAME}-{manifest['version']}"
    files = _distributed_paths(root) + [root / MANIFEST_NAME]
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
            relative = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(f"{archive_root}/{relative}", ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            bundle.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    digest_path = archive.with_suffix(archive.suffix + ".sha256")
    digest_path.write_text(f"{_sha256_file(archive)}  {archive.name}\n", encoding="ascii", newline="\n")
    return archive, digest_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--standard-root", type=Path, default=DEFAULT_STANDARD_ROOT)
    parser.add_argument("--output-dir", type=Path, default=REPOSITORY_ROOT / "dist" / "standards")
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    root = args.standard_root.resolve()
    try:
        if args.write_manifest:
            write_manifest(root)
        manifest = verify_manifest(root)
        if args.verify_only:
            print(f"VERIFIED {manifest['standard_id']} {manifest['version']} {manifest['release_digest_sha256']}")
            return 0
        archive, digest = build_zip(root, args.output_dir.resolve())
        print(archive)
        print(digest)
        return 0
    except ReleaseBuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
