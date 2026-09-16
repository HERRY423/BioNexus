"""Read-only rule-registry change inventory against supplied historic DE bundles.

This prepares a human reassessment queue, never a revised scientific verdict.
Missing rule execution traces must not turn into 'unaffected'.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from bionexus.de_bundle import verify_de_bundle
from bionexus.de_external_study import _load, digest


def assess_rule_change(before: dict, after: dict, bundles: list[str | Path]) -> dict:
    old, new = before.get("rules"), after.get("rules")
    if not isinstance(old, dict) or not isinstance(new, dict):
        raise ValueError("two rule registry snapshots required")
    changes = []
    for rid in sorted(set(old) | set(new)):
        a, b = old.get(rid), new.get(rid)
        if a == b:
            continue
        if any(v is not None and not isinstance(v, dict) for v in (a, b)):
            raise ValueError("rule records must be objects")
        aliases = []
        for rule in (a, b):
            if rule:
                declared = rule.get("aliases", [])
                if not isinstance(declared, list) or any(not isinstance(x, str) for x in declared):
                    raise ValueError("rule aliases must be text lists")
                aliases.extend(declared)
        changes.append({"rule_id": rid, "aliases": sorted(set(aliases)),
                        "change": "ADDED" if a is None else "REMOVED" if b is None else "MODIFIED",
                        "before_sha256": digest(a) if a is not None else None,
                        "after_sha256": digest(b) if b is not None else None,
                        "before_scope": a.get("applicable_regimes", []) if a else [],
                        "after_scope": b.get("applicable_regimes", []) if b else []})
    affected_ids = {value for c in changes for value in [c["rule_id"], *c["aliases"]]}
    cases, seen = [], set()
    for bundle in bundles:
        directory = Path(bundle)
        resolved = str(directory.resolve())
        if resolved in seen:
            raise ValueError("duplicate bundle path")
        seen.add(resolved)
        integrity = verify_de_bundle(directory)
        case = {"bundle": resolved, "bundle_integrity": integrity["status"],
                "manifest_sha256": integrity.get("manifest_sha256"), "human_owner": None,
                "human_decision": "PENDING", "scientific_authorization": "NONE"}
        if integrity["status"] not in {"CONSISTENT", "LEGACY_LIMITED"}:
            case.update(impact="INTEGRITY_BLOCKED", issues=integrity["issues"])
        else:
            audit_bytes = (directory / "audit.json").read_bytes()
            manifest_bytes = (directory / "manifest.json").read_bytes()
            if (hashlib.sha256(manifest_bytes).hexdigest() != integrity["manifest_sha256"]
                    or hashlib.sha256(audit_bytes).hexdigest() != json.loads(manifest_bytes)["audit_sha256"]):
                raise ValueError("bundle changed during impact inventory")
            audit = json.loads(audit_bytes)
            if any(not isinstance(f, dict) or not isinstance(f.get("rule_id"), str) for f in audit["findings"]):
                raise ValueError("audit findings must carry explicit rule IDs")
            matched = sorted({f.get("rule_id") for f in audit["findings"] if f.get("rule_id") in affected_ids})
            case.update(audit_sha256=hashlib.sha256(audit_bytes).hexdigest(), previous_status=integrity["audit_status"],
                        matched_rule_ids=matched,
                        impact=("REASSESS_REQUIRED" if matched else "RULE_APPLICATION_UNRECORDED") if changes
                        else "NO_REGISTRY_CHANGE")
        cases.append(case)
    return {"schema": "bionexus.rule-impact.v1", "before_registry_sha256": digest(before),
            "after_registry_sha256": digest(after), "changes": changes, "cases": cases,
            "scope": "SUPPLIED_BUNDLES_AND_REGISTRY_ONLY", "rule_revision_approval": "NOT_ESTABLISHED",
            "scientific_authorization": "NONE",
            "limitations": ["Findings are not a complete rule-application trace; no matching finding cannot establish no impact.",
                            "Registry comparison does not detect implementation-only rule changes or audits not supplied.",
                            "No old artifact is modified, no rule activated, and no historical scientific conclusion upgraded.",
                            "Snapshot hashes bind content, not independent reviewer identity or approval."]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("bundles", nargs="+")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        result = assess_rule_change(_load(args.before), _load(args.after), args.bundles)
        with Path(args.out).open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(1, f"Invalid rule impact input: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
