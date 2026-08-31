# BNS-020: BioNexus Conformance Test Kit (BCTK) Development Diagnostic Standard

**Status**: Development / Not Certifiable | **Version**: 0.2-trust-reset | **Supersedes**: none  
**Applies to**: `src/bionexus/bctk/`, `bctk` CLI, `bionexus conformance`, all third-party agents, plugins, workflows, and analysis packages.

---

## 1. Executive Summary & Ecosystem Philosophy

The **BioNexus Conformance Test Kit (BCTK)** is currently a target-bound
development diagnostic for scientific AI agents, plugins, computational workflows,
and analysis tools. It does not issue certification or endorsement.

Drawing inspiration from the **OpenTelemetry (OTel) Compliance Model**, BioNexus explicitly decouples **compliance testing** from **internal tool usage**:

> BioNexus does not require third-party tools to use its pipelines. During the
> Scientific Trust Reset, BCTK scores are internal diagnostics only. A third party
> MUST NOT claim BioNexus conformance from a BCTK run.

Any third-party Agent, Plugin, Tool, Nextflow Workflow, Python Package, or MCP Server can test compliance by running:
```bash
bctk test <target>
# or
bionexus conformance test <target>
```

---

## 2. The 8 Normative Conformance Dimensions

BCTK evaluates 8 orthogonal scientific dimensions:

```
+-----------------------------------------------------------------------------------+
|                     BioNexus Conformance Dimensions (BCTK)                        |
+-----------------------------------+-----------------------------------------------+
| 1. BIOLOGICAL SEMANTICS           | 2. INPUT STATE HONESTY                        |
|    - Gene identifier hygiene      |    - Non-negative counts for discrete models  |
|    - Discrete counts vs log scale |    - Non-integer float checks                 |
|    - Physical spatial coordinates |    - Statistical sample size thresholds       |
+-----------------------------------+-----------------------------------------------+
| 3. BACKEND IDENTITY (BN-F010)     | 4. PROVENANCE (W3C PROV-O)                    |
|    - Zero silent substitution     |    - Machine-readable activity sidecars       |
|    - Distribution package witness |    - SHA-256 entity hashes                    |
|    - Symbol entrypoint resolution |    - Environment & dependency capture         |
+-----------------------------------+-----------------------------------------------+
| 5. CLAIM WARRANT (BNS-017)        | 6. ABSTENTION (BNS-005)                       |
|    - Evidence ceiling clamping    |    - Deterministic precondition refusal       |
|    - Cell-type hallucination gate |    - Structured EvidenceCard refusal payload  |
|    - Multiple testing adjustment  |    - Zero silent fallback to toy proxies      |
+-----------------------------------+-----------------------------------------------+
| 7. FAILURE HANDLING (BNS-014)     | 8. CROSS-HOST CONSISTENCY (BNS-008)           |
|    - BioFailureBench trap defense |    - Host-agnostic ABI compliance             |
|    - Canonical failure taxonomy   |    - Deterministic RNG under fixed seed       |
|    - Actionable remediation       |    - Headless CI/CD automation readiness      |
+-----------------------------------+-----------------------------------------------+
```

---

## 3. Normative Rule Catalog (Summary)

| Rule ID | Dimension | Title | Severity | Normative Ref |
| :--- | :--- | :--- | :---: | :--- |
| `BCTK-SEM-001` | Biological Semantics | Gene Identifier Hygiene | HIGH | BNS-002 §2 |
| `BCTK-SEM-002` | Biological Semantics | Expression Matrix Scale Semantics | CRITICAL | BNS-002 §3 (BNS-II-001) |
| `BCTK-SEM-003` | Biological Semantics | Spatial Coordinate Space Justification | CRITICAL | BNS-002 §4 (BNS-II-005) |
| `BCTK-SEM-004` | Biological Semantics | Species Reference Genome Consistency | MEDIUM | BNS-001 §4 |
| `BCTK-INP-001` | Input State Honesty | Non-Negative Count Invariant | CRITICAL | BNS-002 §3.1 (BN-F001) |
| `BCTK-INP-002` | Input State Honesty | Non-Integer Count Model Invariant | CRITICAL | BNS-002 §3.2 (BN-F001) |
| `BCTK-INP-003` | Input State Honesty | Sample Size Honesty (n >= 3) | HIGH | BNS-002 §5 (BN-F006) |
| `BCTK-INP-004` | Input State Honesty | Input Data Preflight Audit | HIGH | BNS-013 §2 |
| `BCTK-BAK-001` | Backend Identity | Zero Silent Substitution (Anti-Masquerading) | CRITICAL | BNS-003 §3 (BN-F010) |
| `BCTK-BAK-002` | Backend Identity | Backend Version Contract Verification | HIGH | BNS-003 §4 |
| `BCTK-BAK-003` | Backend Identity | Entry Point Symbol Resolution | CRITICAL | BNS-003 §4.1 |
| `BCTK-BAK-004` | Backend Identity | Cryptographic Execution Fingerprinting | HIGH | BNS-003 §5 |
| `BCTK-PRV-001` | Provenance | W3C PROV-O Activity Sidecars | HIGH | BNS-006 §2 |
| `BCTK-PRV-002` | Provenance | SHA-256 Input/Output Integrity Binding | HIGH | BNS-006 §3 |
| `BCTK-PRV-003` | Provenance | Environment & Software Capture | MEDIUM | BNS-006 §4 |
| `BCTK-PRV-004` | Provenance | Standards Interoperability (RO-Crate / BCO) | MEDIUM | BNS-016 §2 |
| `BCTK-WAR-001` | Claim Warrant | Evidence-Capped Claim Ceilings | CRITICAL | BNS-004 §3 (BNS-017) |
| `BCTK-WAR-002` | Claim Warrant | Cell-Type Hallucination Defense | CRITICAL | BNS-001 §6 (BN-F005) |
| `BCTK-WAR-003` | Claim Warrant | Multiple Testing Correction Honesty | HIGH | BNS-004 §2.4 (BN-F002) |
| `BCTK-WAR-004` | Claim Warrant | Regulatory / GxP Compliance Non-Overclaim | HIGH | BNS-001 §6.3 |
| `BCTK-ABS-001` | Abstention | Deterministic Precondition Refusal | CRITICAL | BNS-005 §2 |
| `BCTK-ABS-002` | Abstention | Structured EvidenceCard Refusal Payload | HIGH | BNS-005 §3 |
| `BCTK-ABS-003` | Abstention | Zero Silent Fallback to Toy Proxies | CRITICAL | BNS-005 §4 |
| `BCTK-FAI-001` | Failure Handling | BioFailureBench Trap Defense | CRITICAL | BNS-014 §2 |
| `BCTK-FAI-002` | Failure Handling | Failure Taxonomy Linkage | HIGH | BNS-011 §2 |
| `BCTK-FAI-003` | Failure Handling | Actionable Remediation Prescription | MEDIUM | BNS-011 §3 |
| `BCTK-HST-001` | Cross-Host Consistency | Host-Agnostic Interface Compliance | HIGH | BNS-008 §2 |
| `BCTK-HST-002` | Cross-Host Consistency | Deterministic Execution Under Fixed Seed | HIGH | BNS-008 §3 |
| `BCTK-HST-003` | Cross-Host Consistency | Headless & Non-Interactive CI Compatibility | MEDIUM | BNS-008 §4 |

---

## 4. Suspended Tier Mapping

The historical GOLD/SILVER/BRONZE thresholds are retained only as an unverified
`diagnostic_tier` for migration and calibration research. Every report MUST set
`conformance_tier=NOT_ASSESSED`, `badge_eligible=false`, and
`trust_decision=NOT_ASSESSED` until an independent certification authority and
target-bound evidence protocol are operational.

| Diagnostic mapping | Minimum Overall Score | Backend Identity (BN-F010) | Abstention (BNS-005) | Critical Failures Allowed |
| :--- | :---: | :---: | :---: | :---: |
| **GOLD** | **>= 95.0%** | **100% PASS** | **100% PASS** | **0** |
| **SILVER** | **>= 85.0%** | **100% PASS** | **100% PASS** | **0** |
| **BRONZE** | **>= 70.0%** | Any non-masquerading state | **>= 80% PASS** | **0** |
| **NON_CONFORMANT** | < 70.0% | Any BN-F010 violation | < 80% | >= 1 |

---

## 5. Evidence Binding, Signature, and Revocation

Every diagnostic report binds the sorted target file bytes into
`target_content_sha256` and hashes the complete report payload. The report hash is
an integrity checksum, not a signature or attestation.

`bctk badge` and `--badge` MUST fail closed. Future certification evidence MUST use
`bionexus.evidence-attestation.v1`: Ed25519 over a canonical payload containing the
artifact SHA-256, an explicitly trusted key, an expiry interval, and signed
revocation checks. No default BioNexus self-signing key is trusted. These controls
are research integrity mechanisms and do not claim regulatory electronic-signature
compliance.

BNS-022 additionally requires institutional separation: the SSC may define the
technical conformance specification but may not assess a named implementation;
commercial operators may not select assessors or issue certificates; and only a
recognized independent conformity assessment body may issue, suspend, or revoke
a future certificate. Cryptographic validity alone does not satisfy these
governance and impartiality gates.

## 6. Independently adoptable protocol profiles

- **BNS-CT-001** BCTK MUST publish profile results for `BNS-Core`,
  `BNS-Warrant`, `BNS-Provenance`, `BNS-Agent`, `BNS-Validation`, and
  `BNS-Full` so an implementation can adopt a bounded contract surface.
- **BNS-CT-002** A mandatory dimension that is missing, skipped,
  `NOT_APPLICABLE`, or `NOT_ASSESSED` MUST make its profile `NOT_ASSESSED`.
- **BNS-CT-003** A failed mandatory dimension MUST make its profile fail; a
  score from other dimensions MUST NOT average away the failure.
- **BNS-CT-004** `BNS-Full` MUST be deterministically derived from the component
  profiles and MUST NOT pass while any component is failed or unassessed.
- **BNS-CT-005** Profile results are technical diagnostics and MUST retain
  `certification_effect=NONE` while BNS-GV-020 is unmet.
