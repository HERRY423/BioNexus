"""Passive, standard-library reader for DE shadow bundles.

File consistency is not analysis verification, scientific approval, or producer
authentication. This file can also be executed directly with ``python -S``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

BUNDLE_SCHEMA = "bionexus.de-shadow-bundle.v1"
INTEGRITY_PROFILE = "bionexus.de-shadow-integrity.v1"
VERIFICATION_SCHEMA = "bionexus.de-bundle-verification.v1"
IMMUTABLE_ARTIFACTS = ("audit.json", "audit-full.md", "REVIEW.md")
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
AUDIT_STATUSES = {"ROBUST_PASS", "NEEDS_DATA", "NOT_ASSESSED", "NEEDS_REVISION", "BLOCKER_DETECTED"}
EXIT_CODES = {"CONSISTENT": 0, "INVALID": 1, "UNSUPPORTED_SCHEMA": 2, "LEGACY_LIMITED": 3}


class BundleError(ValueError):
    def __init__(self, code: str, artifact: str, message: str) -> None:
        super().__init__(message)
        self.code, self.artifact = code, artifact


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise ValueError(f"Non-finite JSON value: {value}")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON number")
    return number


def _read(directory: Path, name: str) -> bytes:
    # Callers use fixed names only; never follow paths supplied by a manifest.
    path = directory / name
    if path.is_symlink() or path.resolve().parent != directory:
        raise BundleError("UNSAFE_ARTIFACT", name, "Artifact must be a regular file directly inside the bundle")
    try:
        if not path.is_file():
            raise BundleError("MISSING_ARTIFACT", name, "Required artifact is missing or is not a file")
        with path.open("rb") as stream:
            data = stream.read(MAX_ARTIFACT_BYTES + 1)
        if len(data) > MAX_ARTIFACT_BYTES:
            raise BundleError("ARTIFACT_TOO_LARGE", name, "Artifact exceeds the 8 MiB reader limit")
        return data
    except OSError as exc:
        raise BundleError("UNREADABLE_ARTIFACT", name, "Artifact could not be read") from exc


def _parse(data: bytes, name: str) -> dict[str, Any]:
    try:
        result = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_object,
                            parse_constant=_nonfinite, parse_float=_finite_float)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise BundleError("INVALID_JSON", name, "Expected finite UTF-8 JSON with unique object keys") from exc
    if not isinstance(result, dict):
        raise BundleError("INVALID_JSON", name, "Expected a JSON object")
    return result


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def verify_de_bundle(directory: str | Path, *, expected_manifest_sha256: str | None = None) -> dict[str, Any]:
    """Read fixed bundle artifacts without execution, networking, or mutations.

Unknown schemas refuse interpretation. Historic v1 bundles remain readable with
LEGACY_LIMITED status; missing report hashes never become full verification.
An optional out-of-band manifest digest detects rewriting of local hashes. Its
source/trustworthiness remains the caller's responsibility.
"""
    report: dict[str, Any] = {
        "schema": VERIFICATION_SCHEMA, "status": "INVALID", "bundle_schema": None,
        "integrity_profile": None, "manifest_sha256": None, "manifest_anchor": "NOT_PROVIDED",
        "checked_artifacts": [], "audit_status": None, "issues": [],
        "scientific_authorization": "NONE", "analysis_execution_verification": "NOT_PERFORMED",
        "input_content_verification": "NOT_PERFORMED", "producer_authentication": "NOT_ESTABLISHED",
        "mutable_reviews": "NOT_VERIFIED",
    }
    try:
        root = Path(directory).resolve()
        manifest_bytes = _read(root, "manifest.json")
        manifest_hash = _digest(manifest_bytes)
        report["manifest_sha256"] = manifest_hash
        if expected_manifest_sha256 is not None:
            if not _is_digest(expected_manifest_sha256):
                raise BundleError("INVALID_ANCHOR", "manifest.json", "Expected a lowercase SHA-256 digest")
            if manifest_hash != expected_manifest_sha256:
                report["manifest_anchor"] = "MISMATCH"
                raise BundleError("MANIFEST_HASH_MISMATCH", "manifest.json", "Manifest differs from caller-supplied digest")
            report["manifest_anchor"] = "MATCHED"
        manifest = _parse(manifest_bytes, "manifest.json")
        report["bundle_schema"] = manifest.get("schema") if isinstance(manifest.get("schema"), str) else None
        report["integrity_profile"] = manifest.get("integrity_profile") if isinstance(manifest.get("integrity_profile"), str) else None
        if manifest.get("schema") != BUNDLE_SCHEMA:
            raise BundleError("UNSUPPORTED_SCHEMA", "manifest.json", "Bundle schema is not supported by this reader")
        if manifest.get("scientific_authorization") != "NONE":
            raise BundleError("AUTHORITY_ESCALATION", "manifest.json", "Shadow bundles cannot grant scientific authorization")
        origin = manifest.get("data_origin")
        if not isinstance(origin, str) or origin not in {"SYNTHETIC_DEMO", "USER_SUPPLIED_UNVERIFIED"}:
            raise BundleError("UNKNOWN_DATA_ORIGIN", "manifest.json", "Data origin is absent or unrecognized")
        if not _is_digest(manifest.get("audit_sha256")):
            raise BundleError("INVALID_DIGEST", "manifest.json", "audit_sha256 is required")
        audit_bytes = _read(root, "audit.json")
        if _digest(audit_bytes) != manifest["audit_sha256"]:
            raise BundleError("ARTIFACT_HASH_MISMATCH", "audit.json", "Audit bytes differ from the manifest")
        audit = _parse(audit_bytes, "audit.json")
        status = audit.get("overall_status")
        if not isinstance(status, str) or status not in AUDIT_STATUSES:
            raise BundleError("UNSUPPORTED_SCHEMA", "audit.json", "Audit status is unknown; do not infer success")
        if type(audit.get("passed")) is not bool or audit["passed"] != (status == "ROBUST_PASS"):
            raise BundleError("INCONSISTENT_STATUS", "audit.json", "passed must agree with the declared audit status")
        if not isinstance(audit.get("findings"), list) or not isinstance(audit.get("checks"), list):
            raise BundleError("INVALID_AUDIT_SHAPE", "audit.json", "Audit findings and checks must be arrays")
        report["audit_status"] = status
        report["checked_artifacts"].append("audit.json")
        profile_present = "integrity_profile" in manifest
        hashes_present = "immutable_artifacts" in manifest
        if not profile_present and not hashes_present:
            report["status"] = "LEGACY_LIMITED"
            report["issues"].append({"code": "LEGACY_REPORTS_UNBOUND", "artifact": "manifest.json",
                                     "message": "Historical bundle binds audit.json only; human reports are not verified"})
            return report
        if not profile_present or not hashes_present:
            raise BundleError("INCOMPLETE_INTEGRITY_PROFILE", "manifest.json", "Profile and immutable hashes must occur together")
        if manifest["integrity_profile"] != INTEGRITY_PROFILE:
            raise BundleError("UNSUPPORTED_SCHEMA", "manifest.json", "Integrity profile is not supported")
        hashes = manifest["immutable_artifacts"]
        if not isinstance(hashes, dict) or set(hashes) != set(IMMUTABLE_ARTIFACTS):
            raise BundleError("INVALID_ARTIFACT_SET", "manifest.json", "Integrity v1 binds exactly audit.json, audit-full.md and REVIEW.md")
        for name in IMMUTABLE_ARTIFACTS:
            if not _is_digest(hashes[name]):
                raise BundleError("INVALID_DIGEST", name, "Artifact digest is malformed")
            data = audit_bytes if name == "audit.json" else _read(root, name)
            if _digest(data) != hashes[name]:
                raise BundleError("ARTIFACT_HASH_MISMATCH", name, "Artifact bytes differ from the manifest")
            if name != "audit.json":
                report["checked_artifacts"].append(name)
        report["status"] = "CONSISTENT"
    except BundleError as exc:
        report["status"] = "UNSUPPORTED_SCHEMA" if exc.code == "UNSUPPORTED_SCHEMA" else "INVALID"
        report["issues"].append({"code": exc.code, "artifact": exc.artifact, "message": str(exc)})
    except (OSError, ValueError, RuntimeError) as exc:
        report["issues"].append({"code": "UNREADABLE_BUNDLE", "artifact": "bundle", "message": type(exc).__name__})
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify DE bundle file consistency only; no scientific approval")
    parser.add_argument("bundle")
    parser.add_argument("--expected-manifest-sha256", default=None)
    args = parser.parse_args(argv)
    report = verify_de_bundle(args.bundle, expected_manifest_sha256=args.expected_manifest_sha256)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return EXIT_CODES[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
