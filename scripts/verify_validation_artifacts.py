#!/usr/bin/env python3
"""CLI entry point for unified validation artifact verification (BNS-010, BNS-015)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from bionexus.validation_verifier import verify_validation_artifacts  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify BioNexus validation artifacts, checksums, and certification consistency."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root directory (default: current repo root)",
    )
    parser.add_argument(
        "--enforce-version",
        type=str,
        default=None,
        help="Enforce a specific version string (default: bionexus.versions.VERSION)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )
    args = parser.parse_args()

    result = verify_validation_artifacts(repo_root=args.root, enforce_version=args.enforce_version)

    if args.json:
        import json
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(result.summary_str())

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
