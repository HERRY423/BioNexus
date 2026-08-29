#!/usr/bin/env python3
"""Assess a host-assembled multi-source claim packet without deciding it."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _REPO_ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.ecosystem_claim import (  # noqa: E402
    EcosystemClaimPacket,
    assess_ecosystem_claim,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a passive BioNexus Warrant + Audit + EvidenceCard assessment"
    )
    parser.add_argument("packet", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    try:
        payload = json.loads(args.packet.read_text(encoding="utf-8"))
        packet = EcosystemClaimPacket.from_dict(payload)
        result = assess_ecosystem_claim(packet)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "INVALID", "errors": [str(exc)]}, indent=2), file=sys.stderr)
        return 2

    output = json.dumps(result.to_dict(), indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output + "\n", encoding="utf-8")
        print(f"Ecosystem claim assessment written to {args.out}")
    else:
        print(output)

    return {"PASS": 0, "CONFLICTED": 1, "BLOCKED": 2}[result.audit.status]


if __name__ == "__main__":
    raise SystemExit(main())
