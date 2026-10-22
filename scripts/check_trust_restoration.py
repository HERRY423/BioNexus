"""Verify correction/archive byte bindings without granting scientific authority."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RECORD = "review/trust-restoration-2026-09-19/CORRECTIONS-rc9.json"


def check(root: Path, record: str = RECORD) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []

    def digest(relative: str) -> str:
        path = root / relative
        path.resolve().relative_to(root)
        if path.is_symlink():
            raise ValueError(f"Symlink is not a frozen artifact: {relative}")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    try:
        corrections = json.loads((root / record).read_text(encoding="utf-8"))
        prior = corrections.get("supersedes")
        if prior and digest(prior["path"]) != prior["sha256"]:
            errors.append("Prior correction record changed")
        if corrections.get("scientific_authorization") != "NONE":
            errors.append("Correction must not authorize scientific claims")
        if not corrections.get("records"):
            errors.append("Missing correction inventory")
        for item in corrections.get("records", []):
            if digest(item["original_archive"]) != item["original_sha256"]:
                errors.append(f"Original archive changed: {item['path']}")
            if digest(item["path"]) != item["corrected_sha256"]:
                errors.append(f"Corrected artifact changed: {item['path']}")
        manifest = json.loads((root / Path(record).parent / "original-evidence-manifest.json").read_text(encoding="utf-8"))
        for item in manifest["files"]:
            if digest(item["archive_path"]) != item["sha256"]:
                errors.append(f"Archived bytes changed: {item['path']}")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    return {"status": "FAIL" if errors else "PASS", "errors": errors,
            "scope": "Correction and archive byte bindings only",
            "original_claim_validity": "NOT_AUTHENTICATED", "scientific_authorization": "NONE"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--record", default=RECORD, help="Explicit correction snapshot to verify")
    args = parser.parse_args()
    result = check(args.root, args.record)
    print(json.dumps(result, indent=2))
    return int(bool(result["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
