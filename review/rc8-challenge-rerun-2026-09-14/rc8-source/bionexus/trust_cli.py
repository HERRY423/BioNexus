"""Command-line verifier for BioNexus target-bound evidence attestations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from bionexus.trust_evidence import (
    AttestationVerification,
    EvidenceAttestation,
    TrustDecision,
    TrustRegistry,
    verify_attestation,
)


def _default_registry_path() -> Path:
    return Path(__file__).parent / "data" / "trust_registry.json"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bionexus-evidence-verify",
        description="Verify a target-bound scientific evidence signature and revocation state.",
    )
    parser.add_argument("attestation", type=Path)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--trust-registry", type=Path, default=_default_registry_path())
    args = parser.parse_args(argv)

    try:
        attestation = EvidenceAttestation.from_dict(
            json.loads(args.attestation.read_text(encoding="utf-8"))
        )
        registry = TrustRegistry.load(args.trust_registry)
        result = verify_attestation(attestation, registry, artifact_path=args.artifact)
    except Exception as exc:
        result = AttestationVerification(TrustDecision.MALFORMED, (str(exc),))

    print(
        json.dumps(
            {
                "decision": result.decision.value,
                "accepted": result.accepted,
                "attestation_id": result.attestation_id,
                "artifact_sha256": result.artifact_sha256,
                "reasons": list(result.reasons),
            },
            indent=2,
        )
    )
    return 0 if result.accepted else 2


if __name__ == "__main__":
    sys.exit(main())
