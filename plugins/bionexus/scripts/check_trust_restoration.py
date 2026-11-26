"""Verify correction/archive byte bindings without granting scientific authority."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RECORD = "review/trust-restoration-2026-09-19/CORRECTIONS-scientific-audit-power.json"


def check(root: Path, record: str = RECORD, *, verify_git_origin: bool = False) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    verified_commits: list[str] = []

    def artifact_bytes(relative: str) -> bytes:
        path = root / relative
        path.resolve().relative_to(root)
        if path.is_symlink():
            raise ValueError(f"Symlink is not a frozen artifact: {relative}")
        return path.read_bytes()

    def digest(relative: str) -> str:
        return hashlib.sha256(artifact_bytes(relative)).hexdigest()

    try:
        corrections = json.loads(artifact_bytes(record))
        prior = corrections.get("supersedes")
        seen = {(root / record).resolve()}
        while prior:
            prior_path = (root / prior["path"]).resolve()
            if prior_path in seen:
                raise ValueError("Cycle in correction history")
            seen.add(prior_path)
            prior_bytes = artifact_bytes(prior["path"])
            if hashlib.sha256(prior_bytes).hexdigest() != prior["sha256"]:
                errors.append("Prior correction record changed")
                break
            if "recorded_at" in prior or "recorded_in_commit" in prior:
                commit, stamp = prior["recorded_in_commit"], prior["recorded_at"]
                if not re.fullmatch("[0-9a-f]{40}", commit) or datetime.fromisoformat(stamp).utcoffset() is None:
                    raise ValueError("Invalid Git recording metadata for predecessor")
                if verify_git_origin:
                    actual_stamp = subprocess.check_output(
                        ["git", "show", "-s", "--format=%cI", commit], cwd=root, text=True,
                    ).strip()
                    blob = subprocess.check_output(["git", "show", f"{commit}:{prior['path']}"], cwd=root)
                    if actual_stamp != stamp or blob != prior_bytes:
                        raise ValueError("Git commit does not match the predecessor timestamp and bytes")
                    added = subprocess.check_output(
                        ["git", "diff-tree", "--root", "-r", "--no-commit-id", "--name-only", "--diff-filter=A",
                         commit, "--", prior["path"]], cwd=root, text=True,
                    ).splitlines()
                    if prior["path"] not in added:
                        raise ValueError("Recorded commit did not add the predecessor snapshot")
                    verified_commits.append(commit)
            prior_record = json.loads(prior_bytes)
            if not isinstance(prior_record, dict):
                raise ValueError("Invalid prior correction record")
            prior = prior_record.get("supersedes")
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
        if verify_git_origin and not verified_commits:
            errors.append("No predecessor with verifiable Git recording metadata")
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        errors.append(str(exc))
    return {"status": "FAIL" if errors else "PASS", "errors": errors,
            "scope": "Correction and archive byte bindings", "verified_git_commits": verified_commits,
            "original_claim_validity": "NOT_AUTHENTICATED", "scientific_authorization": "NONE"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--record", default=RECORD, help="Explicit correction snapshot to verify")
    parser.add_argument("--verify-git-origin", action="store_true", help="Check recorded commits in a Git checkout containing the predecessor history")
    args = parser.parse_args()
    result = check(args.root, args.record, verify_git_origin=args.verify_git_origin)
    print(json.dumps(result, indent=2))
    return int(bool(result["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
