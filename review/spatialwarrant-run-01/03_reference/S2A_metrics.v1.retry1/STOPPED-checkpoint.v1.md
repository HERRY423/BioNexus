# SpatialWarrant S2A retry1 stopped checkpoint

Status: STOPPED. Retry1 did not complete. No retry2 was created.
Started: 2026-09-05T11:43:33.527993+00:00
Interruption recorded: 2026-09-05T15:23:37.711441+00:00

The Codex turn was interrupted while the retry1 full matrix scan was running. The last received progress was 42%, or 75,375,795 of 177,994,136 declared coordinate entries. The execution session no longer existed on resumption, visible Python processes had zero CPU change during a three-second sample, and the target contained only pre-scan artifacts. Therefore the full scan, QC metrics, input-validation artifact, BioNexus sidecar, completed manifest and completion checkpoint are absent.

The serialization self-test passed before scanning and is preserved. This is engineering evidence only. The earlier failed directory and its failure evidence remain unchanged. The retry1 directory is retained as a stopped partial run and must not be represented as successful.

S2B: PENDING. S3: BLOCKED. Patient-level inference: BLOCKED. Machine verdict: PENDING. Biological conclusion: PENDING.
