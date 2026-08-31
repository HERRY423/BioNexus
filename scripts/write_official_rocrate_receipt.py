"""Write a fail-closed receipt after the official validator CLI succeeds."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

EXPECTED_VALIDATOR_VERSION = "0.11.2"
TARGET_PROFILE = "provenance-run-crate-0.5"
INHERITED_PROFILES = [
    "ro-crate-1.1",
    "process-run-crate-0.5",
    "workflow-ro-crate-1.0",
    "workflow-run-crate-0.5",
    TARGET_PROFILE,
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_receipt(crate_dir: Path, validation_log: Path, output: Path) -> None:
    version = importlib.metadata.version("roc-validator")
    if version != EXPECTED_VALIDATOR_VERSION:
        raise RuntimeError(
            f"Expected roc-validator {EXPECTED_VALIDATOR_VERSION}, found {version}"
        )
    log_text = validation_log.read_text(encoding="utf-8")
    success_marker = f"RO-Crate is a valid {TARGET_PROFILE}"
    if success_marker not in log_text:
        raise RuntimeError("Official validator success marker is absent from the captured log")
    metadata_path = crate_dir / "ro-crate-metadata.json"
    if not metadata_path.is_file():
        raise FileNotFoundError(metadata_path)

    receipt = {
        "schema_version": "bionexus.official-rocrate-validation-receipt.v1",
        "status": "THIRD_PARTY_TOOL_VALIDATED",
        "validator": {
            "package": "roc-validator",
            "cli": "rocrate-validator",
            "version": version,
        },
        "target_profile": TARGET_PROFILE,
        "inherited_profiles": INHERITED_PROFILES,
        "requirement_severity": "REQUIRED",
        "crate_metadata_sha256": _sha256(metadata_path),
        "validation_log_sha256": _sha256(validation_log),
        "external_adoption_status": "NOT_ESTABLISHED",
        "scope_note": (
            "Third-party tool validation establishes technical conformance for this fixture; "
            "it is not certification, endorsement, or external adoption."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crate-dir", type=Path, required=True)
    parser.add_argument("--validation-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_receipt(args.crate_dir, args.validation_log, args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
