"""Replay the frozen 09-08 54-case DE audit challenge against rc.8 source.

Never overwrites BN-METHODS-20260908 freeze, frozen-source, or run-01.
"""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone

import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ORIGINAL = REPO / "review" / "methods-experiments-2026-09-08"
CASES = ORIGINAL / "run-01" / "challenge" / "cases"
ORIGINAL_OUTCOMES = ORIGINAL / "run-01" / "challenge" / "case-outcomes.csv"
RC8_COMMIT = "fffd792fcd3949805debeee5c421feee8fbba921"
OUT = HERE / "run-01"
SNAPSHOT = HERE / "rc8-source"


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def json_default(value):
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "value"):
        return value.value
    return str(value)


def write_json(path: Path, obj) -> None:
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, default=json_default, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def snapshot_rc8() -> dict:
    if SNAPSHOT.exists():
        raise FileExistsError(f"Refusing to overwrite snapshot {SNAPSHOT}")
    listed = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", RC8_COMMIT, "src/bionexus"],
        cwd=REPO,
        text=True,
    ).splitlines()
    if not listed:
        raise RuntimeError(f"No src/bionexus files at {RC8_COMMIT}")
    hashes = {}
    for rel in listed:
        content = subprocess.check_output(["git", "show", f"{RC8_COMMIT}:{rel}"], cwd=REPO)
        dest = SNAPSHOT / Path(rel).relative_to("src")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        hashes[rel] = digest_bytes(content)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    identity = {
        "study_id": "BN-METHODS-RC8-REPLAY-20260914",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "engine_commit": RC8_COMMIT,
        "workspace_head": head,
        "registration": "POST_OUTCOME_REPLAY_NOT_INDEPENDENT_STUDY",
        "source_file_count": len(hashes),
        "source_tree_sha256": digest_bytes(
            "\n".join(f"{rel} {hashes[rel]}" for rel in sorted(hashes)).encode("utf-8")
        ),
        "source_hashes": hashes,
        "protocol_sha256": digest_path(HERE / "PROTOCOL.md"),
        "runner_sha256": digest_path(Path(__file__)),
        "original_challenge_cases": str(CASES.relative_to(REPO).as_posix()),
        "python": sys.version,
        "platform": platform.platform(),
        "product_edits_during_replay": False,
    }
    write_json(HERE / "IDENTITY.json", identity)
    return identity


def load_engine():
    snapshot_path = str(SNAPSHOT)
    if snapshot_path in sys.path:
        sys.path.remove(snapshot_path)
    sys.path.insert(0, snapshot_path)
    for name in [key for key in sys.modules if key == "bionexus" or key.startswith("bionexus.")]:
        del sys.modules[name]
    module = importlib.import_module("bionexus.de_audit")
    imported = Path(module.__file__).resolve()
    expected = (SNAPSHOT / "bionexus" / "de_audit.py").resolve()
    if imported != expected:
        raise RuntimeError(f"Imported {imported}, expected {expected}")
    return module.audit_differential_expression


def severity_value(finding) -> str:
    severity = getattr(finding, "severity", None)
    if hasattr(severity, "value"):
        return str(severity.value)
    return str(severity)


def summarize_result(result) -> dict:
    findings = list(getattr(result, "findings", []) or [])
    checks = list(getattr(result, "checks", []) or [])
    return {
        "overall_status": result.overall_status,
        "passed": bool(result.passed),
        "blocker_count": int(result.blocker_count),
        "high_impact_count": int(result.high_impact_count),
        "advisory_count": int(result.advisory_count),
        "finding_rule_ids": [getattr(f, "rule_id", None) for f in findings],
        "finding_severities": [severity_value(f) for f in findings],
        "required_check_statuses": {
            getattr(c, "check_id", ""): getattr(getattr(c, "status", None), "value", str(getattr(c, "status", "")))
            for c in checks
            if getattr(c, "required_for_pass", False)
        },
    }


def synonym_receipt(receipt):
    if not isinstance(receipt, dict):
        return receipt
    patched = copy.deepcopy(receipt)
    status = str(patched.get("fit_status") or "")
    if status.upper().strip() == "COMPLETE":
        patched["fit_status"] = "COMPLETED"
        patched["_replay_fitstatus_synonym"] = "COMPLETE->COMPLETED"
    return patched


def checklist_decision(table: pd.DataFrame, metadata: pd.DataFrame, receipt) -> tuple[str, bool, bool]:
    valid_prob = "padj" in table.columns and table["padj"].dropna().between(0, 1).all()
    donors_ok = metadata.groupby("condition").donor.nunique().min() >= 3
    donor_record = bool(receipt and receipt.get("statistical_unit") == "donor")
    accepted = bool(valid_prob and donors_ok and donor_record)
    if accepted:
        return "ACCEPT", True, False
    return "REJECT", False, True


def load_case(folder: Path) -> dict:
    definition = json.loads((folder / "case.json").read_text(encoding="utf-8"))
    raw_receipt = json.loads((folder / "receipt.json").read_text(encoding="utf-8"))
    metadata = pd.read_csv(folder / "metadata.csv", dtype={"donor": str})
    table = pd.read_csv(folder / "de.csv")
    return {
        "folder": folder,
        "definition": definition,
        "receipt": raw_receipt,
        "metadata": metadata,
        "table": table,
        "de_path": folder / "de.csv",
    }


def run_arm(audit, case: dict, arm: str):
    started = time.perf_counter()
    family = case["definition"]["family"]
    claim = case["definition"]["claim"]
    receipt = case["receipt"]
    output = None
    if arm == "accept_all":
        status, accepted, issue = "ACCEPT", True, False
        abstain = False
    elif arm == "reject_all":
        status, accepted, issue = "REJECT", False, True
        abstain = False
    elif arm == "deterministic_checklist":
        status, accepted, issue = checklist_decision(case["table"], case["metadata"], receipt)
        abstain = False
    else:
        execution = None
        claim_text = claim
        if arm == "without_execution_metadata":
            execution = None
        elif arm == "without_claim_text":
            execution = receipt
            claim_text = None
        elif arm == "bionexus_full_fitstatus_synonym":
            execution = synonym_receipt(receipt)
        else:
            execution = receipt
        if arm == "without_claim_text":
            claim_text = None
        result = audit(
            de_table=case["de_path"],
            sample_metadata=case["metadata"],
            execution_record=execution,
            claim_text=claim_text,
            donor_col="donor",
            condition_col="condition",
        )
        output = result.to_dict()
        compact = summarize_result(result)
        output["_replay_compact"] = compact
        status = result.overall_status
        accepted = bool(result.passed)
        issue = any(severity_value(f) in {"BLOCKER", "HIGH_IMPACT"} for f in result.findings)
        abstain = status in {"NEEDS_DATA", "NOT_ASSESSED"}
        seconds = time.perf_counter() - started
        return {
            "status": status,
            "accepted": accepted,
            "issue_identified": bool(issue),
            "abstained": bool(abstain),
            "seconds": seconds,
            "output": output,
            "compact": compact,
        }
    return {
        "status": status,
        "accepted": accepted,
        "issue_identified": bool(issue),
        "abstained": bool(abstain),
        "seconds": time.perf_counter() - started,
        "output": output,
        "compact": None,
    }


def arm_summary(frame: pd.DataFrame) -> list[dict]:
    rows = []
    for arm, group in frame.groupby("arm"):
        invalid = group[group.invalid]
        valid = group[~group.invalid]
        rows.append(
            {
                "arm": arm,
                "invalid_cases": int(len(invalid)),
                "valid_cases": int(len(valid)),
                "invalid_accepted": int(invalid.accepted.sum()),
                "valid_retained": int(valid.accepted.sum()),
                "invalid_issue_identified": int(invalid.issue_identified.sum()),
                "invalid_abstained": int(invalid.abstained.sum()),
                "valid_abstained": int(valid.abstained.sum()),
                "unsupported_acceptance_rate": float(invalid.accepted.mean()) if len(invalid) else None,
                "valid_retention": float(valid.accepted.mean()) if len(valid) else None,
                "median_machine_seconds": float(group.seconds.median()),
            }
        )
    return rows


def compare_primary(original: pd.DataFrame, replay: pd.DataFrame) -> dict:
    def slice_arm(frame, arm):
        group = frame[frame.arm == arm]
        invalid = group[group.invalid]
        valid = group[~group.invalid]
        return {
            "invalid_accepted": int(invalid.accepted.sum()),
            "invalid_total": int(len(invalid)),
            "valid_retained": int(valid.accepted.sum()),
            "valid_total": int(len(valid)),
        }

    before = slice_arm(original, "bionexus_full")
    after = slice_arm(replay, "bionexus_full")
    synonym = slice_arm(replay, "bionexus_full_fitstatus_synonym")
    joint = after["valid_retained"] > before["valid_retained"] and after["invalid_accepted"] <= before["invalid_accepted"]
    return {
        "endpoint": "joint valid-retention increase without false-pass increase",
        "original_bionexus_full": before,
        "rc8_bionexus_full": after,
        "rc8_fitstatus_synonym_exploratory": synonym,
        "valid_retention_improved": after["valid_retained"] > before["valid_retained"],
        "false_pass_not_worse": after["invalid_accepted"] <= before["invalid_accepted"],
        "joint_improvement": joint,
        "false_pass_increased": after["invalid_accepted"] > before["invalid_accepted"],
    }


def family_table(original: pd.DataFrame, replay: pd.DataFrame) -> list[dict]:
    rows = []
    orig = original[original.arm == "bionexus_full"]
    new = replay[replay.arm == "bionexus_full"]
    families = sorted(set(orig.family) | set(new.family))
    for family in families:
        o = orig[orig.family == family]
        n = new[new.family == family]
        rows.append(
            {
                "family": family,
                "invalid": bool(o.invalid.iloc[0]) if len(o) else bool(n.invalid.iloc[0]),
                "n": int(len(o)),
                "original_accepted": int(o.accepted.sum()),
                "rc8_accepted": int(n.accepted.sum()),
                "original_statuses": sorted(set(o.status.astype(str))),
                "rc8_statuses": sorted(set(n.status.astype(str))),
            }
        )
    return rows


def main() -> None:
    if OUT.exists():
        raise FileExistsError(f"Refusing to overwrite {OUT}")
    if not CASES.is_dir():
        raise FileNotFoundError(CASES)
    identity = snapshot_rc8()
    audit = load_engine()
    OUT.mkdir(parents=True, exist_ok=False)
    write_json(
        OUT / "execution-start.json",
        {
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "identity_sha256": digest_path(HERE / "IDENTITY.json"),
            "engine_commit": identity["engine_commit"],
        },
    )
    case_out = OUT / "cases"
    case_out.mkdir()
    rows = []
    folders = sorted(path for path in CASES.iterdir() if path.is_dir())
    if len(folders) != 54:
        raise RuntimeError(f"Expected 54 case folders, found {len(folders)}")
    arms = [
        "accept_all",
        "reject_all",
        "deterministic_checklist",
        "bionexus_full",
        "without_claim_text",
        "without_execution_metadata",
        "bionexus_full_fitstatus_synonym",
    ]
    started = time.perf_counter()
    for index, folder in enumerate(folders, start=1):
        case = load_case(folder)
        definition = case["definition"]
        dest = case_out / definition["case_id"]
        dest.mkdir()
        write_json(dest / "case.json", definition)
        for arm in arms:
            result = run_arm(audit, case, arm)
            if result["output"] is not None:
                write_json(dest / f"{arm}.json", result["output"])
            rows.append(
                {
                    "case_id": definition["case_id"],
                    "family": definition["family"],
                    "paraphrase": definition["paraphrase"],
                    "invalid": bool(definition["invalid"]),
                    "arm": arm,
                    "status": result["status"],
                    "accepted": bool(result["accepted"]),
                    "issue_identified": bool(result["issue_identified"]),
                    "abstained": bool(result["abstained"]),
                    "seconds": result["seconds"],
                    "finding_rule_ids": ",".join(result["compact"]["finding_rule_ids"]) if result["compact"] else "",
                    "finding_severities": ",".join(result["compact"]["finding_severities"]) if result["compact"] else "",
                }
            )
        print(f"{index}/54 {definition['case_id']}", flush=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / "case-outcomes.csv", index=False)
    original = pd.read_csv(ORIGINAL_OUTCOMES)
    original["invalid"] = original["invalid"].astype(str).str.lower().isin(["true", "1"])
    original["accepted"] = original["accepted"].astype(str).str.lower().isin(["true", "1"])
    comparison = compare_primary(original, frame)
    payload = {
        "status": "COMPLETE",
        "n_cases": int(frame.case_id.nunique()),
        "n_families": int(frame.family.nunique()),
        "engine_commit": RC8_COMMIT,
        "independent_expert_labels": False,
        "live_llm_baselines": "NOT_RUN",
        "human_review_minutes": None,
        "scientific_authorization": "NONE",
        "arms": arm_summary(frame),
        "primary_comparison": comparison,
        "family_comparison_bionexus_full": family_table(original, frame),
        "warning": (
            "Issue identification is any high-impact or blocker finding, not necessarily "
            "correct localization. The fit-status synonym arm is exploratory."
        ),
    }
    write_json(OUT / "summary.json", payload)
    write_json(
        OUT / "execution-end.json",
        {
            "status": "COMPLETE",
            "seconds": time.perf_counter() - started,
            "ended_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    print(json.dumps(comparison, indent=2), flush=True)


if __name__ == "__main__":
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    main()
