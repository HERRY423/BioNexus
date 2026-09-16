"""Historical bytes and present-day applicability are separate evidence objects.

The archive retains reports affected by the retired metadata synchronizer.
Its integrity never authenticates their original execution or a new release.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn

ARCHIVE = "validation/history/pre-ga-provenance-01"
REPORTS = tuple(
    f"validation/{cap}/{name}"
    for cap in ("pseudobulk", "annotation", "spatial")
    for name in ("REPORT.json", "INFERENTIAL_STRESS_REPORT.json", "CERTIFICATION.json")
) + ("validation/annotation/FLAGSHIP_REPORT.json", "validation/spatial/FLAGSHIP_REPORT.json")


def read_object(path: Path) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate key: {key}")
            result[key] = value
        return result

    def invalid(value: str) -> NoReturn:
        raise ValueError(f"Non-finite JSON number: {value}")

    if path.is_symlink() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("Unsafe or oversized report")
    result = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique, parse_constant=invalid)
    if not isinstance(result, dict):
        raise ValueError("Expected an object")
    return result


def document_digest(document: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(document, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def assess_history(root: Path) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    records = []
    try:
        manifest = read_object(root / ARCHIVE / "manifest.json")
        if manifest.get("schema") != "bionexus.validation-history.v1" or set(manifest.get("reports", {})) != set(REPORTS):
            raise ValueError("Incomplete historical inventory")
        for rel in REPORTS:
            archived = root / ARCHIVE / rel
            archived.resolve().relative_to(root / ARCHIVE)
            digest = hashlib.sha256(archived.read_bytes()).hexdigest()
            if digest != manifest["reports"][rel]:
                raise ValueError(f"Historical bytes changed: {rel}")
            old = read_object(archived)
            current = read_object(root / rel)
            same = document_digest(old) == document_digest(current)
            records.append({"path": rel, "archived_sha256": digest,
                            "current_sha256": hashlib.sha256((root / rel).read_bytes()).hexdigest(),
                            "relationship": "PRESERVED_LEGACY" if same else "CHANGED_REQUIRES_NEW_EXECUTION_EVIDENCE"})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    return {"schema": "bionexus.validation-history-assessment.v1",
            "archive_integrity": "INVALID" if errors else "VERIFIED", "errors": errors,
            "records": records, "original_execution_authenticity": "NOT_ESTABLISHED",
            "current_execution_verification": "NOT_PERFORMED", "scientific_authorization": "NONE"}


def is_quarantined_history(root: Path, relative: str, document: dict[str, Any]) -> bool:
    """Previously rewritten rollups cannot serve as fresh execution evidence."""
    archived = root / ARCHIVE / relative
    return archived.is_file() and document_digest(read_object(archived)) == document_digest(document)


def has_current_run_receipt(root: Path, relative: str, source_snapshot: str) -> bool:
    """Require matching changed output from a completed local run capsule.

    This is local process traceability, never authentication of its producer.
    Neither an unchanged carried-forward report nor a manually refreshed source
    field constitutes current execution evidence.
    """
    current = root / relative
    if not current.is_file():
        return False
    digest = hashlib.sha256(current.read_bytes()).hexdigest()
    for path in (root / "validation/runs").glob("*/receipt.json"):
        try:
            receipt = read_object(path)
            if (receipt.get("schema") != "bionexus.validation-run.v1"
                    or receipt.get("run_id") != path.parent.name
                    or receipt.get("status") != "COMPLETED_LOCAL_ONLY"
                    or type(receipt.get("return_code")) is not int or receipt["return_code"] != 0
                    or receipt.get("error") is not None
                    or receipt.get("source_unchanged") is not True
                    or receipt.get("source_before") != source_snapshot
                    or receipt.get("source_after") != source_snapshot
                    or relative not in receipt.get("changed", [])
                    or receipt.get("after", {}).get(relative) != digest
                    or receipt.get("before", {}).get(relative) == digest):
                continue
            start = datetime.fromisoformat(receipt["started_at"])
            end = datetime.fromisoformat(receipt["finished_at"])
            if start.utcoffset() is None or end.utcoffset() is None or end < start:
                continue
            output = path.parent / "after" / relative
            output.resolve().relative_to(path.parent.resolve())
            if not output.is_symlink() and hashlib.sha256(output.read_bytes()).hexdigest() == digest:
                return True
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    return False
