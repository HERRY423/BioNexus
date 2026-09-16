"""Freeze an honest zero-case external-pilot launch bundle."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from bionexus.de_external_study import digest, validate_plan
from bionexus.provenance import sidecar

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = ROOT.parents[1]
OUT = HERE / "attempt-03"
SUMMARY = ROOT / "attempt-02/SUMMARY.json"
REGISTRY = REPO / "validation/ivn/REGISTRY.json"
GENERATED = ("PLAN_TEMPLATE.json", "PILOT_STATUS.json", "SHA256SUMS.json", "PROVENANCE.json")
STATIC = (
    "PROTOCOL.zh-CN.md", "README.zh-CN.md", "TASK_INTAKE_TEMPLATE.json",
    "REFERENCE_REVIEW_TEMPLATE.json", "ARM_OUTPUT_TEMPLATE.json", "COST_LOG_TEMPLATE.csv",
)


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def main() -> None:
    if OUT.exists():
        raise FileExistsError(f"refusing to overwrite {OUT}")
    OUT.mkdir()
    for name in STATIC:
        shutil.copy2(HERE / name, OUT / name)
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc).isoformat()
    developers = [row["name"] for row in registry["author_roster"]]
    development_datasets = set()
    for path in (REPO / "review/methods-experiments-2026-09-08/run-01/challenge/cases").glob("*/receipt.json"):
        receipt = json.loads(path.read_text(encoding="utf-8"))
        value = str(receipt.get("counts_sha256") or "").lower() if isinstance(receipt, dict) else ""
        if re.fullmatch(r"[0-9a-f]{64}", value) and set(value) != {"0"}:
            development_datasets.add(value)
    if not development_datasets:
        raise RuntimeError("no valid development dataset hashes found")
    plan = {
        "schema": "bionexus.de-external-plan.v1",
        "study_id": "BN-DE-EXTERNAL-PILOT-PENDING-CUSTODIAN",
        "intended_use": "Feasibility pilot for descriptive paired error and person-time estimation; not confirmatory validation.",
        "source_sha256": summary["source_tree_sha256"],
        "frozen_at": now,
        "developer_ids": developers,
        "development_dataset_sha256": sorted(development_datasets),
        "cases": [],
    }
    validate_plan(plan)
    write_new(OUT / "PLAN_TEMPLATE.json", plan)
    status = {
        "schema": "bionexus.de-external-pilot-status.v1",
        "status": "LAUNCH_PACKAGE_READY_AWAITING_EXTERNAL_INPUT",
        "generated_at": now,
        "candidate_source_sha256": summary["source_tree_sha256"],
        "plan_template_sha256": digest(plan),
        "registered_development_dataset_hashes": len(development_datasets),
        "actual_external_tasks": 0,
        "actual_external_sites": 0,
        "tasks_with_two_eligible_blinded_reviews": 0,
        "fully_costed_tasks": 0,
        "registry_external_lab_studies": len(registry.get("lab_studies", [])),
        "registry_non_author_reviews": len(registry.get("reviews", [])),
        "pilot_executed": False,
        "external_validation": "NOT_ESTABLISHED",
        "net_benefit": "NOT_ESTABLISHED",
        "scientific_authorization": "NONE",
        "next_state_requires": [
            "custodian-frozen real external task packets",
            "two independent arm-blinded reference reviews per task before arm outputs",
            "baseline and assisted outputs",
            "complete five-category person-time records or explicit missingness"
        ]
    }
    write_new(OUT / "PILOT_STATUS.json", status)
    manifest_files = [OUT / name for name in STATIC] + [OUT / "PLAN_TEMPLATE.json", OUT / "PILOT_STATUS.json"]
    manifest = {
        "schema": "bionexus.sha256-manifest.v1",
        "files": {path.name: sha_file(path) for path in manifest_files},
    }
    manifest["aggregate_sha256"] = hashlib.sha256(
        "\n".join(f"{k} {manifest['files'][k]}" for k in sorted(manifest["files"])).encode()
    ).hexdigest()
    write_new(OUT / "SHA256SUMS.json", manifest)
    provenance = sidecar(
        activity_name="freeze_external_de_pilot_launch_package",
        input_files=[SUMMARY, REGISTRY, *manifest_files],
        output_files=[OUT / "SHA256SUMS.json"],
        parameters={"actual_external_tasks": 0, "scientific_authorization": "NONE"},
        method="local file hashing and template validation",
        backend="bionexus.de_external_study.validate_plan",
    )
    write_new(OUT / "PROVENANCE.json", provenance)
    package_files = manifest_files + [OUT / "SHA256SUMS.json", OUT / "PROVENANCE.json"]
    with zipfile.ZipFile(OUT / "external-pilot-launch.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in package_files:
            archive.write(path, path.name)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
