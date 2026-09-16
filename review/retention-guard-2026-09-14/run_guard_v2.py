"""Corrected package-complete snapshot wrapper for retention guard attempt 02."""
from __future__ import annotations

import hashlib
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone

import run_guard as base


ROOT = Path(__file__).resolve().parent
ATTEMPT = ROOT / "attempt-02"
base.HERE = ATTEMPT
base.SNAPSHOT = ATTEMPT / "candidate-source"
base.OUT = ATTEMPT / "run-01"


def snapshot_candidate() -> dict:
    if base.SNAPSHOT.exists():
        raise FileExistsError(f"Refusing to overwrite {base.SNAPSHOT}")
    source = base.REPO / "src" / "bionexus"
    hashes = {}
    for path in sorted(item for item in source.rglob("*") if item.is_file()):
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        rel = path.relative_to(base.REPO / "src")
        dest = base.SNAPSHOT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        hashes[rel.as_posix()] = base.digest_path(dest)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=base.REPO, text=True).strip()
    diff = subprocess.check_output(
        ["git", "diff", "--binary", "--", "src/bionexus/de_audit.py", "src/bionexus/claim_semantics.py",
         "tests/unit/test_rc6_p0_boundaries.py", "docs/rc6-p0-closure.md"],
        cwd=base.REPO,
    )
    (ATTEMPT / "candidate.patch").write_bytes(diff)
    return {
        "study_id": "BN-DE-RETENTION-GUARD-20260914-ATTEMPT-02",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "workspace_head": head,
        "registration": "POST_OUTCOME_ENGINEERING_REGRESSION_NOT_INDEPENDENT_STUDY",
        "source_file_count": len(hashes),
        "source_tree_sha256": base.digest_bytes(
            "\n".join(f"{name} {hashes[name]}" for name in sorted(hashes)).encode("utf-8")
        ),
        "candidate_patch_sha256": hashlib.sha256(diff).hexdigest(),
        "source_hashes": hashes,
        "protocol_sha256": base.digest_path(ATTEMPT / "PROTOCOL.md"),
        "runner_sha256": base.digest_path(Path(__file__)),
        "python": sys.version,
        "platform": platform.platform(),
        "attempt_01_status": "SETUP_FAILURE_BEFORE_CASE_EXECUTION",
        "scientific_authorization": "NONE",
    }


base.snapshot_candidate = snapshot_candidate


if __name__ == "__main__":
    base.main()
