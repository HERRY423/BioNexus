# Independent blinded review instructions

The reviewer must be independent of BioNexus implementation and endpoint selection. The project authors must not fill or sign the attestation on the reviewer's behalf.

Before receiving the arm key, the reviewer records the hashes of the preregistration, executable analysis code, and blinded packet. The reviewer runs the locked analysis using only opaque cohort, participant, and arm identifiers; verifies that the 12-donor negative control contains exactly 4,095 non-identity sign flips; and records every failed, negative, missing, and abstained endpoint.

After the primary decision is written and timestamped, a custodian may release the arm key for interpretation. The reviewer then returns `INDEPENDENT_BIOSTATISTICIAN_ATTESTATION.json` with all required fields and a verifiable signature. `PENDING`, self-signed, missing-conflict, or condition-aware analysis is invalid and forces `ABSTAIN`.

The predecessor result BN-PB-IV-002 (`p = 0.05859375`) is historical evidence and must remain a negative result. It cannot be combined with, overwritten by, or reinterpreted through BN-PB-IV-003.
