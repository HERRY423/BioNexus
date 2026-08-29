#!/usr/bin/env python3
"""Audit one host-supplied external evidence envelope."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _REPO_ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.ecosystem_intake import (  # noqa: E402
    ExternalEvidenceEnvelope,
    audit_external_evidence,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit a BioNexus external evidence envelope")
    parser.add_argument("envelope", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    try:
        payload = json.loads(args.envelope.read_text(encoding="utf-8"))
        envelope = ExternalEvidenceEnvelope.from_dict(payload)
        result = audit_external_evidence(envelope)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "INVALID", "errors": [str(exc)]}, indent=2), file=sys.stderr)
        return 2

    output = json.dumps(result.to_dict(), indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output + "\n", encoding="utf-8")
        print(f"External evidence audit written to {args.out}")
    else:
        print(output)
    return 0 if result.status == "VALID" else 1


if __name__ == "__main__":
    raise SystemExit(main())

