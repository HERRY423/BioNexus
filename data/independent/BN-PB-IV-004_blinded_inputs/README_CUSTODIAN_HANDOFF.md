# BN-PB-IV-004 custodian handoff

This directory is an intake boundary, not a place to commit the condition key
or raw participant identifiers. The independent data custodian must provide the
real C04 files only after the preregistration lock has been recorded.

Required inputs:

1. `C04_AUTHORITATIVE_LIMS_MANIFEST.csv` kept locally by the custodian and
   validated with `scripts/validate_c04_lims_pairing.py`.
2. `C04_BLINDED_PSEUDOBULK.h5ad` containing only opaque subject/arm labels.
3. `C04_BLINDED_SAMPLE_MANIFEST.csv` with 24 opaque rows.
4. `CUSTODIAN_DATA_GATE_ATTESTATION.json` filled from the repository template,
   with `status: SIGNED_COMPLETE`, hashes, UTC signature time, and a real
   signature or detached signature hash.

Use the authoritative-manifest preflight before producing the blinded files:

```powershell
python scripts\validate_c04_lims_pairing.py C04_AUTHORITATIVE_LIMS_MANIFEST.csv --report C04_LIMS_PAIRING_PREFLIGHT.json
```

The expected result is `PASS`; an `ABSTAIN` report must not be overridden.

The authoritative LIMS manifest must never be committed to Git, copied into
the blinded packet, or used to infer pairs from GSM numbers, filenames, lane
order, plate proximity, or expression similarity. The completed arm key stays
with the independent custodian.

After all four blinded materials exist, run:

```powershell
python scripts\freeze_pseudobulk_blinded_packet.py
```

The gate must be `PASS` before any outcome code receives the condition key.
