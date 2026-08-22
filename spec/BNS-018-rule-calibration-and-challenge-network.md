# BNS-018: Scientific Rule Calibration & Challenge Network

**Status**: Development / Unverified | **Version**: 1.1-trust-reset | **Supersedes**: none
**Applies to**: `src/bionexus/rule_calibration.py`, `src/bionexus/empirical_warrant.py`, `src/bionexus/annotation_evidence.py`, `src/bionexus/rule_provenance.py`, `src/bionexus/data/rule_registry.json`, `src/bionexus/data/empirical_calibration_registry.json`
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

---

## 1. Purpose & Strategic Vision

BioNexus enforces scientific integrity invariants and epistemic warrant constraints across computational biology. However, scientific rules must never remain static, author-dictated heuristics.

The long-term objective is a living, community-governed and empirically calibrated
knowledge base. The packaged registry does not yet meet that objective: its review,
calibration, and external-validation states are `NOT_ASSESSED`.

**BNS-018** specifies:
1. The **Calibrated Rule Schema**, decomposing every rule into formal propositions, applicable regimes, counterexamples, multi-platform calibrations, sensitivity analyses, and peer reviewer attestations.
2. The **Scientific Challenge Network**, providing a deterministic, peer-reviewed protocol for researchers worldwide to submit empirical counterexamples, challenge flawed statistical assumptions, and calibrate platform-specific operating bounds.
3. The **Federation & Local Overlay Protocol**, enabling research institutions to inherit upstream community rules while maintaining cryptographically signed local calibrations.

---

## 2. Calibrated Rule Architecture (Normative Schema)

- **BNS-RC-001 (Universal Calibrated Rule Structure)**:
  Every scientific rule schema MUST support the following 12 dimensions. Missing
  dimensions MUST remain empty and explicitly `NOT_ASSESSED`; they MUST NOT be
  populated with illustrative or unverified evidence in the production registry:
  1. `scientific_proposition`: Formal theoretical statement, predicate logic, underlying biological/statistical assumptions, and theoretical framework.
  2. `epistemic_class`: Ontological category (`EXECUTION_INVARIANT`, `DATA_INTEGRITY_INVARIANT`, `WARRANT_CONSTRAINT`, `CALIBRATED_THRESHOLD`, `HEURISTIC_DETECTOR`, `POLICY_DEFAULT`).
  3. `supporting_evidence`: Verifiable citations, DOIs, and benchmark dataset references.
  4. `contradictory_evidence`: Dissenting literature, boundary contestations, and negative controls.
  5. `applicable_regimes`: Declared operational regimes (platforms, sample sizes, design pairedness, tissue types).
  6. `known_counterexamples`: Explicit edge cases where standard assumptions break down, paired with mandatory mitigation strategies.
  7. `dataset_calibration`: Empirical parameter distributions, metrics, and confidence intervals measured across canonical reference cohorts (e.g. Tabula Sapiens, PBMC68k, TCGA).
  8. `platform_calibration`: Instrument- and chemistry-specific parameter tunings (e.g. 10x v2 vs v3 vs Flex, Visium HD vs standard, Xenium, MERSCOPE).
  9. `sensitivity_analysis`: Elasticity of scientific conclusions and warrant status to parameter perturbations, identifying cliff-edge transition risks.
  10. `reviewers`: References to verified `bionexus.evidence-attestation.v1` records. Names, affiliations, ORCIDs, or bare hashes alone MUST NOT count as endorsement.
  11. `version_history`: Semantic changelog tracking epistemic rationale across version transitions.
  12. `consensus_state`: Formal community consensus level (`ESTABLISHED`, `STRONG`, `EMERGING`, `CONTESTED`, `DEPRECATED`).

---

## 3. Scientific Challenge Network Protocol

- **BNS-RC-002 (Challenge Submission)**:
  Any researcher or computational biologist MAY submit a formal Challenge against any active rule in the knowledge base. A valid challenge proposal MUST specify:
  - `target_rule_id`: Identifier of the rule being challenged.
  - `challenger_identity`: Verifiable researcher identity (ORCID, institution, or PGP key ID).
  - `challenge_type`: Closed enum: `EMPIRICAL_COUNTEREXAMPLE`, `BENCHMARK_DISSENT`, `REGIME_BOUNDARY_VIOLATION`, `PARAMETER_DRIFT`, `MATHEMATICAL_FLAW`, `PLATFORM_INCOMPATIBILITY`.
  - `title` & `description`: Detailed scientific rationale.
  - `empirical_evidence_refs`: Supporting literature DOIs or dataset accessions.
  - `reproduction_script_sha256`: Cryptographic hash of the executable reproduction workflow proving the claim.

- **BNS-RC-003 (Adjudication & Consensus Lifecycle)**:
  Challenges undergo formal peer review across the Challenge Network. The lifecycle states are:
  1. `PROPOSED`: Challenge registered in the decentralized ledger.
  2. `UNDER_REVIEW`: Review votes may be recorded, but unverified votes do not count toward consensus.
  3. `ACCEPTED_AMENDMENT`: Challenge ratified by at least three reviewer votes, each linked to a verified, unexpired, unrevoked, artifact-bound evidence attestation; the target rule is updated with new bounds or exceptions.
  4. `REGIME_SPLIT`: Challenge demonstrates that the rule holds for some assays but not others; the rule is partitioned into distinct sub-regimes (e.g. droplet vs spatial vs imaging).
  5. `REJECTED_REFUTED`: Challenge is empirically refuted or demonstrated to be non-reproducible.
  6. `DEPRECATED`: The underlying premise is superseded by newer statistical theory.

- **BNS-RC-004 (Fail-Closed Integrity & Zero Silent Drift)**:
  Rule calibrations MUST be immutable at runtime and verifiable against cryptographic SHA-256 digests. Modifying local rules without recording a formal calibration or local overlay MUST be refused by the registry compiler (`BNS-EF-002`).

- **BNS-RC-004A (Signature and Revocation)**:
  An endorsement, calibration approval, challenge resolution, or conformance result
  MUST bind its exact artifact SHA-256 into `bionexus.evidence-attestation.v1`, be
  signed with Ed25519 by a key already present in an explicit trust registry, and
  pass expiry and signed-revocation checks. A self-generated key, bare digest,
  missing artifact, or unverifiable identity yields `NOT_ASSESSED`, never
  `VERIFIED`. This is a research integrity contract, not a regulatory electronic
  signature claim.

---

## 4. Platform & Regime Calibration Rules

- **BNS-RC-005 (Regime Boundary Verification)**:
  Before applying an epistemic rule or issuing a warrant gate, the engine MUST verify whether the experimental setup (assay platform, sample size, library chemistry) falls within the declared `applicable_regimes`. If the assay is outside all declared regimes, the engine MUST issue a regime boundary warning and clamp the warrant ceiling at `PRELIMINARY`.

- **BNS-RC-006 (Platform-Specific Threshold Resolution)**:
  Where a rule specifies platform-dependent thresholds (e.g. spot density for Visium HD vs standard Visium, or sequencing depth for Smart-seq2 vs 10x Chromium), the engine MUST resolve and apply the platform-specific calibration rather than a single hardcoded global constant.

- **BNS-RC-007 (Institutional Overlay & Federation)**:
  Labs and pharmaceutical research centers MAY define private or domain-specific calibration overlays (`lab_overlay.json`). Overlays MUST explicitly cite the upstream community rule ID and record the local PI's cryptographic attestation.

---

## 5. Executable Empirical Warrant Resolution

- **BNS-RC-008 (Five-Dimension Profile Identity)**:
  A numeric threshold used for a scientific warrant MUST be resolved against an
  explicit profile containing `tissue`, `platform`, `reference`, `task`, and
  `evidence_source`. The runtime MUST NOT treat the same numeric score from two
  different mappers, marker panels, references, or tasks as exchangeable unless
  an approved profile explicitly declares that shared regime.

- **BNS-RC-009 (No Universal Numeric Fallback)**:
  If required calibration context is missing, no profile covers the context, the
  only matching profile is `CANDIDATE` or `LEGACY_UNCALIBRATED`, or equally
  specific approved profiles conflict, the resolver MUST return an explicit
  unresolved status. It MUST NOT apply a legacy global threshold, and the
  unresolved metric MUST NOT contribute to a `SUPPORTED` or stronger warrant.

- **BNS-RC-010 (Reference-Domain Mismatch)**:
  A reference-mapping score MUST NOT count as independent identity support when
  the target and reference domains are declared mismatched. A high score under
  domain mismatch MAY be retained as a diagnostic observation, but it MUST NOT
  be interpreted using the in-domain threshold.

- **BNS-RC-011 (Rare, Open-Set, and Continuous States)**:
  A rare or open-set population MUST produce `ABSTAIN` rather than a forced
  nearest-known label, regardless of its top score. A declared continuous state
  geometry MUST cap a discrete identity warrant at `TENTATIVE` unless a separate
  state-aware validation contract is satisfied.

- **BNS-RC-012 (Candidate Fit Is Not Activation)**:
  Automated fitting MUST produce a `CANDIDATE` profile only. An `APPROVED`
  profile MUST include held-out empirical evidence with a source SHA-256 and an
  accountable reviewer approval record. Runtime resolution MUST ignore
  unapproved profiles for positive warrants.

- **BNS-RC-013 (Calibration Receipt)**:
  A threshold fit MUST record the declared target operating criterion, confidence
  method, selected calibration and validation counts, held-out performance, and
  a deterministic hash of the labelled observations. The receipt is
  reproducibility metadata and MUST NOT be represented as a regulatory
  electronic signature or as independent scientific validation by itself.

- **BNS-RC-014 (Decision Provenance)**:
  Every resolved metric comparison MUST expose the calibration registry digest,
  profile identifier, profile version, profile digest, comparison direction,
  threshold, and declared context. Every unresolved comparison MUST expose the
  machine-readable failure status and MUST record that no fallback was used.
