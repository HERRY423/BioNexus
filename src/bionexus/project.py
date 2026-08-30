"""
Project-level ledger for BioNexus: cross-session registry of datasets and Run Capsules.

Closes the project-memory gap: individual Run Capsules are self-contained, but nothing
bound them to a *project* across sessions and agents. The ledger is a single JSON file
(``.bionexus/project.json``) that registers:

- datasets: path, SHA-256, size, semantic type (deduplicated by content hash)
- runs: Run Capsule directories, cryptographically verified at registration time
  (``bionexus.artifacts.verify_run_bundle``); tampered or incomplete capsules are
  refused fail-closed and never silently registered.

Honesty invariants:
- The ledger records what ran and what data existed; it does not certify scientific
  conclusions. Maturity always comes from the capsule's own EvidenceCard.
- Not an electronic lab notebook and not a GxP / 21 CFR Part 11 system.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union

from bionexus.artifacts import load_run_bundle, verify_run_bundle
from bionexus.contracts import GRADE_A, attach_meta, refuse
from bionexus.provenance import sha256_file

PathLike = Union[str, Path]

LEDGER_VERSION = "1.0"
LEDGER_DIRNAME = ".bionexus"
LEDGER_FILENAME = "project.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectLedger:
    """A project-scoped registry of datasets and Run Capsules."""

    def __init__(self, root: PathLike, *, create: bool = False) -> None:
        self.root = Path(root).resolve()
        self.path = self.root / LEDGER_DIRNAME / LEDGER_FILENAME
        if self.path.is_file():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        elif create:
            self.data = {
                "ledger_version": LEDGER_VERSION,
                "name": self.root.name,
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
                "datasets": [],
                "runs": [],
            }
            self.save()
        else:
            raise FileNotFoundError(
                f"No BioNexus project ledger at {self.path}. Run 'bionexus project init' first."
            )

    # ------------------------------------------------------------------ persist
    def save(self) -> Path:
        self.data["updated_at"] = _utc_now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        return self.path

    # ---------------------------------------------------------------- datasets
    def register_dataset(
        self,
        path: PathLike,
        *,
        semantic_type: str = "unspecified",
        role: str = "input",
    ) -> Dict[str, Any]:
        """Register a dataset by content hash. Duplicate hashes update the existing entry."""
        p = Path(path)
        if not p.is_file():
            return refuse(
                method="bionexus.project.register_dataset",
                reason=f"Dataset not found or is not a regular file: {p}",
                extra={"path": str(p)},
            )
        size_bytes = p.stat().st_size
        digest = sha256_file(p)
        existing = self.find_dataset_by_hash(digest)
        if existing is not None:
            existing["paths"] = sorted({*existing.get("paths", [existing.get("path")]), str(p)})
            existing["registered_at"] = _utc_now()
            entry = existing
        else:
            entry = {
                "sha256": digest,
                "size_bytes": size_bytes,
                "semantic_type": semantic_type,
                "role": role,
                "paths": [str(p)],
                "registered_at": _utc_now(),
            }
            self.data["datasets"].append(entry)
        self.save()
        return attach_meta(
            {"refused": False, "dataset": entry, "deduplicated": existing is not None},
            method="bionexus.project.register_dataset",
            backend="bionexus.project",
            evidence_grade=GRADE_A,
            limitations=["Registration records existence and hash; it does not validate data semantics."],
        )

    def find_dataset_by_hash(self, digest: str) -> Optional[Dict[str, Any]]:
        for entry in self.data["datasets"]:
            if entry.get("sha256") == digest:
                return entry
        return None

    # -------------------------------------------------------------------- runs
    def register_run(self, capsule_dir: PathLike) -> Dict[str, Any]:
        """
        Register a Run Capsule after cryptographic verification.

        Incomplete or tampered capsules are refused and never registered (fail-closed).
        """
        capsule = Path(capsule_dir)
        run_file = capsule / "run.json" if capsule.is_dir() else capsule
        if not (capsule.is_dir() or run_file.is_file()):
            return refuse(
                method="bionexus.project.register_run",
                reason=f"Run Capsule not found: {capsule}",
                extra={"path": str(capsule)},
            )
        try:
            manifest = load_run_bundle(capsule)
        except Exception as e:
            return refuse(
                method="bionexus.project.register_run",
                reason=f"Run Capsule unreadable: {e}",
                extra={"path": str(capsule)},
            )

        verification = verify_run_bundle(capsule)
        if not verification.valid:
            return refuse(
                method="bionexus.project.register_run",
                reason=(
                    f"Run Capsule '{verification.run_id}' failed integrity verification and was NOT "
                    f"registered: missing={verification.missing_files} tampered={verification.tampered_files}"
                ),
                extra={"path": str(capsule), "verification": verification.to_dict()},
            )

        run_id = manifest.get("run_id", verification.run_id)
        base_dir = (capsule if capsule.is_dir() else run_file.parent).resolve()
        entry = {
            "run_id": run_id,
            "capability_id": manifest.get("capability_id"),
            "skill_name": manifest.get("skill_name"),
            "status": manifest.get("status"),
            "execution_state": manifest.get("execution_state"),
            "conclusion_maturity": manifest.get("conclusion_maturity"),
            "conclusion_maturity_source": "capsule EvidenceCard (unmodified)",
            "capsule_dir": str(base_dir),
            "verified": True,
            "registered_at": _utc_now(),
        }
        if any(r.get("capsule_dir") == entry["capsule_dir"] for r in self.data["runs"]):
            return refuse(
                method="bionexus.project.register_run",
                reason=f"Run Capsule already registered: {base_dir}",
                extra={"path": str(base_dir)},
            )
        self.data["runs"].append(entry)
        self.save()
        return attach_meta(
            {"refused": False, "run": entry},
            method="bionexus.project.register_run",
            backend="bionexus.project",
            evidence_grade=GRADE_A,
            limitations=["Run registration verifies capsule integrity; it does not certify scientific conclusions."],
        )

    # ------------------------------------------------------------------ status
    def status(self) -> Dict[str, Any]:
        """Project summary: ledger identity plus dataset/run counts and listings."""
        runs = self.data.get("runs", [])
        datasets = self.data.get("datasets", [])
        maturity_counts: Dict[str, int] = {}
        for run in runs:
            m = run.get("conclusion_maturity") or "UNKNOWN"
            maturity_counts[m] = maturity_counts.get(m, 0) + 1
        return {
            "ledger_version": self.data.get("ledger_version"),
            "name": self.data.get("name"),
            "project_root": str(self.root),
            "ledger_path": str(self.path),
            "created_at": self.data.get("created_at"),
            "updated_at": self.data.get("updated_at"),
            "dataset_count": len(datasets),
            "run_count": len(runs),
            "conclusion_maturity_counts": maturity_counts,
            "datasets": datasets,
            "runs": runs,
        }

    def status_markdown(self) -> str:
        s = self.status()
        lines = [
            f"### BioNexus Project Ledger: {s['name']}",
            f"- Root: `{s['project_root']}`",
            f"- Ledger: `{s['ledger_path']}` (v{s['ledger_version']}, updated {s['updated_at']})",
            f"- Datasets: **{s['dataset_count']}** | Run Capsules: **{s['run_count']}**",
        ]
        if s["conclusion_maturity_counts"]:
            counts = ", ".join(f"`{k}`: {v}" for k, v in sorted(s["conclusion_maturity_counts"].items()))
            lines.append(f"- Conclusion maturity across registered runs: {counts}")
        if s["runs"]:
            lines += [
                "",
                "| Run | Capability | Status | Maturity | Capsule |",
                "|---|---|---|---|---|",
            ]
            for run in s["runs"]:
                lines.append(
                    f"| `{run.get('run_id')}` | `{run.get('capability_id')}` | {run.get('status')} "
                    f"| {run.get('conclusion_maturity')} | `{run.get('capsule_dir')}` |"
                )
        return "\n".join(lines)


def find_project_root(start: PathLike) -> Optional[Path]:
    """Walk upwards from ``start`` looking for a ``.bionexus/project.json`` ledger."""
    current = Path(start).resolve()
    for candidate in (current, *current.parents):
        if (candidate / LEDGER_DIRNAME / LEDGER_FILENAME).is_file():
            return candidate
    return None
