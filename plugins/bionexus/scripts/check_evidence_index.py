#!/usr/bin/env python3
"""CLI tool for BioNexus Current Evidence Index and Upstream Invalidation/Recomputation Analysis."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from bionexus.evidence_index import EvidenceIndex


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect BioNexus Evidence Index and analyze upstream change impact."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root directory (default: current repo root)",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Compile current repository state and save to validation/EVIDENCE_INDEX.json",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the integrity of validation/EVIDENCE_INDEX.json against current files",
    )
    parser.add_argument(
        "--impact",
        action="store_true",
        help="Analyze impact of upstream changes (invalidated vs recomputation needed)",
    )
    parser.add_argument(
        "--changed-files",
        nargs="*",
        default=None,
        help="List of changed files to simulate or analyze",
    )
    parser.add_argument(
        "--broken-rules",
        nargs="*",
        default=None,
        help="List of broken or revoked scientific rule IDs to simulate",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format",
    )

    args = parser.parse_args()
    root = args.root
    index_file = root / "validation" / "EVIDENCE_INDEX.json"

    index = EvidenceIndex.build_current_index(root)

    if args.save:
        out_path = index.save(index_file)
        print(f"Successfully generated and saved Evidence Index to: {out_path.relative_to(root)}")
        return 0

    if args.check:
        if not index_file.is_file():
            print(f"Error: {index_file} not found. Run with --save first.")
            return 1
        loaded_index = EvidenceIndex.load(index_file)
        res = loaded_index.verify_index_integrity(root)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            if res["passed"]:
                print(f"=== Evidence Index Verification: PASS ({res['checked_count']} checks) ===")
            else:
                print(f"=== Evidence Index Verification: FAIL ({len(res['errors'])} errors) ===")
                for err in res["errors"]:
                    print(f"  [ERROR] {err}")
        return 0 if res["passed"] else 1

    if args.impact:
        impact = index.assess_upstream_changes(
            repo_root=root,
            changed_files=args.changed_files,
            broken_rules=args.broken_rules,
        )
        if args.json:
            print(json.dumps(impact.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(impact.summary_str())
        return 0

    # Default action: display index summary
    if args.json:
        print(json.dumps(index.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"=== BioNexus Current Evidence Index ({len(index.conclusions)} conclusions) ===")
        for cid, entry in index.conclusions.items():
            print(f"[{entry.verdict}] {cid}")
            print(f"  Statement: {entry.statement}")
            print(f"  Capability: {entry.capability_id}")
            print(f"  Rules: {', '.join(entry.rules)}")
            print(f"  Report: {entry.report_version.get('report_path')}")
            print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
