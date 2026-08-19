# Scientific Review Protocol

## BioNexus Reliability Framework — Scientific Invariant Review

**Version:** 1.0  
**Date:** 2026-08-18  
**Project:** bionexus-reliability v0.10.0

---

## 1. Review Objectives

This review evaluates the scientific validity of all threshold values, decision rules, and detection patterns encoded in BioNexus's reliability framework. These invariants govern:

- When analyses must be refused (e.g., insufficient replicates)
- When claims must be blocked (e.g., causal language detection)
- When evidence levels must be capped (e.g., missing FDR correction)
- How spatial and annotation conclusions are graded

The review ensures these values are:
1. **Scientifically justified** — grounded in statistical theory or empirical evidence
2. **Appropriately conservative** — fail-closed by default, never waving through invalid results
3. **Transparent** — published in source code with clear rationale
4. **Sensitive to context** — thresholds appropriate for the data types and methods involved

---

## 2. Reviewer Roles and Expertise

### Reviewer 1: Single-Cell Computational Researcher
- **Background:** Practical experience with scRNA-seq analysis pipelines, pseudobulk DE workflows, and common failure modes in single-cell analysis
- **Assigned Cases:** Pseudoreplication detection (INV-001, INV-014), causal DE overclaim patterns (INV-010)
- **Key Questions:**
  - Is the replicate threshold (≥2) sufficient for dispersion estimation in typical experimental designs?
  - Are the causal language patterns comprehensive enough to catch common overclaims?
  - Does the pseudoreplication detection logic correctly identify the dangerous cases?

### Reviewer 2: Spatial Transcriptomics Researcher
- **Background:** Experience with MERFISH, Xenium, Visium, or similar spatial platforms; understanding of spatial statistics and confound structure
- **Assigned Cases:** Spatial robustness ladder (INV-011, INV-012, INV-013), spatial spots minimum (INV-002, INV-017)
- **Key Questions:**
  - Are the 12 canonical alternatives comprehensive for current spatial technologies?
  - Is the core control set (cell_size, transcript_density, segmentation_uncertainty) appropriate?
  - Is 5 spots a reasonable minimum for graph construction?
  - Does the ROBUST/SUPPORTED/FRAGILE/ABSTAIN ladder match the evidentiary standards of the field?

### Reviewer 3: Biostatistics / Computational Methods Researcher
- **Background:** Statistical methodology, multiple testing correction, replication standards, and annotation validation
- **Assigned Cases:** FDR threshold (INV-003), annotation evidence thresholds (INV-004 through INV-008, INV-016), cell-type hallucination patterns (INV-015)
- **Key Questions:**
  - Is FDR α=0.05 appropriate as a hard floor, or should it be capability-dependent?
  - Are the annotation thresholds (0.60 marker consistency, 0.20 negative violation, 0.70 reference mapping, 0.80 cross-method, 0.15 doublet rate) well-calibrated?
  - Does the SUPPORTED/TENTATIVE/ABSTAIN ladder correctly implement evidentiary hierarchy?
  - Are the cell-type hallucination patterns sufficiently specific to avoid false positives?

---

## 3. Review Process

### Phase 1: Independent Review (Week 1–2)
Each reviewer independently examines their assigned invariants:
1. Read the source code and rationale for each invariant
2. Evaluate scientific justification against current literature
3. Assess sensitivity (high/medium/low) and whether it's correctly classified
4. Record verdict: **APPROVE**, **REQUEST_CHANGE**, or **FLAG_CONCERN**
5. Provide written justification for each verdict

### Phase 2: Cross-Review (Week 3)
- Reviewers exchange comments on flagged invariants
- Disagreements are documented in `SCIENTIFIC_REVIEW.json` under `disagreements`
- Each reviewer may respond to concerns raised about their assigned cases

### Phase 3: Consensus Meeting (Week 4)
- All reviewers convene to resolve disagreements
- Final verdicts recorded: **APPROVED**, **REVISED**, or **DEFERRED**
- Any approved changes are documented in `changes_made`

---

## 4. Record Format

### Invariant Review Entry
```json
{
  "invariant_id": "INV-001",
  "reviewer_id": "reviewer-1",
  "review_date": "2026-08-XX",
  "verdict": "APPROVE | REQUEST_CHANGE | FLAG_CONCERN",
  "justification": "Written explanation of the scientific reasoning",
  "literature_support": ["DOI or citation if applicable"],
  "sensitivity_assessment": "high | medium | low",
  "recommended_value": null,
  "notes": "Additional context or concerns"
}
```

### Disagreement Record
```json
{
  "disagreement_id": "DIS-001",
  "invariant_id": "INV-XXX",
  "reviewers_involved": ["reviewer-1", "reviewer-3"],
  "nature_of_disagreement": "Description of the scientific disagreement",
  "resolution": "How the disagreement was resolved",
  "final_decision": "APPROVED | REVISED | DEFERRED"
}
```

---

## 5. Disagreement Resolution Mechanism

1. **Documentation:** All disagreements are recorded with full scientific reasoning from each side
2. **Evidence Standard:** Resolution requires citation of empirical evidence, statistical theory, or established best practices
3. **Escalation:** If reviewers cannot reach consensus, the invariant is marked DEFERRED with a note explaining the unresolved scientific question
4. **Conservative Default:** While deferred, the existing threshold remains in effect (fail-closed principle)
5. **External Consultation:** For critical invariants (sensitivity=high), external domain experts may be consulted

---

## 6. Timeline

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| Framework Creation | Day 0 | This protocol + INVARIANTS_CATALOG.json |
| Independent Review | Weeks 1–2 | Per-reviewer verdicts in SCIENTIFIC_REVIEW.json |
| Cross-Review | Week 3 | Disagreement documentation |
| Consensus Meeting | Week 4 | Final verdicts, change log |
| Implementation | Weeks 5–6 | Code changes (if any) with version bump |

---

## 7. Invariant Catalog Summary

The following 17 invariants require review:

| ID | Name | Source File | Sensitivity |
|----|------|-------------|-------------|
| INV-001 | pseudoreplication_threshold | capabilities.py | high |
| INV-002 | spatial_spots_minimum | capabilities.py | medium |
| INV-003 | fdr_alpha_threshold | capabilities.py | high |
| INV-004 | annotation_marker_consistency_threshold | annotation_evidence.py | medium |
| INV-005 | annotation_negative_marker_violation_max | annotation_evidence.py | medium |
| INV-006 | annotation_reference_mapping_min | annotation_evidence.py | high |
| INV-007 | annotation_cross_method_agreement_min | annotation_evidence.py | medium |
| INV-008 | annotation_doublet_rate_max | annotation_evidence.py | medium |
| INV-009 | causal_language_pattern | verification.py | high |
| INV-010 | causal_de_overclaim_patterns | claim_checker.py | high |
| INV-011 | spatial_robustness_ladder | spatial_inference.py | high |
| INV-012 | spatial_core_controls | spatial_inference.py | high |
| INV-013 | spatial_canonical_alternatives | spatial_inference.py | medium |
| INV-014 | pseudoreplication_detection_pattern | analysis_audit.py | high |
| INV-015 | cell_type_hallucination_patterns | claim_checker.py | high |
| INV-016 | annotation_verdict_ladder | annotation_evidence.py | medium |
| INV-017 | spatial_coordinate_audit_min_spots | integrity.py | medium |

---

## 8. Change Control

Any approved changes to invariants require:
1. Update to the source code with the new threshold/pattern
2. Version bump in `pyproject.toml` (minor or major, depending on impact)
3. Entry in CHANGELOG.md describing the change and scientific rationale
4. Re-run of all affected tests to verify no regressions
5. Update to INVARIANTS_CATALOG.json with new value and review status = "approved"

---

## 9. Contact and Governance

- **Review Coordinator:** [TO BE ASSIGNED]
- **Final Arbiter:** [TO BE ASSIGNED — typically Principal Investigator or Scientific Advisory Board]
- **Review Records Maintained In:** `review/SCIENTIFIC_REVIEW.json`
- **Invariant Catalog:** `review/INVARIANTS_CATALOG.json`

---

*This protocol ensures that BioNexus's scientific guardrails are themselves subject to scientific scrutiny, maintaining the integrity of the fail-closed philosophy.*
