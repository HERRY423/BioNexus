#!/usr/bin/env python3
"""Retired legacy study-attestation generator.

The former implementation minted local keys and labelled the resulting structures
as independent Sigstore/Rekor/RFC3161 evidence. That path is intentionally disabled
by the Phase-1 Scientific Trust Reset.
"""

import sys


def main() -> int:
    print(
        "DISABLED: legacy self-attestation cannot establish external scientific trust. "
        "Create bionexus.evidence-attestation.v1 records with an independently managed "
        "key, explicit trust registry, artifact digest, expiry, and revocation policy.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
