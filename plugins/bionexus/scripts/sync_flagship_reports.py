#!/usr/bin/env python3
"""Read-only historical report inventory; NEVER rebinds execution provenance."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from bionexus.validation_history import assess_history


def sync_nested_provenance(*args, **kwargs) -> None:
    raise RuntimeError("Execution provenance is immutable; run a new validation instead of rebinding history")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = assess_history(args.root)
    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
    print(payload)
    return 0 if result["archive_integrity"] == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
