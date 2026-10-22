"""
Static contract definitions for Canonical Flagship Bioinformatics Capabilities.
"""

from __future__ import annotations

from typing import Dict

from bionexus.capability_catalog.models import (
    BackendRequirement,
    CapabilityContract,
    EvidenceRequirement,
    InputSpecification,
    Precondition,
    RefusalTrigger,
    SemanticInputType,
)

CANONICAL_CAPABILITIES: Dict[str, CapabilityContract] = {
    # 1. Single-cell Pseudobulk Differential Expression
    "scrna.pseudobulk_de": CapabilityContract(
        id="scrna.pseudobulk_de",
        version=1,
        display_name="Single-Cell Pseudobulk Differential Expression",
        skill_name="single-cell-rna-qc",
        summary="Condition differential expression across biological replicate groups using negative binomial GLM (PyDESeq2).",
        intent=[
            "compare_conditions",
            "differential_expression",
            "condition_de",
            "treatment_effect",
            "disease_vs_control",
        ],
        inputs={
            "expression": InputSpecification(
                name="expression",
                semantic_type=SemanticInputType.RAW_COUNTS.value,
                required=True,
                description="Pseudobulk summed count matrix of integer counts per sample x condition.",
                validation_rule="audit_expression_matrix:counts",
            ),
            "sample_design": InputSpecification(
                name="sample_design",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=True,
                description="Sample metadata table with biological replicate identifiers and condition factors.",
            ),
        },
        preconditions=[
            Precondition(
                id="min_replicates",
                rule="n_replicates_per_condition >= 2",
                description="Each experimental condition must contain at least 2 biological replicates to estimate dispersion.",
                fatal_if_violated=True,
            ),
            Precondition(
                id="raw_integer_counts",
                rule="is_integer_like(counts) == True",
                description="Negative binomial GLM requires raw integer counts, not normalized floats.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="pydeseq2",
            import_name="pydeseq2",
            minimum_version="0.4.0",
            extra="deseq",
            entry_points=("pydeseq2.dds.DeseqDataSet", "pydeseq2.ds.DeseqStats"),
            description="PyDESeq2 Wald tests on pseudobulk counts",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="normalized_matrix_only",
                description="Normalized continuous matrix passed where raw counts required.",
                remedy="Sum unnormalized raw counts (adata.raw.X) over (sample, cell_type, condition) groups before testing.",
                violated_rule="Negative binomial dispersion estimation requires integer count distribution",
            ),
            RefusalTrigger(
                condition_id="missing_replicates",
                description="Fewer than 2 biological replicates per experimental condition.",
                remedy="Condition DE is statistically invalid without biological replicates (pseudoreplication). Collect additional replicates or report exploratory marker rankings only.",
                violated_rule="Biological replication invariant",
            ),
            RefusalTrigger(
                condition_id="missing_backend",
                description="PyDESeq2 backend not available in environment.",
                remedy="Install via `pip install bionexus-reliability[deseq]` or `pip install pydeseq2`.",
                violated_rule="Gold-standard backend requirement",
            ),
        ],
        outputs=[
            "differential_expression_table (CSV)",
            "volcano_plot (PNG)",
            "dispersion_plot (PNG)",
            "evidence_card (JSON/Markdown)",
            "provenance_sidecar (JSON)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="required",
            effect_size="required",
            min_fdr_alpha=0.05,
            mandatory_limitations=[
                "Condition DE requires pseudobulk replicate aggregation to prevent false discoveries from single-cell pseudoreplication.",
                "Research Use Only. Not for clinical diagnosis.",
            ],
        ),
        forbidden_claims=[
            "causal_interaction",
            "clinical_diagnosis",
            "treatment_recommendation",
        ],
        evidence_ceiling_without_external_validation="SUPPORTED",
    ),
    # 2. Single-cell Exploratory Clustering & Markers
    "scrna.exploratory_clustering": CapabilityContract(
        id="scrna.exploratory_clustering",
        version=1,
        display_name="Single-Cell Exploratory Clustering & Marker Identification",
        skill_name="single-cell-rna-qc",
        summary="scverse exploratory workflow: MAD QC, normalization, HVG, PCA, UMAP, Leiden clustering, and Wilcoxon marker detection.",
        intent=[
            "cluster_cells",
            "scrna_clustering",
            "marker_genes",
            "dimension_reduction",
            "umap_visualization",
        ],
        inputs={
            "counts": InputSpecification(
                name="counts",
                semantic_type=SemanticInputType.RAW_COUNTS.value,
                required=True,
                description="Single-cell count matrix (.h5ad/.h5).",
                validation_rule="audit_expression_matrix:counts",
            ),
        },
        preconditions=[
            Precondition(
                id="min_cells_and_genes",
                rule="n_cells >= 20 and n_genes >= 100",
                description="Sufficient cells and features for meaningful manifold learning.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="scanpy",
            import_name="scanpy",
            minimum_version="1.10.0",
            extra="goldchain",
            entry_points=("scanpy.pp", "scanpy.tl"),
            description="Scanpy single-cell analysis toolkit",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="missing_backend",
                description="Scanpy or anndata is not installed.",
                remedy="Install via `pip install bionexus-reliability[goldchain]` or `pip install scanpy anndata`.",
                violated_rule="scverse gold chain backend requirement",
            ),
            RefusalTrigger(
                condition_id="hallucinated_cell_types",
                description="Attempting to fabricate biological cell type identity without validated reference markers.",
                remedy="Keep cluster identifiers numeric ('0', '1', '2') unless validated against reference atlases.",
                violated_rule="Zero hallucination of cell-type identity invariant",
            ),
        ],
        outputs=[
            "clustered_anndata (.h5ad)",
            "marker_genes_table (CSV)",
            "umap_leiden_plot (PNG)",
            "dotplot_markers (PNG)",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="required",
            effect_size="required",
            mandatory_limitations=[
                "Cluster labels are numeric only. Biological cell types must be verified with orthogonal references.",
                "Marker p-values from rank_genes_groups are exploratory and must not be cited as treatment condition DE.",
            ],
        ),
        forbidden_claims=[
            "cell_type_identity_without_reference",
            "causal_interaction",
            "clinical_diagnosis",
        ],
        evidence_ceiling_without_external_validation="PRELIMINARY",
    ),
    # 3. Spatial Transcriptomics Moran's I SVG Detection
    "spatial.morans_svg": CapabilityContract(
        id="spatial.morans_svg",
        version=1,
        display_name="Spatial Transcriptomics Spatially Variable Gene Detection",
        skill_name="spatial-transcriptomics",
        summary="Squidpy spatial KNN graph construction, Moran's I spatial autocorrelation, and spatial scatter plots.",
        intent=[
            "spatial_transcriptomics",
            "spatially_variable_genes",
            "morans_i",
            "spatial_patterns",
            "visium_analysis",
        ],
        inputs={
            "expression": InputSpecification(
                name="expression",
                semantic_type=SemanticInputType.NORMALIZED_MATRIX.value,
                required=True,
                description="Spatial transcriptomics expression matrix (.h5ad / SpatialData .zarr).",
            ),
            "coordinates": InputSpecification(
                name="coordinates",
                semantic_type=SemanticInputType.SPATIAL_COORDINATES.value,
                required=True,
                description="2D/3D spatial coordinate matrix (adata.obsm['spatial']).",
                validation_rule="audit_spatial_coordinates",
            ),
            "spatial_state": InputSpecification(
                name="spatial_state",
                semantic_type=SemanticInputType.BIGDATA_STORE.value,
                required=True,
                description=(
                    "Expression, gene names, cell labels, coordinate system, and immutable dataset/state/"
                    "segmentation/label revision identifiers; exact contact graph and covariates when applicable."
                ),
            ),
        },
        preconditions=[
            Precondition(
                id="spatial_coords_present",
                rule="'spatial' in adata.obsm and shape[1] in (2, 3)",
                description="Spatial coordinates must be present in obsm['spatial'].",
                fatal_if_violated=True,
            ),
            Precondition(
                id="non_degenerate_geometry",
                rule="variance(spatial_coords) > 1e-8",
                description="Coordinates must have non-zero variance along spatial axes.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="squidpy",
            import_name="squidpy",
            minimum_version="1.3.0",
            extra="spatial",
            entry_points=("squidpy.gr.spatial_neighbors", "squidpy.gr.spatial_autocorr"),
            description="Squidpy spatial analysis library",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="missing_coordinates",
                description="Dataset contains no spatial coordinate arrays.",
                remedy="Provide spatial data containing obsm['spatial'] (Visium, Slide-seq, MERFISH, or SpatialData).",
                violated_rule="Spatial geometry requirement",
            ),
            RefusalTrigger(
                condition_id="missing_backend",
                description="Squidpy library not available.",
                remedy="Install via `pip install bionexus-reliability[spatial]` or `pip install squidpy spatialdata`.",
                violated_rule="Squidpy spatial backend requirement",
            ),
        ],
        outputs=[
            "spatially_variable_genes_table (CSV)",
            "spatial_scatter_plot (PNG)",
            "moran_i_distribution (PNG)",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="required",
            effect_size="required",
            min_fdr_alpha=0.05,
            mandatory_limitations=[
                "Spatial Moran's I identifies spatial autocorrelation, not mechanistic cell-cell signaling.",
                "Research Use Only.",
            ],
        ),
        forbidden_claims=[
            "causal_interaction",
            "cell_cell_communication",
            "cell_type_identity_without_reference",
        ],
        evidence_ceiling_without_external_validation="FRAGILE",
    ),
    # 4. Clinical Cohort Kaplan-Meier Survival Analysis
    "survival.kaplan_meier": CapabilityContract(
        id="survival.kaplan_meier",
        version=1,
        display_name="Clinical Cohort Kaplan-Meier Survival Estimation & Log-Rank Test",
        skill_name="clinical-cohort-analysis",
        summary="Non-parametric Kaplan-Meier survival curve estimation, log-rank hazard equality tests, and median survival confidence intervals.",
        intent=[
            "survival_analysis",
            "kaplan_meier",
            "log_rank_test",
            "cohort_stratification",
            "prognostic_biomarker",
        ],
        inputs={
            "duration": InputSpecification(
                name="duration",
                semantic_type=SemanticInputType.SURVIVAL_DATA.value,
                required=True,
                description="Time-to-event or last follow-up duration array (positive numbers).",
            ),
            "event": InputSpecification(
                name="event",
                semantic_type=SemanticInputType.SURVIVAL_DATA.value,
                required=True,
                description="Binary event indicator (1 = event/death, 0 = censored).",
            ),
            "group": InputSpecification(
                name="group",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=True,
                description="Categorical patient stratification group (e.g. Biomarker High vs Low).",
            ),
        },
        preconditions=[
            Precondition(
                id="positive_durations",
                rule="all(durations >= 0)",
                description="All follow-up durations must be non-negative.",
                fatal_if_violated=True,
            ),
            Precondition(
                id="non_zero_events",
                rule="sum(events) > 0",
                description="At least one observed event required to compute survival probability.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="lifelines",
            import_name="lifelines",
            minimum_version="0.27.0",
            extra="survival",
            entry_points=("lifelines.KaplanMeierFitter", "lifelines.CoxPHFitter"),
            description="Lifelines survival analysis library",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="all_censored",
                description="Zero events observed in cohort (100% censoring).",
                remedy="Survival estimation requires at least one uncensored event.",
                violated_rule="Event observation requirement",
            ),
            RefusalTrigger(
                condition_id="missing_backend",
                description="Lifelines survival package not installed.",
                remedy="Install via `pip install bionexus-reliability[survival]` or `pip install lifelines`.",
                violated_rule="Survival analysis backend requirement",
            ),
        ],
        outputs=[
            "kaplan_meier_curve (PNG)",
            "log_rank_test_summary (CSV/JSON)",
            "median_survival_table (CSV)",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="optional",
            effect_size="required",
            mandatory_limitations=[
                "Kaplan-Meier estimates unadjusted univariate associations and does not control for confounding clinical covariates.",
                "Research Use Only. Not for individual clinical treatment assignment.",
            ],
        ),
        forbidden_claims=[
            "hazard_causation",
            "clinical_diagnosis",
            "treatment_recommendation",
        ],
        evidence_ceiling_without_external_validation="SUPPORTED",
    ),
    # 5. scvi-tools Deep Generative Modeling
    "scvi.probabilistic_vae": CapabilityContract(
        id="scvi.probabilistic_vae",
        version=1,
        display_name="scvi-tools Deep Generative Latent Modeling & Integration",
        skill_name="scvi-tools",
        summary="Train official scvi-tools variational autoencoder models (scVI, scANVI, totalVI) on raw counts for batch correction and latent representation.",
        intent=[
            "train_scvi",
            "batch_integration",
            "latent_embedding",
            "deep_generative_model",
            "zero_shot_imputation",
        ],
        inputs={
            "counts": InputSpecification(
                name="counts",
                semantic_type=SemanticInputType.RAW_COUNTS.value,
                required=True,
                description="Raw un-normalized single-cell count matrix.",
                validation_rule="audit_expression_matrix:counts",
            ),
        },
        preconditions=[
            Precondition(
                id="raw_counts_only",
                rule="is_integer_like(counts) == True",
                description="scvi-tools models the discrete data-generating process (Negative Binomial/ZINB) and strictly requires un-normalized raw counts.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="scvi-tools",
            import_name="scvi",
            minimum_version="1.0.0",
            extra="scverse",
            entry_points=("scvi.model.SCVI",),
            description="scvi-tools probabilistic generative modeling framework",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="normalized_input",
                description="Log-normalized or scaled float matrix provided instead of raw counts.",
                remedy="Train scvi-tools models exclusively on raw integer counts (adata.raw.X or layer='counts'). Do not log-transform beforehand.",
                violated_rule="Discrete likelihood distribution invariant",
            ),
            RefusalTrigger(
                condition_id="missing_backend",
                description="scvi-tools and PyTorch packages are not installed.",
                remedy="Install via `pip install bionexus-reliability[scverse]` or `pip install scvi-tools torch`.",
                violated_rule="scvi-tools backend requirement",
            ),
        ],
        outputs=[
            "latent_representation (adata.obsm['X_scVI'])",
            "trained_model_checkpoint",
            "normalized_expression_denoised",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="optional",
            effect_size="required",
            uncertainty_quantification="required",
            mandatory_limitations=[
                "scVI embeddings represent a probabilistic latent space and do not guarantee biological cell-type identity.",
                "Requires GPU acceleration for large datasets (>50k cells).",
            ],
        ),
        forbidden_claims=[
            "cell_type_identity_without_reference",
            "true_expression_recovery",
            "clinical_diagnosis",
        ],
        evidence_ceiling_without_external_validation="PRELIMINARY",
    ),
    # 6. Instrument Table to Allotrope ASM Standardization
    "allotrope.format_conversion": CapabilityContract(
        id="allotrope.format_conversion",
        version=1,
        display_name="Analytical Instrument Table to Allotrope ASM JSON Standardization",
        skill_name="instrument-data-to-allotrope",
        summary="Convert laboratory instrument tabular outputs (plate readers, qPCR, chromatography, spectrophotometry) to standardized Allotrope Simple Model (ASM) JSON.",
        intent=[
            "allotrope_conversion",
            "standardize_instrument_data",
            "plate_reader_parser",
            "lims_ingest",
            "asm_json",
        ],
        inputs={
            "raw_file": InputSpecification(
                name="raw_file",
                semantic_type=SemanticInputType.INSTRUMENT_TABLE.value,
                required=True,
                description="Analytical instrument export file (.csv, .xlsx, .txt).",
            ),
        },
        preconditions=[
            Precondition(
                id="supported_instrument_or_mapping",
                rule="has_native_adapter(file) or has_yaml_mapping(file)",
                description="File format must match a supported allotropy parser or custom YAML mapping configuration.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="allotropy",
            import_name="allotropy",
            minimum_version="0.1.30",
            extra="allotrope",
            entry_points=("allotropy",),
            description="Allotropy open-source instrument parser library",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="missing_mapping",
                description="Instrument file format is unrecognized and no custom YAML mapping was provided.",
                remedy="Provide an allotropy-compatible vendor export or create a declarative YAML mapping schema.",
                violated_rule="Deterministic data transformation invariant",
            ),
            RefusalTrigger(
                condition_id="missing_backend",
                description="allotropy parser package not installed.",
                remedy="Install via `pip install bionexus-reliability[allotrope]` or `pip install allotropy`.",
                violated_rule="Allotropy backend requirement",
            ),
        ],
        outputs=[
            "allotrope_asm_record (.json)",
            "flattened_2d_table (.csv)",
            "evidence_card (JSON/Markdown)",
            "provenance_sidecar (JSON)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "Conversion maps syntax and schema only; does not validate analytical sensor calibration.",
                "Research Use Only. Not an FDA 21 CFR Part 11 certified data converter.",
            ],
        ),
        forbidden_claims=[
            "sensor_calibration_validated",
            "regulatory_compliance",
        ],
        evidence_ceiling_without_external_validation="PRELIMINARY",
    ),
    # 7. Nextflow Pipeline Launch Artifacts & Cluster Preflight
    "nextflow.pipeline_launch": CapabilityContract(
        id="nextflow.pipeline_launch",
        version=1,
        display_name="Nextflow nf-core Samplesheet & Launch Artifact Preparation",
        skill_name="nextflow-development",
        summary="Generate canonical nf-core samplesheets, validate execution profiles, and generate reproducibility launch commands for Slurm/AWS/GCP.",
        intent=[
            "nextflow_pipeline",
            "nf_core_samplesheet",
            "cluster_config",
            "batch_compute_launch",
            "rnaseq_pipeline",
            "scrnaseq_pipeline",
            "differentialabundance_pipeline",
            "sarek_pipeline",
            "spatialtranscriptomics_pipeline",
            "nextflow_receipt",
            "harvest_nextflow_run",
        ],
        inputs={
            "sample_manifest": InputSpecification(
                name="sample_manifest",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=True,
                description="Directory of FASTQ/BAM files, raw sample CSV metadata, or completed Nextflow run directory.",
            ),
        },
        preconditions=[
            Precondition(
                id="valid_paired_reads",
                rule="fastq_1 and (fastq_2 or is_single_end)",
                description="Sequencing read paths must resolve to valid existing FASTQ files.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="nf-core",
            import_name="bionexus",
            minimum_version="0.8.0",
            extra="dev",
            description="nf-core sample generator, cluster launch compiler, and Nextflow run harvester",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="missing_fastq_files",
                description="Specified sequencing read files do not exist on disk.",
                remedy="Check sample path patterns and provide valid absolute paths to raw sequencing files.",
                violated_rule="File existence prerequisite",
            ),
        ],
        outputs=[
            "samplesheet.csv",
            "nextflow.config",
            "launch_command.sh",
            "nextflow_tool_receipt (JSON)",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "Generates deployment configurations; pipeline execution requires Nextflow runtime and container engine (Docker/Singularity).",
            ],
        ),
        forbidden_claims=[
            "pipeline_results_without_execution",
            "regulatory_compliance",
        ],
        evidence_ceiling_without_external_validation="PRELIMINARY",
    ),
    # 8. Deterministic ACMG Variant Tiering
    "variant.acmg_classification": CapabilityContract(
        id="variant.acmg_classification",
        version=1,
        display_name="Deterministic ACMG/AMP Genetic Variant Pathogenicity Classification",
        skill_name="variant-interpretation",
        summary="Deterministic Bayesian and rule-based combination of caller-supplied ACMG/AMP criteria (PVS1, PS1-4, PM1-6, PP1-5, BA1, BS1-4, BP1-7).",
        intent=[
            "variant_interpretation",
            "acmg_classification",
            "pathogenicity_scoring",
            "clinical_genetics",
            "variant_tiering",
        ],
        inputs={
            "variant_id": InputSpecification(
                name="variant_id",
                semantic_type=SemanticInputType.VARIANT_RECORDS.value,
                required=True,
                description="Genomic variant HGVS descriptor or coordinate string.",
            ),
            "acmg_codes": InputSpecification(
                name="acmg_codes",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=True,
                description="Caller-verified ACMG criteria codes with evidence rationales.",
            ),
        },
        preconditions=[
            Precondition(
                id="no_auto_pvs1_without_mechanism",
                rule="pvs1_applied -> lof_mechanism_verified == True",
                description="PVS1 null variant criterion strictly requires verified loss-of-function disease mechanism for the target gene.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="local combiner",
            import_name="bionexus",
            minimum_version="0.8.0",
            description="Deterministic ACMG/AMP Bayesian posterior combiner",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="unverified_clinical_diagnosis",
                description="Attempting to issue formal clinical diagnostic report without CLIA/CAP certification.",
                remedy="Attach mandatory RUO disclaimer. Output must state 'Research Use Only' and cannot be used for direct patient management.",
                violated_rule="Regulatory and clinical honesty invariant",
            ),
        ],
        outputs=[
            "acmg_classification_record (JSON)",
            "clinical_monograph (Markdown)",
            "posterior_probability_score",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="required",
            mandatory_limitations=[
                "Deterministic combiner only; does not query live clinical registries (ClinVar/gnomAD) unless MCP tools are connected.",
                "Research Use Only. Not for clinical diagnostic use.",
            ],
        ),
        forbidden_claims=[
            "clinical_diagnosis",
            "treatment_recommendation",
        ],
        evidence_ceiling_without_external_validation="ROBUST",
    ),
    # 9. Cell Annotation Evidence Assessment (flagship capability B, BNS-013)
    "scrna.annotation_evidence": CapabilityContract(
        id="scrna.annotation_evidence",
        version=1,
        display_name="Cell Annotation Evidence Assessment",
        skill_name="single-cell-rna-qc",
        summary=(
            "Not another annotator: assesses how much evidence backs each candidate cell-type label "
            "(reference mapping, marker consistency, negative markers, doublet risk, ontology compatibility, "
            "open-set detection, cross-method agreement) and returns per-label verdicts."
        ),
        intent=[
            "annotation_evidence",
            "label_support",
            "cell_type_verification",
            "open_set_annotation",
            "annotation_audit",
        ],
        inputs={
            "expression": InputSpecification(
                name="expression",
                semantic_type=SemanticInputType.NORMALIZED_MATRIX.value,
                required=True,
                description="Cell-level expression used for marker consistency and doublet assessment.",
            ),
            "candidate_labels": InputSpecification(
                name="candidate_labels",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=True,
                description="Candidate label assignment per cluster or per cell to be assessed (never asserted).",
            ),
            "reference": InputSpecification(
                name="reference",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=False,
                description="Reference atlas mapping or curated marker panel with positive and negative markers.",
            ),
        },
        preconditions=[
            Precondition(
                id="annotation_source_recorded",
                rule="every non-numeric label cites an evidence source",
                description="A label without a recorded evidence source is a candidate, not an identity (BNS-II-008).",
                fatal_if_violated=True,
            ),
            Precondition(
                id="negative_markers_evaluated",
                rule="negative_marker_violation is measured or explicitly declared unmeasured",
                description="Positive-marker coherence alone cannot separate related lineages.",
                fatal_if_violated=False,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="local deterministic evidence combiner",
            import_name="bionexus",
            minimum_version="0.10.0",
            description="Deterministic annotation-evidence scoring (annotation_evidence.assess_annotation_evidence)",
            entry_points=("bionexus.annotation_evidence",),
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="no_annotation_evidence",
                description="No reference mapping, marker panel, or cross-method evidence is available for the labels.",
                remedy="Keep labels numeric or explicitly putative; attach a reference atlas or curated marker panel with negative markers.",
                violated_rule="Annotation evidence requirement (BN-F003)",
            ),
            RefusalTrigger(
                condition_id="open_set_population",
                description="An unknown/open-set population is being forced onto a known reference label.",
                remedy="Report the population as unknown/novel (ABSTAIN verdict) until orthogonal evidence is collected.",
                violated_rule="Open-set honesty invariant (BN-F003)",
            ),
        ],
        outputs=[
            "per_label_verdicts (SUPPORTED | TENTATIVE | ABSTAIN) (JSON/CSV)",
            "missing_evidence_requests (list)",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="optional",
            effect_size="recommended",
            mandatory_limitations=[
                "Verdicts describe evidence support for labels, not ground-truth identity.",
                "ABSTAIN for open-set labels is the honest answer, not a failure.",
            ],
        ),
        forbidden_claims=[
            "cell_type_identity_without_reference",
            "causal_interaction",
            "clinical_diagnosis",
        ],
        evidence_ceiling_without_external_validation="SUPPORTED",
    ),
    # 10. Spatial Inference Validity Assessment (flagship capability C, BNS-013)
    "spatial.inference_validity": CapabilityContract(
        id="spatial.inference_validity",
        version=2,
        display_name="Spatial Alternative Explanation Battery",
        skill_name="spatial-transcriptomics",
        summary=(
            "An executable, empirically calibrated challenge battery for a declared spatial observation: tests "
            "segmentation perturbations, transcript leakage, morphology, density, contact geometry, batch/FOV, "
            "neighborhood radius, coordinate nulls, and cell-label perturbations. It does not run a generic "
            "spatial workflow or silently substitute expert magic numbers."
        ),
        intent=[
            "spatial_inference_validity",
            "alternative_explanation_testing",
            "spatial_conclusion_robustness",
            "spatial_confound_audit",
        ],
        inputs={
            "observation": InputSpecification(
                name="observation",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=True,
                description="The spatial finding under test, stated as an observation (not a mechanism).",
            ),
            "coordinates": InputSpecification(
                name="coordinates",
                semantic_type=SemanticInputType.SPATIAL_COORDINATES.value,
                required=True,
                description="Physical spatial coordinates in micrometers; embeddings are not accepted.",
                validation_rule="audit_spatial_coordinates",
            ),
            "alternative_controls": InputSpecification(
                name="alternative_controls",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=False,
                description="Status of each alternative-explanation control (TESTED / CONTROLLED / UNTESTED / FAILED).",
            ),
            "battery_plan": InputSpecification(
                name="battery_plan",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=True,
                description=(
                    "Predeclared radii, leakage sensitivity, perturbation counts, seed, minimum group size, and "
                    "graph bound for executable alternative-explanation testing."
                ),
            ),
        },
        preconditions=[
            Precondition(
                id="coordinate_provenance_recorded",
                rule="coordinate origin is physical tissue space in micrometers",
                description="Embeddings substituted for tissue coordinates invalidate spatial statistics (BNS-II-006).",
                fatal_if_violated=True,
            ),
            Precondition(
                id="core_confound_controls_tested",
                rule=(
                    "cell_size, transcript_density, segmentation_uncertainty, transcript_leakage, and "
                    "contact_geometry are TESTED or CONTROLLED"
                ),
                description="The canonical spatial confound controls must be addressed before any validity verdict.",
                fatal_if_violated=False,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="local deterministic alternative-explanation tester",
            import_name="bionexus",
            minimum_version="0.10.0",
            description=(
                "Bounded perturbation battery with profile-conditioned warrant decisions "
                "(spatial_alternative_battery.run_spatial_alternative_battery)"
            ),
            entry_points=(
                "bionexus.spatial_alternative_battery",
                "bionexus.spatial_inference",
            ),
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="no_controls_provided",
                description="Validity requested with zero alternative-explanation controls.",
                remedy=(
                    "Run the bounded battery with segmentation/leakage variants, morphology and density covariates, "
                    "contact geometry, radius sensitivity, coordinate nulls, and label perturbations."
                ),
                violated_rule="Alternative-explanation requirement (BN-F006)",
            ),
            RefusalTrigger(
                condition_id="embedding_substitution",
                description="UMAP/PCA coordinates offered where physical tissue coordinates are required.",
                remedy="Provide physical tissue coordinates in micrometers; no embedding fallback is permitted.",
                violated_rule="Spatial provenance invariant (BN-F009)",
            ),
        ],
        outputs=[
            "alternative_explanation_battery (per-control scores, perturbations, and calibration resolution) (JSON)",
            "validity_verdict (ROBUST | SUPPORTED | FRAGILE | CONFLICTED | ABSTAIN)",
            "unresolved_alternatives (list)",
            "state-bound provenance and input hashes",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="recommended",
            effect_size="recommended",
            mandatory_limitations=[
                "A FRAGILE verdict names the untested alternatives, not a negative result.",
                "An unapproved or absent empirical calibration profile cannot produce a CONTROLLED diagnostic.",
                "Assumed leakage fractions are sensitivity analyses, not estimates of true transcript leakage.",
                "Orthogonal validation is required to assert beyond FRAGILE for confound-sensitive observations.",
            ],
        ),
        forbidden_claims=[
            "causal_interaction",
            "cell_cell_communication",
            "cell_type_identity_without_reference",
        ],
        evidence_ceiling_without_external_validation="FRAGILE",
    ),
    # 11. HPC & Cloud-Native Batch Job Generation, Dispatch & Lifecycle Management
    "cluster.hpc_dispatch": CapabilityContract(
        id="cluster.hpc_dispatch",
        version=1,
        display_name="HPC & Cloud-Native Batch Job Generation, Dispatch & Lifecycle Management",
        skill_name="nextflow-development",
        summary="Generate native batch scripts (Slurm/PBS/LSF/Kubernetes/AWS/GCP), submit jobs, track queue status, and perform OOM/timeout post-mortem diagnosis.",
        intent=[
            "cluster_dispatch",
            "hpc_submit",
            "slurm_job",
            "batch_job",
            "cloud_compute",
            "job_diagnostics",
            "kubernetes_job",
        ],
        inputs={
            "command": InputSpecification(
                name="command",
                semantic_type=SemanticInputType.COMPUTE_SPECIFICATION.value,
                required=True,
                description="Bioinformatics command line string or list of execution commands.",
            ),
        },
        preconditions=[
            Precondition(
                id="positive_cpus_and_memory",
                rule="cpus > 0 and memory_specified == True",
                description="HPC batch jobs must declare valid positive CPU and memory allocation limits.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="bionexus-cluster",
            import_name="bionexus.cluster",
            minimum_version="0.9.0",
            description="BioNexus unified HPC and cloud batch dispatcher",
            entry_points=("bionexus.cluster",),
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="unsupported_scheduler",
                description="Target scheduler is not recognized or supported by BioNexus.",
                remedy="Select a supported scheduler: slurm, pbs, lsf, sge, kubernetes, aws_batch, or gcp_batch.",
                violated_rule="Scheduler compatibility rule",
            ),
        ],
        outputs=[
            "job_script (bash/YAML/JSON)",
            "job_id",
            "job_submission_result (JSON)",
            "job_diagnostic_report (Markdown/JSON)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "Generates and dispatches batch job manifests; execution outcome depends on remote cluster infrastructure health.",
            ],
        ),
        forbidden_claims=[
            "pipeline_results_without_execution",
            "regulatory_compliance",
        ],
        evidence_ceiling_without_external_validation="SUPPORTED",
    ),
    # 12. Large-Scale Biological Matrix Memory Estimation & Out-of-Core Streaming Audit
    "bigdata.out_of_core_audit": CapabilityContract(
        id="bigdata.out_of_core_audit",
        version=1,
        display_name="Large-Scale Biological Matrix Memory Estimation & Out-of-Core Streaming Audit",
        skill_name="single-cell-rna-qc",
        summary="Audit storage format, estimate RAM requirements for multi-million cell datasets, prevent OOM crashes, and generate out-of-core streaming execution plans.",
        intent=[
            "bigdata_audit",
            "memory_estimation",
            "out_of_core",
            "zarr_streaming",
            "oom_prevention",
            "large_matrix_plan",
        ],
        inputs={
            "matrix_dimensions": InputSpecification(
                name="matrix_dimensions",
                semantic_type=SemanticInputType.BIGDATA_STORE.value,
                required=True,
                description="Dataset dimensions (n_cells, n_genes) or file path to H5AD/Zarr store.",
            ),
        },
        preconditions=[
            Precondition(
                id="valid_positive_dimensions",
                rule="n_cells > 0 and n_genes > 0",
                description="Dataset matrix dimensions must be non-zero positive integers.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="bionexus-bigdata",
            import_name="bionexus.bigdata",
            minimum_version="0.9.0",
            description="BioNexus large-scale matrix memory and streaming estimator",
            entry_points=("bionexus.bigdata",),
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="critical_oom_in_memory",
                description="Attempting to perform in-memory dense matrix operations that exceed 200% of host RAM.",
                remedy="Must switch to AnnData backed mode (backed='r'), convert to chunked Zarr, or dispatch to HPC cluster with higher RAM.",
                violated_rule="Host memory safety invariant",
            ),
        ],
        outputs=[
            "memory_estimation_report (JSON)",
            "streaming_execution_plan (Markdown)",
            "storage_audit_report (JSON)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "Calculates theoretical and empirical working memory bounds based on sparse/dense representations.",
            ],
        ),
        forbidden_claims=[
            "regulatory_compliance",
        ],
        evidence_ceiling_without_external_validation="SUPPORTED",
    ),
    # 13. Spatial Transcriptomics Tangram Single-Cell to Spatial Deconvolution
    "spatial.tangram_deconvolution": CapabilityContract(
        id="spatial.tangram_deconvolution",
        version=1,
        display_name="Spatial Transcriptomics Tangram Single-Cell to Spatial Deconvolution",
        skill_name="spatial-transcriptomics",
        summary="Optimal transport & deep learning mapping of single-cell reference transcriptomes to spatial coordinates with spot deconvolution.",
        intent=[
            "tangram_mapping",
            "spatial_deconvolution",
            "spot_deconvolution",
            "cell_to_space",
            "visium_deconvolution",
        ],
        inputs={
            "sc_reference": InputSpecification(
                name="sc_reference",
                semantic_type=SemanticInputType.RAW_COUNTS.value,
                required=True,
                description="Annotated single-cell RNA-seq reference AnnData.",
            ),
            "spatial_target": InputSpecification(
                name="spatial_target",
                semantic_type=SemanticInputType.SPATIAL_COORDINATES.value,
                required=True,
                description="Spatial transcriptomics AnnData containing obsm['spatial'].",
                validation_rule="audit_spatial_coordinates",
            ),
        },
        preconditions=[
            Precondition(
                id="spatial_coords_present",
                rule="'spatial' in spatial_adata.obsm and shape[1] in (2, 3)",
                description="Spatial coordinates must be present in target obsm['spatial'].",
                fatal_if_violated=True,
            ),
            Precondition(
                id="reference_cell_types_present",
                rule="cell_type_col in sc_adata.obs",
                description="Single-cell reference must contain cell type annotations in obs.",
                fatal_if_violated=True,
            ),
            Precondition(
                id="shared_genes_sufficient",
                rule="len(shared_marker_genes) >= 10",
                description="At least 10 marker genes must overlap between single-cell reference and spatial target.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="tangram-sc",
            import_name="tangram",
            minimum_version="1.0.4",
            extra="spatial",
            entry_points=("tangram.mapper",),
            description="Tangram optimal transport spatial mapping library",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="missing_coordinates",
                description="Spatial target contains no 2D/3D coordinate arrays.",
                remedy="Ensure spatial AnnData contains valid 2D coordinates in obsm['spatial'].",
                violated_rule="Spatial geometry requirement",
            ),
            RefusalTrigger(
                condition_id="unannotated_reference",
                description="Single-cell reference lacks cell type annotations.",
                remedy="Provide single-cell AnnData with labeled cell types in obs (e.g. obs['cell_type']).",
                violated_rule="Reference annotation requirement",
            ),
            RefusalTrigger(
                condition_id="insufficient_shared_genes",
                description="Fewer than 10 marker genes overlap between scRNA and spatial target.",
                remedy="Harmonize gene symbol / Ensembl ID nomenclature between single-cell and spatial datasets.",
                violated_rule="Feature overlap requirement",
            ),
        ],
        outputs=[
            "tangram_cell_proportions (adata_sp.obsm['tangram_ct_pred'])",
            "dominant_cell_types (adata_sp.obs['dominant_cell_type'])",
            "cell_to_spot_mapping_matrix (.h5ad)",
            "deconvolution_summary (CSV)",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "Predicted spot proportions represent probabilistic optimal transport weights, not physical microscopic counting.",
                "Research Use Only. Not for clinical diagnosis.",
            ],
        ),
        forbidden_claims=[
            "clinical_diagnosis",
            "causal_interaction",
            "cell_type_identity_without_reference",
        ],
        evidence_ceiling_without_external_validation="SUPPORTED",
    ),
    "structure.confidence_audit": CapabilityContract(
        id="structure.confidence_audit",
        display_name="Macromolecular Structural Confidence & Epistemic Audit",
        intent=["alphafold_structure_confidence", "protein_disorder_audit", "plddt_verification"],
        skill_name="alphafold-database-fetch-and-analyze",
        inputs={
            "plddt_scores": InputSpecification(
                name="plddt_scores",
                semantic_type=SemanticInputType.PDB_STRUCTURE.value,
                required=True,
                description="Per-residue or global pLDDT structural confidence scores.",
            ),
        },
        preconditions=[
            Precondition(
                id="BNS-STR-001",
                rule="plddt_in_valid_range",
                description="pLDDT scores must lie in [0, 100].",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="biopython",
            import_name="Bio",
            minimum_version="1.80",
            description="BioPython PDB/mmCIF structural parser and B-factor auditor.",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="REFUSE-IDR-POCKET-001",
                description="Asserting a rigid binding pocket on an intrinsically disordered region (pLDDT < 50).",
                remedy="Abstain from rigid pocket assertions; model disordered ensemble or test induced folding.",
                violated_rule="AlphaFold pLDDT < 50 disorder invariant",
            ),
        ],
        outputs=[
            "confidence_assessment (StructureConfidenceAssessment)",
            "evidence_card (EvidenceCard)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "pLDDT < 50 indicates intrinsic disorder and cannot support fixed pocket claims.",
                "Predicted structures do not substitute for experimental crystallography / cryo-EM.",
                "Research Use Only. Not for clinical decision-making.",
            ],
        ),
        forbidden_claims=[
            "crystallographic_ground_truth",
            "clinical_diagnosis",
        ],
        evidence_ceiling_without_external_validation="SUPPORTED",
    ),
    "bioactivity.affinity_audit": CapabilityContract(
        id="bioactivity.affinity_audit",
        display_name="Small-Molecule Bioactivity & Affinity Epistemic Audit",
        intent=["chembl_bioactivity_audit", "affinity_potency_tiering", "dose_response_verification"],
        skill_name="chembl-database",
        inputs={
            "affinity_value": InputSpecification(
                name="affinity_value",
                semantic_type=SemanticInputType.INSTRUMENT_TABLE.value,
                required=True,
                description="Binding affinity or functional inhibition measurement value.",
            ),
        },
        preconditions=[
            Precondition(
                id="BNS-BIO-001",
                rule="positive_affinity_measurement",
                description="Affinity value in nanomolar must be strictly positive.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="chembl_webresource_client",
            import_name="chembl_webresource_client",
            description="ChEMBL API client and bioactivity validator.",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="REFUSE-INACTIVE-LEAD-001",
                description="Asserting potent targeted inhibition for compound with IC50/Kd > 10 µM.",
                remedy="Abstain from targeted lead claims; activities > 10 µM are non-specific.",
                violated_rule="Medicinal chemistry 10 µM non-specific threshold",
            ),
        ],
        outputs=[
            "bioactivity_assessment (BioactivityAssessment)",
            "evidence_card (EvidenceCard)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "Affinity > 10 µM is non-specific or inactive in standard medicinal chemistry.",
                "Single-concentration primary screening requires confirmatory multi-point titration.",
                "Research Use Only. Not for clinical therapeutic use.",
            ],
        ),
        forbidden_claims=[
            "potent_lead_from_weak_binding",
            "clinical_diagnosis",
        ],
        evidence_ceiling_without_external_validation="SUPPORTED",
    ),
}

# ==============================================================================
# Frontier / Experimental Capabilities (BNS-010 / Research Track)
# Segregated from Stable Canonical v1.0 Release.
# ==============================================================================


