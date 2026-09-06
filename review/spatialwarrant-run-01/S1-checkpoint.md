# SpatialWarrant S1 checkpoint

Status: COMPLETED_WITH_OPEN_IDENTITY_AND_PATHOLOGY_GATES. STOPPED_AFTER_S1; S2_NOT_AUTHORIZED.
Timestamp: 2026-09-05T07:02:02.134053+00:00

The user approved v1 SHA-256 854e2d06eb25903a870606934964fd8b7f0a40a16a9658ef565cf5ab14a03c82 for S1 only. The D storage-v2 plan and its failed writeability check remain unchanged, with the user's NOT_APPROVED decision recorded separately in 00_plan. All S0-S7 modules, scientific questions, methods, claims and evidence boundaries are retained.

## Authorization and storage

- All input, extraction, metadata, scripts, logs, manifests and audit artifacts are under C:\Plugin\BioNexus\review\spatialwarrant-run-01.
- Exact pre-S1 C free space: 53911097344 bytes. Non-destructive 55-byte write/flush/read check matched and was removed.
- User-specified start gate: 32212254720 bytes (30 GiB). Runtime write floor: 21474836480 bytes (20 GiB), enforced on download/extraction chunks. No floor-triggered stop occurred.
- C free at this checkpoint measurement: 46966353920 bytes (43.741 GiB).
- No S2 execution, no S2-S6 package installation, no biological conclusion or scientific verdict. Scientific results and machine verdict remain PENDING.

## Acquired inputs and technical checks

| Input | Observed S1 result |
| --- | --- |
| Zenodo 4739739 | All five publisher files acquired; exact sizes and provider MD5 verified; archives safely extracted; per-member byte hashes saved |
| GSE176078 | Full 558829202-byte scRNA archive acquired; original interrupted prefix/ranges preserved; safe extraction completed; provider checksum not supplied, so no provider-checksum success claimed |
| scRNA release | 100064 metadata rows / 26 orig.ident sample labels; 29733 feature symbols; barcode/metadata join matches; no Patient column |
| 10x Block A Section 1 | Official web summary, filtered H5 and spatial archive acquired; H5 shape [36601, 3798], GRCh38 identifiers and barcode-coordinate presence checked; no transfer run |
| Literature | Life Sciences Literature PubMed efetch actually succeeded for PMID 34493872 / DOI 10.1038/s41588-021-00911-1; original plugin request/return/XML retained; additional PMC BioC source saved separately |
| Primary program | Exact MSigDB 2024.1.Hs source and 200-member set hashed; 196 common unambiguous symbols across all six raw feature lists (98%); full/missing membership retained, no expression-based selection |
| LIANA / PROGENy | Commit-bound LIANA CSV and 4620 consensus pairs; dated/hash-bound PROGENy source snapshot; no analysis library installed or executed |
| BioNexus | Actual shared-kernel provenance.sidecar and read-only doctor called; technical provenance only, no Warrant or evidence-claim audit |

The scoped downloaded scRNA release has 100064 cells; do not repeat the paper's broader total as this file's cell count. Raw-count MatrixMarket headers were inspected, not all count entries. Registered NGS workflow run: NONE. Execution description: local Python execution for S1 acquisition/metadata audit; NGS data-understanding skill applied.

## Identity and pathology gates that remain open

1. The publisher Visium patientid field is observed for six sample bundles. scRNA supplies orig.ident, not a dedicated patient key. sample-identity.csv preserves 33 rows: six Visium bundles, 26 scRNA sample keys, one 10x input. Independent patient/sample/physical-section hierarchy still requires review; continue to say six sections, not six verified independent patients.
2. CID4290 (Visium) versus CID4290A (scRNA/GEO) is unresolved; no suffix deletion or automatic merge. Three other Visium sample IDs match the scRNA sample IDs literally; two additional TNBC samples are described by the paper as processed by an independent laboratory. Shared-study/reference dependence is retained.
3. Most invasive-cancer labels are composite (for example invasive cancer + stroma + lymphocytes). Their exact producer meanings must be reviewed before a primary label-code mapping is frozen. Current pathology-label-map.json is PENDING_REVIEW_NOT_FROZEN; no mask or substitute boundary was created. Expression, proportions, clustering, deconvolution and literature cannot choose the boundary.
4. CID4290, CID44971 and CID4535 have 6, 2 and 2 metadata barcodes outside the producer tissue mask. Detailed exclusion candidates are saved; original files were not modified. Region-level spot/UMI eligibility remains PENDING.
5. Publisher filtered .gz files are actually plain text; raw .gz files are gzip. File magic was used after preserving the initial failure. Raw feature tables contain ID/symbol/modality columns while filtered tables are selected symbol-only lists; row-number joins are invalid. The main endpoint continues to require raw-count inputs.
6. Visual registration, physical tissue-region relationships, donor independence, the 10x donor/spot-pathology truth and all S2-S6 biological analyses remain unverified/unexecuted. The four missing current program symbols (MARCHF1, RIGI, TMT1B, WARS1) are recorded as absent exact symbol matches; no aliases were silently invented.

These are open evidence/entry gates, not biological findings. The frozen gene-set identifier coverage passes its technical threshold; this does not pass identity, boundary, statistical or clinical validation gates. S2 must not start automatically.

## Actual usage and retained failures

- Completed primary downloaded payloads: 1568957531 bytes (excludes HTTP overhead; full resumed GEO counted once).
- Extracted archive members: 3357908894 bytes.
- Retained input/resource/source/recovery files: 5485808784 bytes; retained prefix/range files explain additional disk use.
- S1 elapsed wall interval since recorded preflight: 1610.966 seconds. This is observed preparation/acquisition time, not an analysis-runtime forecast.
- Peak process RAM: NOT_MEASURED. Future analysis RAM/runtime: PENDING.
- Direct 10x landing-page HTTP 429 and old LIANA resource-path HTTP 404 are preserved; official input/source paths were subsequently acquired. GEO's interrupted sequential transfer and every resumed range are recorded. The first metadata reader's gzip-suffix error and the Unicode/shell issues are retained in logs/S1-execution-issues.json.

## Key artifacts

- 00_plan/authorization-v1-S1-*.json and v2-NOT_APPROVED-*.json: current user decision, hash bindings and storage gate.
- 02_identity/sample-identity.csv; identity-gate.json; study-design-evidence.json.
- 02_identity/scrna-input-integrity.json; visium-input-integrity.json; visium-integrity-exceptions.json; 10x-input-integrity.json.
- 02_identity/pathology-label-inventory.csv; pathology-label-map.json; primary-program.lock.json and feature mapping.
- manifest/S1-storage-budget.json; S1-source-manifest.json; S1-input-file-index.json; resource-lock.json.
- manifest/S1-bionexus-provenance.sidecar.json; logs/S1-events.jsonl; manifest/scripts/.
- S1-starting-point-assessment.json and manifest/S1-artifact-index.sha256.

BioNexus text-file hashing may normalize CRLF; the exact-byte input index is authoritative for physical downloaded bytes. Hashes provide integrity, not producer authentication or scientific validation. No machine verdict is filled from a policy ceiling.

S1 execution is now stopped. Human review of the identity/pathology gates and an explicit subsequent instruction are required before any S2 work; computation approval never accepts a biological conclusion.
