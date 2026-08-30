# BioNexus Data Governance: Sensitivity Tiers & Egress Policy

BioNexus ships **10 third-party hosted MCP endpoints** (external processors) alongside a
**zero-egress local stdio server**. Whether a researcher can safely hand real data to the
system depends on making that boundary explicit and enforceable. This document defines
the classification vocabulary, the deterministic policy matrix, and the honest limits of
what a policy layer can guarantee.

> **RUO boundary**: BioNexus is Research Use Only. RESTRICTED (PHI / clinical
> diagnostic) data is refused for any external zone unconditionally, and processed
> locally only behind an explicit operator acknowledgement. BioNexus holds no CLIA,
> CAP, IVDR, or 21 CFR Part 11 certification.

---

## 1. Sensitivity Tiers (`SensitivityTier`)

| Tier | Meaning | Examples |
|---|---|---|
| `PUBLIC` | Published or reference data | public GeoJSON datasets, Ensembl IDs, published marker lists |
| `INTERNAL` | Lab-internal but non-identifying research data (default when undeclared) | in-house count matrices, unpublished QC metrics |
| `SENSITIVE` | Proprietary / unpublished / potentially identifying research data | pre-publication cohort genotypes, licensed patient-derived cell line metadata |
| `RESTRICTED` | PHI / clinical diagnostic data | identifiable clinical records, diagnostic VCFs linked to individuals |

Classification is **declaration-driven**: `bionexus data-classify <path> --tier SENSITIVE`.
Undeclared data defaults to `INTERNAL` (usable, but external egress is advisory).

### Heuristic signal cap

A deterministic keyword scan (filename + caller-supplied metadata values) caps a
declared tier at `SENSITIVE` when signals fire. Signals **only restrict** — they never
lower a declared restriction, never raise data to `RESTRICTED`, and cannot detect
de-identified data. Current signals: `patient`, `clinical`, `clinic`, `phi`, `mrn`,
`medical_record`, `medicalrecord`, `diagnosis`, `hospital`, `icd`, `subject_id`, `case_id`.

### Governance sidecar

`classify_dataset` writes `<path>.bionexus-governance.json` binding the decision to the
file's SHA-256 at classification time:

```json
{
  "schema": "bionexus.governance.sidecar/1.0",
  "path": "cohort_counts.h5ad",
  "sha256": "…",
  "declared_tier": "SENSITIVE",
  "effective_tier": "SENSITIVE",
  "signals_detected": [],
  "signal_capped": false,
  "classified_at": "2026-08-30T05:00:00+00:00"
}
```

---

## 2. Egress Zones (`EgressZone`)

| Zone | Meaning | BioNexus endpoints |
|---|---|---|
| `LOCAL` | Zero network egress (stdio, local files) | `bionexus-local-mcp` |
| `ORGANIZATION` | Institution-hosted services | (no defaults; user-registered) |
| `EXTERNAL` | Third-party hosted endpoints (external processors) | see §3 |

---

## 3. Governed Endpoint Inventory

Resolved from `bionexus.registry.yaml` (`mcp_servers.hosted`) — the SSOT for what is an
external processor. All **hosted** endpoints receive query content outside the
organization's trust boundary:

| Endpoint | Category | Zone |
|---|---|---|
| `pubmed` (NCBI PubMed) | literature | EXTERNAL |
| `biorxiv` (bioRxiv / medRxiv) | preprints | EXTERNAL |
| `consensus` (Consensus AI) | literature | EXTERNAL |
| `wiley` (Wiley Online Library) | literature | EXTERNAL |
| `chembl` (ChEMBL) | chemistry | EXTERNAL |
| `c-trials` (ClinicalTrials.gov) | clinical | EXTERNAL |
| `ot` (Open Targets) | target_discovery | EXTERNAL |
| `synapse` (Sage Bionetworks) | data_repository | EXTERNAL |
| `owkin` (Owkin) | precision_medicine | EXTERNAL |
| `biorender` (BioRender) | visualization | EXTERNAL |
| `benchling` (Benchling, disabled placeholder) | lims | EXTERNAL |
| `bionexus-local-mcp` | local fallback (UniProt, Ensembl, gnomAD, PDB, AlphaFold, Reactome, STRING, GEO, GTEx) | **LOCAL** |

Unknown endpoint ids resolve conservatively to `EXTERNAL`, so the restrictive branch of
the policy matrix applies.

---

## 4. Policy Matrix (`check_egress_policy`)

Decisions use the same vocabulary as the intent router: `PERMITTED`,
`DEGRADED_ADVISORY`, `ABSTAIN`. The matrix is deterministic and tested by an L3
eval case (`l3-outcome-egress-policy-007`).

| Tier \ Zone | LOCAL | ORGANIZATION | EXTERNAL |
|---|---|---|---|
| `PUBLIC` | PERMITTED | PERMITTED | PERMITTED |
| `INTERNAL` | PERMITTED | PERMITTED | DEGRADED_ADVISORY |
| `SENSITIVE` | PERMITTED | DEGRADED_ADVISORY | **ABSTAIN** |
| `RESTRICTED` | ABSTAIN (PERMITTED with `allow_restricted_local_ack=True`) | **ABSTAIN (unconditional)** | **ABSTAIN (unconditional)** |

```bash
# Classify once, at data arrival
bionexus data-classify cohort_counts.h5ad --tier SENSITIVE

# Gate every query that would carry data fragments outward
bionexus policy check --tier SENSITIVE --endpoint pubmed        # exit 1 (ABSTAIN)
bionexus policy check --tier SENSITIVE --endpoint local         # exit 0 (PERMITTED)
bionexus policy check --tier RESTRICTED --endpoint local \
    --ack-restricted-local                                      # exit 0, RUO limitations attached
```

Agents should call `bionexus.governance.assert_query_permitted(tier, endpoint)` before
issuing any hosted-endpoint query that embeds data-derived content (sequences, variants,
cohort metadata). Pure keyword lookups over published literature with `PUBLIC` inputs
need no gate.

---

## 5. Honest Limits

1. **A guardrail, not DLP.** The policy gates what agents and the MCP layer send; it
   cannot control what a human pastes into a chat box.
2. **Heuristics cap, never classify.** The keyword scan can only restrict a permissive
   declaration; it cannot certify that data is de-identified.
3. **Declaration is load-bearing.** `INTERNAL` defaults are advisory precisely because
   the system cannot know data provenance; declarations written into sidecars are the
   durable record.
4. **RUO only.** RESTRICTED-data handling here is about not leaking PHI *through
   BioNexus*; it is not, and must never be presented as, clinical-grade processing.
