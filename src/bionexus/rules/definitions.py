"""
BioNexus Canonical Scientific Rule Research Objects (BNS-019).

Defines peer-review-grade research objects for core scientific audit rules.
Each object details applicability, exceptions, expected benefits, false rejection
risks, scholarly citations, semantic change rationales, and dual-track truth semantics.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Dict, Optional

from bionexus.rule_classification import (
    EnforcementLevel,
    EpistemicKind,
    RuleCategory,
)
from bionexus.rule_provenance import ConsensusLevel
from bionexus.rules.research_object import (
    CitationRef,
    RuleDualTrackSemantics,
    ScientificRuleObject,
)

CANONICAL_SCIENTIFIC_RULES: Dict[str, ScientificRuleObject] = {
    "BFA-001": ScientificRuleObject(
        rule_id="BFA-001",
        name="Cell-Level Pseudoreplication in Cross-Condition Differential Expression",
        version="2.1.0",
        category=RuleCategory.WARRANT_EPISTEMIC,
        epistemic_kind=EpistemicKind.WARRANT_CONSTRAINT,
        enforcement_level=EnforcementLevel.ENFORCED,
        consensus=ConsensusLevel.ESTABLISHED,
        applicability_conditions=[
            "Comparative differential expression between multi-individual experimental groups (e.g. Disease vs Healthy, Treated vs Untreated).",
            "Single-cell or single-nucleus RNA-seq data where individual cells are sampled from biological individuals (donors/animals).",
            "Population-level inference claiming biological differences that generalize across individuals.",
        ],
        exceptions=[
            "Pure technical batch benchmark evaluating cell-cell technical noise without biological population claims.",
            "Clonally derived homogeneous isogenic cell lines under identical culture conditions with zero between-individual biological variance.",
            "Marker gene identification within a single cluster/sample solely for preliminary cell-type clustering diagnostics (rank_genes_groups), with explicit disclaimer prohibiting cross-group DEG claims.",
        ],
        expected_benefit=(
            "Eliminates catastrophic false discovery rate (FDR) inflation (often >30-70% empirical false discoveries) "
            "caused by treating dependent single cells as independent statistical degrees of freedom, preventing "
            "unreproducible target discoveries."
        ),
        false_rejection_risk=(
            "If applied rigidly without checking aggregation state, may falsely reject correctly aggregated pseudobulk "
            "analyses where single-cell rank_genes_groups was merely retained for visualization or within-sample cell typing."
        ),
        literature_citations=[
            CitationRef(
                author="Squair, J. W. et al.",
                year=2021,
                title="Confronting false discoveries in single-cell differential expression",
                journal="Nature Communications",
                doi="10.1038/s41467-021-25960-2",
                evidence_quote=(
                    "Methods that fail to account for cell-level dependence or sample-level biological replicate structure "
                    "suffer from severe false-discovery inflation, frequently exceeding 50% even in null permutations."
                ),
                relevance="Seminal empirical demonstration of pseudoreplication in single-cell genomics.",
            ),
            CitationRef(
                author="Lun, A. T. L. & Marioni, J. C.",
                year=2017,
                title="Overcoming confounding plate effects in differential expression analyses of single-cell RNA-seq data",
                journal="Biostatistics",
                doi="10.1093/biostatistics/kxw055",
                evidence_quote="Pseudobulk aggregation to the sample/donor level correctly preserves the inferential error rate.",
                relevance="Foundational mathematical proof of pseudobulk aggregation validity.",
            ),
            CitationRef(
                author="Crowell, H. L. et al.",
                year=2020,
                title="muscat detects subpopulation-specific state transitions from multi-sample multi-condition single-cell transcriptomics data",
                journal="Nature Communications",
                doi="10.1038/s41467-020-19894-4",
                evidence_quote="Aggregation of counts by cluster and biological sample yields optimal balance of sensitivity and FDR control.",
                relevance="Validation of sample-level aggregation across diverse scRNA platforms.",
            ),
        ],
        change_rationale=(
            "Upgraded from a static syntax check on rank_genes_groups calls to an epistemic boundary engine: "
            "distinguishes between harmless exploratory clustering diagnostics and invalid population-level cross-condition claims."
        ),
        dual_track_semantics=RuleDualTrackSemantics(
            rule_flag_meaning="Analysis script or result table used single cells as independent statistical units across experimental groups.",
            expert_flaw_meaning="The statistical test degrees of freedom were artificially inflated by thousands of cells, generating invalid p-values that mistake donor-specific individuality for condition effects.",
            harmless_exception_context="The analysis was performed for exploratory within-sample clustering or preliminary cell-type label suggestion with no cross-condition population claim asserted.",
        ),
        aliases=["min_replicates", "pseudoreplication", "cell_level_de"],
    ),
    "BFA-001b": ScientificRuleObject(
        rule_id="BFA-001b",
        name="Small Biological Replicate Cohort (N=2) Boundary & Epistemic Downscoping",
        version="2.0.0",
        category=RuleCategory.WARRANT_EPISTEMIC,
        epistemic_kind=EpistemicKind.WARRANT_CONSTRAINT,
        enforcement_level=EnforcementLevel.ADVISORY,
        consensus=ConsensusLevel.ESTABLISHED,
        applicability_conditions=[
            "Comparative transcriptomics with N=2 biological replicates in one or more conditions.",
            "Studies attempting negative-binomial dispersion estimation or population-level generalizability claims.",
        ],
        exceptions=[
            "Exploratory pilot investigations with explicit 'EXPLORATORY_COHORT' framing and honest disclosure of fragile sample power.",
            "Deterministic or massive monogenic knockout effects (|log2FC| >= 4.0) where between-donor biological variance is eclipsed by effect magnitude.",
            "Ultra-rare clinical punch biopsies or scarce patient cohorts where N >= 3 is physically impossible, accompanied by orthogonal qPCR/proteomic validation.",
        ],
        expected_benefit=(
            "Prevents premature promotion of fragile N=2 discoveries to universal clinical or diagnostic biomarkers, "
            "while avoiding dogmatic outright rejection of precious exploratory pilot studies."
        ),
        false_rejection_risk=(
            "Treating N >= 3 as a blunt universal blocker destroys valid exploratory rare-disease research and early-stage "
            "functional drug screens where N=2 is scientifically legitimate under bounded claims."
        ),
        literature_citations=[
            CitationRef(
                author="Schurch, N. J. et al.",
                year=2016,
                title="How many biological replicates are needed in an RNA-seq experiment and which differential expression tool should you use?",
                journal="RNA",
                doi="10.1261/rna.053959.115",
                evidence_quote="At N=2, all methods lack power to reliably estimate dispersion; at least three replicates are recommended for modest fold changes, while strong effects remain identifiable.",
                relevance="Benchmark of sample size requirements across biological effect sizes.",
            ),
            CitationRef(
                author="Love, M. I., Huber, W. & Anders, S.",
                year=2014,
                title="Moderated estimation of fold change and dispersion for RNA-seq data with DESeq2",
                journal="Genome Biology",
                doi="10.1186/s13059-014-0550-8",
                evidence_quote="Empirical Bayes shrinkage allows estimation with small N, but degrees of freedom remain constrained.",
                relevance="Statistical mechanics of dispersion shrinkage with low sample sizes.",
            ),
        ],
        change_rationale=(
            "Replaced rigid N >= 3 blocking with the Context-Conditioned Epistemic Ladder: N=2 is permitted with bounded "
            "exploratory authorization (EXPLORATORY_COHORT) and clear prohibition of universal causal claims."
        ),
        dual_track_semantics=RuleDualTrackSemantics(
            rule_flag_meaning="Condition has only N=2 biological donors/replicates, presenting limited statistical power and fragile dispersion estimation.",
            expert_flaw_meaning="Attempting to assert robust population-level universality or clinical biomarker status when biological dispersion cannot be reliably identified from N=2.",
            harmless_exception_context="Results are explicitly scoped as within-cohort exploratory candidates with planned orthogonal validation and strong effect sizes.",
        ),
        aliases=["borderline_replicates", "n2_exploratory_regime"],
    ),
    "BFA-002": ScientificRuleObject(
        rule_id="BFA-002",
        name="Raw Integer Count Matrix Integrity for Negative Binomial Modeling",
        version="2.1.0",
        category=RuleCategory.INVARIANT_INTEGRITY,
        epistemic_kind=EpistemicKind.DATA_INTEGRITY_INVARIANT,
        enforcement_level=EnforcementLevel.ENFORCED,
        consensus=ConsensusLevel.ESTABLISHED,
        applicability_conditions=[
            "Statistical modeling tools assuming a discrete count likelihood (e.g. DESeq2, EdgeR, negative binomial GLMs).",
            "Input matrices passed to pseudobulk aggregation and dispersion fitting routines.",
        ],
        exceptions=[
            "Linear modeling frameworks that explicitly operate on log-transformed, variance-stabilized continuous values (e.g. limma-trend, voom with logCPM).",
            "Machine learning clustering or dimensionality reduction pipelines operating on log1p normalized expression.",
        ],
        expected_benefit=(
            "Guarantees that discrete count distributional assumptions of negative binomial likelihoods are satisfied, "
            "preventing severe parameter distortion and erroneous dispersion convergence."
        ),
        false_rejection_risk=(
            "Rejecting valid continuous models (like limma-voom) if the check is inappropriately applied to tools that "
            "do not require discrete integer counts."
        ),
        literature_citations=[
            CitationRef(
                author="Ahlmann-Eltze, C. & Huber, W.",
                year=2023,
                title="Comparison of transformations for single-cell RNA-seq data",
                journal="Nature Methods",
                doi="10.1038/s41592-023-01814-1",
                evidence_quote="Log-transformed counts fed into count-based GLMs violate distributional assumptions and severely bias variance estimates.",
                relevance="Comprehensive evaluation of count transformation interactions with GLMs.",
            ),
            CitationRef(
                author="Robinson, M. D. & Smyth, G. K.",
                year=2008,
                title="Small-sample estimation of negative binomial dispersion, with applications to SAGE data",
                journal="Biostatistics",
                doi="10.1093/biostatistics/kxm030",
                evidence_quote="The negative binomial likelihood requires discrete non-negative integer frequency data.",
                relevance="Theoretical foundation of discrete dispersion estimation.",
            ),
        ],
        change_rationale=(
            "Upgraded from naive layer name checks ('counts', 'raw') to full array data inspection, verifying discrete "
            "non-negative finite values and providing automated conversion guidance."
        ),
        dual_track_semantics=RuleDualTrackSemantics(
            rule_flag_meaning="Matrix input contains negative, fractional, or log-transformed values where discrete counts were required.",
            expert_flaw_meaning="Negative binomial GLM mathematically invalid because log-space variance behavior violates discrete Poisson-gamma mixture assumptions.",
            harmless_exception_context="The downstream model explicitly uses Gaussian continuous likelihoods (e.g. limma-trend) designed for log2-transformed continuous values.",
        ),
        aliases=["raw_counts_required", "non_negative_integer_counts"],
    ),
    "BFA-003": ScientificRuleObject(
        rule_id="BFA-003",
        name="Multiple Testing Correction & Selective Reporting Prevention",
        version="2.0.0",
        category=RuleCategory.WARRANT_EPISTEMIC,
        epistemic_kind=EpistemicKind.WARRANT_CONSTRAINT,
        enforcement_level=EnforcementLevel.ENFORCED,
        consensus=ConsensusLevel.ESTABLISHED,
        applicability_conditions=[
            "Genome-wide or high-throughput differential expression testing across thousands of simultaneous gene features.",
            "Claims asserting statistical significance of specific candidate genes.",
        ],
        exceptions=[
            "Pre-specified single-hypothesis testing of a single candidate gene declared a priori before data collection.",
            "Honest negative result reporting explicitly acknowledging that no genes achieved genome-wide FDR significance.",
        ],
        expected_benefit=(
            "Controls the False Discovery Rate under Benjamini-Hochberg / Storey q-value paradigms, preventing "
            "hundreds to thousands of chance fluctuations from being reported as genuine biological discoveries."
        ),
        false_rejection_risk=(
            "Falsely flagging honest negative findings where researchers correctly reported that zero genes survived FDR "
            "correction without selective p-hacking."
        ),
        literature_citations=[
            CitationRef(
                author="Benjamini, Y. & Hochberg, Y.",
                year=1995,
                title="Controlling the false discovery rate: a practical and powerful approach to multiple testing",
                journal="Journal of the Royal Statistical Society: Series B",
                doi="10.1111/j.2517-6161.1995.tb02031.x",
                evidence_quote="Controlling the FDR provides an appropriate compromise between false positive control and statistical power in simultaneous testing.",
                relevance="The foundation of false discovery rate control in modern genomics.",
            ),
        ],
        change_rationale=(
            "Added explicit 'Honest Negative Result' recognition: distinguishing between p-hacking (reporting raw p < 0.05 "
            "when padj is non-significant) and honest null reporting (where zero DEGs surviving FDR is faithfully stated)."
        ),
        dual_track_semantics=RuleDualTrackSemantics(
            rule_flag_meaning="Results table lacks adjusted p-values, or raw p < 0.05 is selectively highlighted while FDR < 0.05 yields zero genes.",
            expert_flaw_meaning="P-hacking and selective reporting: capitalising on random noise across 20,000 tested genes without multiple-testing adjustment.",
            harmless_exception_context="Study explicitly froze as a negative result (Honest Null) reporting no genes passed the genome-wide significance threshold.",
        ),
        aliases=["fdr_correction", "multiple_testing", "p_hacking_guard"],
    ),
    "BFA-004": ScientificRuleObject(
        rule_id="BFA-004",
        name="Complete Technical Batch vs Biological Condition Confounding",
        version="2.0.0",
        category=RuleCategory.WARRANT_EPISTEMIC,
        epistemic_kind=EpistemicKind.WARRANT_CONSTRAINT,
        enforcement_level=EnforcementLevel.ENFORCED,
        consensus=ConsensusLevel.ESTABLISHED,
        applicability_conditions=[
            "Differential expression comparisons across experimental groups where technical batches (sequencer, flowcell, lane, day, processing site) are recorded or present.",
        ],
        exceptions=[
            "Technical benchmarking papers whose explicit goal is to measure batch differences rather than biological condition effects.",
        ],
        expected_benefit=(
            "Intercepts experimental designs where technical batch is 100% collinear with biological condition, in which "
            "case no mathematical algorithm can distinguish technical instrumentation shift from true biology."
        ),
        false_rejection_risk=(
            "Incorrectly flagging balanced designs with partial batch overlap that can be fully corrected via covariate "
            "adjustment in the GLM design matrix (e.g. ~ batch + condition)."
        ),
        literature_citations=[
            CitationRef(
                author="Nygaard, V., Rødland, E. A. & Hovig, E.",
                year=2016,
                title="Methods that remove batch effects while retaining group differences may also mediate spurious findings",
                journal="Nucleic Acids Research",
                doi="10.1093/nar/gkw084",
                evidence_quote="When batch and group are completely confounded, batch correction algorithms cannot recover the true biological signal.",
                relevance="Definitive proof that complete confounding is mathematically uncorrectable.",
            ),
            CitationRef(
                author="Leek, J. T. et al.",
                year=2010,
                title="Tackling the widespread and critical impact of batch effects in high-throughput data",
                journal="Nature Reviews Genetics",
                doi="10.1038/nrg2825",
                evidence_quote="Complete confounding between processing batch and clinical outcome represents an irrecoverable design failure.",
                relevance="Comprehensive survey of batch effects and experimental design principles.",
            ),
        ],
        change_rationale=(
            "Differentiates between benign partial batch imbalance (solvable by multi-factor GLM) and 100% complete technical "
            "collinearity (contingency matrix where all Control is Batch A and all Disease is Batch B)."
        ),
        dual_track_semantics=RuleDualTrackSemantics(
            rule_flag_meaning="Contingency table between condition and batch shows 100% complete separation (zero degrees of freedom for separating batch from condition).",
            expert_flaw_meaning="Fatal experimental design flaw: differences between groups reflect sequencer calibration, reagent lots, or temperature rather than disease biology.",
            harmless_exception_context="Study is a technical QA/QC study specifically characterizing the batch effect magnitude itself.",
        ),
        aliases=["batch_confounding", "collinear_batch_condition"],
    ),
    "BFA-007": ScientificRuleObject(
        rule_id="BFA-007",
        name="Single-Donor Cell Contribution Dominance & Private Transcriptome Bias",
        version="2.0.0",
        category=RuleCategory.WARRANT_EPISTEMIC,
        epistemic_kind=EpistemicKind.WARRANT_CONSTRAINT,
        enforcement_level=EnforcementLevel.ADVISORY,
        consensus=ConsensusLevel.ESTABLISHED,
        applicability_conditions=[
            "Single-cell cell-type or subpopulation differential expression analysis.",
            "Subsets of cells where donor contribution is highly skewed (>70% cells from one donor).",
        ],
        exceptions=[
            "Tumor clonal evolution studies where a specific patient exhibits a private driver mutation expansion explicitly framed as patient-specific.",
            "Pseudobulk aggregation that equalizes donor weights (one pseudobulk profile per donor regardless of cell count), accompanied by Leave-One-Donor-Out sensitivity checks.",
        ],
        expected_benefit=(
            "Prevents a single outlier donor's idiosyncratic genetic background or private clonal expansion from "
            "masquerading as a universal population-level cell-state signature."
        ),
        false_rejection_risk=(
            "Flagging genuine biological cell-type expansions (e.g. rare antigen-specific T cell clone) if the rule "
            "does not provide a sensitivity-analysis remedy (Leave-One-Donor-Out) to verify robustness."
        ),
        literature_citations=[
            CitationRef(
                author="Crowell, H. L. et al.",
                year=2020,
                title="muscat detects subpopulation-specific state transitions from multi-sample multi-condition single-cell transcriptomics data",
                journal="Nature Communications",
                doi="10.1038/s41467-020-19894-4",
                evidence_quote="Unequal cell representation across replicates biases cell-level testing toward the dominant donor's transcriptome.",
                relevance="Quantification of donor dominance effects in subpopulation DE.",
            ),
        ],
        change_rationale=(
            "Provides an actionable PI decision item and sensitivity check: instead of outright blocking, recommends "
            "Leave-One-Donor-Out (LODO) DEG Jaccard concordance (>75%) to confirm effect reproducibility."
        ),
        dual_track_semantics=RuleDualTrackSemantics(
            rule_flag_meaning="A single donor contributes >=70% of cells within the analyzed cell type cluster.",
            expert_flaw_meaning="Identified DEGs reflect the private transcriptome or somatic variant of one individual rather than true condition-associated regulation.",
            harmless_exception_context="Analysis employs pseudobulk aggregation where each donor contributes exactly one equal-weight profile and LODO confirms DEG stability.",
        ),
        aliases=["donor_imbalance", "private_transcriptome_bias"],
    ),
    "BFA-008": ScientificRuleObject(
        rule_id="BFA-008",
        name="Unwarranted Causal and Diagnostic Biomarker Overclaiming",
        version="2.0.0",
        category=RuleCategory.WARRANT_EPISTEMIC,
        epistemic_kind=EpistemicKind.WARRANT_CONSTRAINT,
        enforcement_level=EnforcementLevel.ENFORCED,
        consensus=ConsensusLevel.ESTABLISHED,
        applicability_conditions=[
            "Observational transcriptomics without active randomized intervention, genetic instrument (Mendelian randomization), or functional perturbation.",
        ],
        exceptions=[
            "True functional genetic perturbation experiments (e.g. CRISPR-Cas9, Perturb-seq, RNAi knockdowns) with randomized controls.",
            "Prospective clinical validation cohorts with pre-registered diagnostic accuracy endpoints.",
        ],
        expected_benefit=(
            "Enforces epistemic modesty: prevents non-interventional observational correlations from being marketed as "
            "direct therapeutic targets, causal disease drivers, or validated clinical biomarkers."
        ),
        false_rejection_risk=(
            "Over-restricting standard academic prose when researchers use hedged associational language with clear "
            "correlation-not-causation caveats."
        ),
        literature_citations=[
            CitationRef(
                author="Pearl, J.",
                year=2009,
                title="Causality: Models, Reasoning, and Inference",
                journal="Cambridge University Press",
                doi="10.1017/CBO9780511803161",
                evidence_quote="Causal claims cannot be established from observational distributions without structural identification assumptions.",
                relevance="Theoretical foundation of causal identifiability and observational bounds.",
            ),
            CitationRef(
                author="Hernán, M. A. & Robins, J. M.",
                year=2020,
                title="Causal Inference: What If",
                journal="Chapman & Hall/CRC",
                doi="10.1201/9781315370279",
                evidence_quote="Confounding and selection bias preclude causal interpretation in the absence of valid exchangeability.",
                relevance="Epidemiological and observational causal inference standards.",
            ),
        ],
        change_rationale=(
            "Connected to DeterministicWarrantEngine: decomposes compound claims into Directionality, CausalStrength, and "
            "GeneralizationScope, strictly confining observational claims to EXPLORATORY_COHORT or OBSERVATIONAL_ASSOCIATION."
        ),
        dual_track_semantics=RuleDualTrackSemantics(
            rule_flag_meaning="Manuscript or summary asserts causal verbs ('causes', 'drives', 'biomarker for treatment') from purely observational non-perturbed data.",
            expert_flaw_meaning="Logical and scientific non-sequitur: observational gene expression differences cannot establish directional etiology or clinical utility without perturbation.",
            harmless_exception_context="Claims are strictly phrased as observational associations with explicit downstream functional verification recommendations.",
        ),
        aliases=["causal_overclaim", "biomarker_overclaim", "prohibited_causal_language"],
    ),
    "BFA-014": ScientificRuleObject(
        rule_id="BFA-014",
        name="Execution Binding Hallucination and Past-Tense Fact Contradiction",
        version="2.0.0",
        category=RuleCategory.INVARIANT_INTEGRITY,
        epistemic_kind=EpistemicKind.EXECUTION_INVARIANT,
        enforcement_level=EnforcementLevel.ENFORCED,
        consensus=ConsensusLevel.ESTABLISHED,
        applicability_conditions=[
            "Scientific reports, audit dossiers, and Methods sections claiming that specific statistical algorithms or workflows were executed.",
        ],
        exceptions=[],
        expected_benefit=(
            "Guarantees absolute scientific truthfulness between stated Methods text and cryptographic execution records, "
            "preventing automated AI agents or human researchers from hallucinating unexecuted analyses."
        ),
        false_rejection_risk=(
            "Virtually zero false rejection risk: if code and execution records state Method X was used, claiming Method Y is an objective falsehood."
        ),
        literature_citations=[
            CitationRef(
                author="BioNexus Epistemic Trust Framework",
                year=2026,
                title="Structural Honesty and Execution Binding in Scientific AI Agents (BNS-017 / BNS-025)",
                journal="BioNexus Standards Series",
                doi="",
                evidence_quote="Past-tense factual statements in scientific reports must be cryptographically bound to verified execution records.",
                relevance="BioNexus core invariant for preventing hallucinated scientific analysis.",
            ),
        ],
        change_rationale=(
            "Eliminates self-attested methodology claims: verifies execution fingerprints and rejects unexecuted fact assertions."
        ),
        dual_track_semantics=RuleDualTrackSemantics(
            rule_flag_meaning="The written report asserts that a specific model/test was performed, but the verified execution record shows a different algorithm or none at all.",
            expert_flaw_meaning="Scientific fraud or critical reporting error: presenting simulated or unperformed analyses as completed empirical facts.",
            harmless_exception_context="None: past-tense execution claims must strictly match executed facts.",
        ),
        aliases=["execution_hallucination", "unexecuted_fact_claim"],
    ),
}


def get_canonical_rule_objects() -> Dict[str, ScientificRuleObject]:
    """Retrieve all canonical scientific rule research objects."""
    return deepcopy(CANONICAL_SCIENTIFIC_RULES)


def get_rule_object(rule_id: str) -> Optional[ScientificRuleObject]:
    """Retrieve a specific rule research object by ID or alias."""
    if rule_id in CANONICAL_SCIENTIFIC_RULES:
        return deepcopy(CANONICAL_SCIENTIFIC_RULES[rule_id])
    for r in CANONICAL_SCIENTIFIC_RULES.values():
        if rule_id in r.aliases:
            return deepcopy(r)
    return None
