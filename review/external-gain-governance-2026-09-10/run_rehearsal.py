"""Local synthetic workflow rehearsal. No expert labels or decisions are generated."""
from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from bionexus.de_audit import audit_differential_expression
from bionexus.de_external_study import digest, main as study_main
from bionexus.de_pilot import demo_inputs, summarize_reviews, write_bundle
from bionexus.rule_impact import main as impact_main


def save(path, data):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def run(destination):
    destination.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[2]
    sources = ["de_external_study.py", "pilot_costs.py", "de_pilot.py", "de_bundle.py",
               "rule_calibration.py", "rule_impact.py", "de_audit.py", "human_adjudication.py"]
    inventory = {name: hashlib.sha256((root / "src/bionexus" / name).read_bytes()).hexdigest() for name in sources}
    save(destination / "component-source-hashes.json", inventory)
    audit = audit_differential_expression(**demo_inputs())
    bundle = write_bundle(audit, destination / "synthetic-bundle", inputs={}, claim="SYNTHETIC DEMO ONLY", synthetic=True)
    before_bytes = {p.name: p.read_bytes() for p in bundle.iterdir()}
    source_hash = digest(inventory)
    packet_hash = hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest()
    plan = {"schema": "bionexus.de-external-plan.v1", "study_id": "SYNTHETIC_SOFTWARE_REHEARSAL",
            "intended_use": "exercise contracts, not a scientific study", "source_sha256": source_hash,
            "frozen_at": datetime.now(timezone.utc).isoformat(), "developer_ids": ["SOFTWARE_FIXTURE"],
            "development_dataset_sha256": [packet_hash],
            "cases": [{"case_id": "DEMO", "task_family": "SYNTHETIC", "site_id": "NO_LAB",
                       "packet_sha256": packet_hash, "dataset_sha256": packet_hash,
                       "data_origin": "SYNTHETIC_DEMO", "not_used_in_development": False}]}
    save(destination / "synthetic-plan.json", plan)
    study_main(["template", "--out", str(destination / "external-plan-BLANK.json")])
    study_main(["template", "--plan", str(destination / "synthetic-plan.json"),
                "--out", str(destination / "synthetic-observations.json")])
    study_main(["score", str(destination / "synthetic-plan.json"), str(destination / "synthetic-observations.json"),
                "--expected-plan-sha256", digest(plan), "--out", str(destination / "synthetic-summary.json")])
    first_rule = audit.to_dict()["findings"][0]["rule_id"]
    old = {"rehearsal_only": True, "rules": {"DEMO_ONLY": {"aliases": [first_rule], "applicable_regimes": []}}}
    new = deepcopy(old)
    new["rules"]["DEMO_ONLY"]["note"] = "synthetic revision to exercise impact inventory; never activated"
    save(destination / "synthetic-registry-before.json", old)
    save(destination / "synthetic-registry-after.json", new)
    impact_main([str(destination / "synthetic-registry-before.json"), str(destination / "synthetic-registry-after.json"),
                 str(bundle), "--out", str(destination / "synthetic-rule-impact.json")])
    summary = json.loads((destination / "synthetic-summary.json").read_text(encoding="utf-8"))
    impact = json.loads((destination / "synthetic-rule-impact.json").read_text(encoding="utf-8"))
    assert summary["declared_holdout_tasks"] == 0 and summary["net_benefit"] == "NOT_ESTABLISHED"
    assert summary["joint_quality_and_time_gain_observed"] is None
    assert impact["cases"][0]["impact"] == "REASSESS_REQUIRED"
    assert impact["cases"][0]["human_decision"] == "PENDING"
    assert before_bytes == {p.name: p.read_bytes() for p in bundle.iterdir()}
    pilot = summarize_reviews([bundle / "review.json"])
    assert pilot["included_cases"] == 0
    save(destination / "synthetic-pilot-summary.json", pilot)
    save(destination / "REHEARSAL.json", {
        "status": "LOCAL_SOFTWARE_REHEARSAL_COMPLETED", "data_origin": "SYNTHETIC_DEMO",
        "component_source_inventory_sha256": source_hash, "external_tasks_scored": 0,
        "expert_labels_created": 0, "laboratory_time_records_created": 0,
        "old_bundle_bytes_preserved": True, "scientific_authorization": "NONE",
        "external_validation": "NOT_ESTABLISHED", "net_benefit": "NOT_ESTABLISHED"})
    print(json.dumps({"rehearsal": str(destination.resolve()), "external_tasks_scored": 0,
                      "old_bundle_bytes_preserved": True, "net_benefit": "NOT_ESTABLISHED"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    run(parser.parse_args().destination)
