"""Append-only local run capsules around legacy validation writers.

Top-level reports are compatibility views. Before/after bytes live separately;
an unchanged report is never attributed to the new execution.
"""
from __future__ import annotations

import functools
import hashlib
import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from bionexus.validation_verifier import compute_validation_source_snapshot


@contextmanager
def exclusive_writer(root: Path) -> Iterator[None]:
    """Refuse overlapping writers instead of attributing another run's output."""
    lock = root / "validation/runs/.writer.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise RuntimeError("Validation writer lock exists; inspect the active or interrupted run before retrying") from exc
    try:
        with handle:
            handle.write(datetime.now(timezone.utc).isoformat())
        yield
    finally:
        lock.unlink()


def capture_files(root: Path, destination: Path) -> dict[str, str]:
    inventory = {}
    for path in sorted((root / "validation").rglob("*")):
        relative = path.relative_to(root)
        if any(part in ("history", "runs", "__pycache__") for part in relative.parts) or not path.is_file():
            continue
        if path.is_symlink():
            raise ValueError(f"Symlink in validation evidence: {relative}")
        raw = path.read_bytes()
        copied = destination / relative
        copied.parent.mkdir(parents=True, exist_ok=True)
        with copied.open("xb") as handle:
            handle.write(raw)
        inventory[relative.as_posix()] = hashlib.sha256(raw).hexdigest()
    return inventory


def record_validation_run(root: Path) -> Callable[[Callable[..., int]], Callable[..., int]]:
    """Preserve failed, partial and successful runs, without upgrading old data."""
    def decorate(function: Callable[..., int]) -> Callable[..., int]:
        def execute(*args: Any, **kwargs: Any) -> int:
            run = root / "validation" / "runs" / uuid.uuid4().hex
            run.mkdir(parents=True, exist_ok=False)
            before_source = compute_validation_source_snapshot(root)
            before = capture_files(root, run / "before")
            started = datetime.now(timezone.utc).isoformat()
            result = None
            error = None
            try:
                result = function(*args, **kwargs)
                return result
            except BaseException as exc:
                error = type(exc).__name__
                raise
            finally:
                after = capture_files(root, run / "after")
                after_source = compute_validation_source_snapshot(root)
                receipt = {
                    "schema": "bionexus.validation-run.v1", "run_id": run.name,
                    "status": ("FAILED_SOURCE_CHANGED" if before_source != after_source else
                               "COMPLETED_LOCAL_ONLY" if result == 0 and error is None else "FAILED"),
                    "runner": function.__module__, "started_at": started,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "return_code": result, "error": error,
                    "source_before": before_source, "source_after": after_source,
                    "source_unchanged": before_source == after_source,
                    "before": before, "after": after,
                    "changed": sorted(path for path, digest in after.items() if before.get(path) != digest),
                    "deleted": sorted(set(before) - set(after)),
                    "execution_authority": "LOCAL_PROCESS_ONLY", "scientific_authorization": "NONE",
                }
                with (run / "receipt.json").open("x", encoding="utf-8") as handle:
                    json.dump(receipt, handle, indent=2)
                if before_source != after_source:
                    raise RuntimeError("Validation source changed during execution; candidate rejected")

        @functools.wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> int:
            with exclusive_writer(root):
                return execute(*args, **kwargs)
        return wrapped
    return decorate
