"""
BioNexus Machine-Readable Scientific Capability Contracts.

Defines formal, machine-actionable contracts for biological analyses:
- Input semantic requirements (e.g. raw integer counts vs normalized continuous scales)
- Preconditions (e.g. minimum biological replicates, non-degenerate coordinates)
- Canonical backend specifications
- Deterministic refusal triggers & actionable remedies
- Evidence requirements & mandatory limitations

Enables AI Coding Agents to understand *when an analysis is scientifically valid*
and *when it is scientifically invalid and must be refused*.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from bionexus.backends import probe
from bionexus.contracts import (
    ConclusionMaturity,
    DimensionGrade,
    EvidenceCard,
    ExecutionState,
)


class SemanticInputType(str, Enum):
    """Semantic data type expected for analytical inputs."""

    RAW_COUNTS = "raw_counts"  # Non-negative integer count matrix
    NORMALIZED_MATRIX = "normalized_matrix"  # Log-normalized / scaled continuous expression
    SPATIAL_COORDINATES = "spatial_coordinates"  # 2D/3D spot/cell centroid coordinates
    SAMPLE_METADATA = "sample_metadata"  # Per-sample/cell covariate annotations
    VARIANT_RECORDS = "variant_records"  # HGVS, VCF, or genomic variant coordinates
    SURVIVAL_DATA = "survival_data"  # Time-to-event and censoring indicators
    INSTRUMENT_TABLE = "instrument_table"  # Raw analytical instrument output (plate reader, chromatography)
    PROTEIN_SEQUENCE = "protein_sequence"  # Amino acid sequence string / FASTA
    PDB_STRUCTURE = "pdb_structure"  # 3D atomic coordinates (PDB/mmCIF)


@dataclass
class InputSpecification:
    """Specification of an input artifact and its semantic requirements."""

    name: str
    semantic_type: str
    required: bool = True
    description: str = ""
    validation_rule: Optional[str] = None


@dataclass
class Precondition:
    """Mathematical or biological invariant required before execution."""

    id: str
    rule: str
    description: str
    fatal_if_violated: bool = True


@dataclass
class BackendRequirement:
    """Canonical community package required for gold-standard execution."""

    canonical_name: str
    import_name: str
    minimum_version: Optional[str] = None
    extra: Optional[str] = None
    description: str = ""


@dataclass
class RefusalTrigger:
    """Condition that deterministically mandates an agent refusal with scientific justification."""

    condition_id: str
    description: str
    remedy: str
    violated_rule: str


@dataclass
class EvidenceRequirement:
    """Evidence criteria that must be reported in the output EvidenceCard."""

    multiple_testing: str = "required"  # "required" | "recommended" | "optional"
    effect_size: str = "required"
    min_fdr_alpha: float = 0.05
    uncertainty_quantification: str = "recommended"
    mandatory_limitations: List[str] = field(default_factory=list)


@dataclass
class CapabilityContract:
    """
    Machine-readable Scientific Capability Contract.
    """

    id: str
    version: int = 1
    display_name: str = ""
    skill_name: str = ""
    summary: str = ""
    intent: List[str] = field(default_factory=list)
    inputs: Dict[str, InputSpecification] = field(default_factory=dict)
    preconditions: List[Precondition] = field(default_factory=list)
    backend: BackendRequirement = field(
        default_factory=lambda: BackendRequirement(
            canonical_name="none", import_name="none"
        )
    )
    refusal_conditions: List[RefusalTrigger] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    evidence_requirements: EvidenceRequirement = field(
        default_factory=EvidenceRequirement
    )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize contract to dictionary."""
        return asdict(self)

    def evaluate_viability(
        self,
        *,
        input_metadata: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> CapabilityEvaluationResult:
        """
        Evaluate whether the requested analysis is scientifically valid.
        """
        meta = input_metadata or {}
        violations: List[str] = []
        triggered_refusals: List[RefusalTrigger] = []
        remedies: List[str] = []

        # 1. Input Semantic Check
        for inp_name, inp_spec in self.inputs.items():
            if inp_spec.required:
                present = meta.get(f"{inp_name}_present", True)
                if not present:
                    violations.append(f"Missing required input '{inp_name}'")
                    remedies.append(f"Provide valid input artifact for '{inp_name}' ({inp_spec.semantic_type}).")

                # Semantic type verification
                if inp_spec.semantic_type == SemanticInputType.RAW_COUNTS.value:
                    if meta.get("is_normalized") is True or meta.get("is_integer_like") is False:
                        trigger = next(
                            (r for r in self.refusal_conditions if r.condition_id == "normalized_matrix_only"),
                            RefusalTrigger(
                                condition_id="normalized_matrix_only",
                                description="Input matrix contains normalized continuous floats where raw integer counts are required.",
                                remedy="Provide raw un-normalized count matrix (e.g. adata.raw.X or raw integer counts layer).",
                                violated_rule="Raw integer counts distribution assumption",
                            ),
                        )
                        triggered_refusals.append(trigger)
                        violations.append(trigger.description)
                        remedies.append(trigger.remedy)

        # 2. Precondition Evaluation
        # Minimum replicates check
        min_reps = meta.get("min_replicates_per_condition")
        if min_reps is not None and min_reps < 2:
            trigger = next(
                (r for r in self.refusal_conditions if r.condition_id == "missing_replicates"),
                RefusalTrigger(
                    condition_id="missing_replicates",
                    description=f"Found {min_reps} replicates per condition, minimum required is 2.",
                    remedy="Condition differential expression requires at least 2 biological replicates per group to estimate within-group biological dispersion.",
                    violated_rule="Biological replicate requirement",
                ),
            )
            triggered_refusals.append(trigger)
            violations.append(trigger.description)
            remedies.append(trigger.remedy)

        # Spatial spots check
        n_spots = meta.get("n_spatial_spots")
        if n_spots is not None and n_spots < 5:
            trigger = next(
                (r for r in self.refusal_conditions if r.condition_id == "insufficient_spatial_spots"),
                RefusalTrigger(
                    condition_id="insufficient_spatial_spots",
                    description=f"Found {n_spots} spatial spots, minimum required is 5 for graph construction.",
                    remedy="Provide spatial dataset with sufficient spatial coordinate entries.",
                    violated_rule="Spatial neighborhood graph connectivity",
                ),
            )
            triggered_refusals.append(trigger)
            violations.append(trigger.description)
            remedies.append(trigger.remedy)

        # Spatial coordinate variance check
        if meta.get("coordinate_variance_zero") is True:
            trigger = RefusalTrigger(
                condition_id="degenerate_spatial_coordinates",
                description="Spatial coordinates have zero variance along spatial axes.",
                remedy="Provide non-degenerate spatial coordinates with varied positions.",
                violated_rule="Spatial geometry variance invariant",
            )
            triggered_refusals.append(trigger)
            violations.append(trigger.description)
            remedies.append(trigger.remedy)

        # Survival zero events check
        if meta.get("n_events") == 0:
            trigger = next(
                (r for r in self.refusal_conditions if r.condition_id == "all_censored"),
                RefusalTrigger(
                    condition_id="all_censored",
                    description="Zero events observed in cohort (100% censoring).",
                    remedy="Survival estimation requires at least one uncensored event.",
                    violated_rule="Event observation requirement",
                ),
            )
            triggered_refusals.append(trigger)
            violations.append(trigger.description)
            remedies.append(trigger.remedy)

        # 3. Backend Probe Check
        backend_name = self.backend.import_name
        if backend_name and backend_name != "none":
            status = probe(backend_name)
            if not status.available:
                trigger = next(
                    (r for r in self.refusal_conditions if r.condition_id == "missing_backend"),
                    RefusalTrigger(
                        condition_id="missing_backend",
                        description=f"Required gold-standard backend '{self.backend.canonical_name}' is not installed.",
                        remedy=f"Install via `pip install bionexus[{self.backend.extra}]` or `pip install {self.backend.import_name}`.",
                        violated_rule="Gold-standard backend requirement",
                    ),
                )
                triggered_refusals.append(trigger)
                violations.append(trigger.description)
                remedies.append(trigger.remedy)

        # 4. Synthesize Evaluation
        permitted = len(triggered_refusals) == 0 and len(violations) == 0
        if not permitted:
            exec_state = ExecutionState.REFUSED.value
            concl_maturity = ConclusionMaturity.ABSTAIN.value
            card = EvidenceCard(
                execution_state=exec_state,
                input_integrity=DimensionGrade.GRADE_C.value if any("normalized" in v.lower() for v in violations) else DimensionGrade.UNTESTED.value,
                assumption_validity=DimensionGrade.GRADE_C.value,
                statistical_support=DimensionGrade.UNTESTED.value,
                details={
                    "contract_id": self.id,
                    "refusal_triggers": [r.condition_id for r in triggered_refusals],
                    "violations": violations,
                },
            )
            status = "REFUSED"
        else:
            exec_state = ExecutionState.EXECUTED.value
            concl_maturity = ConclusionMaturity.SUPPORTED.value
            card = EvidenceCard(
                execution_state=exec_state,
                input_integrity=DimensionGrade.GRADE_A.value,
                assumption_validity=DimensionGrade.GRADE_A.value,
                statistical_support=DimensionGrade.GRADE_A.value,
                details={
                    "contract_id": self.id,
                    "execution_backend": self.backend.canonical_name,
                },
            )
            status = "PERMITTED"

        return CapabilityEvaluationResult(
            capability_id=self.id,
            status=status,
            permitted=permitted,
            violations=violations,
            refusal_triggers=triggered_refusals,
            remedies=remedies,
            evidence_card=card,
            conclusion_maturity=concl_maturity,
        )


@dataclass
class CapabilityEvaluationResult:
    """Result of evaluating a scientific capability contract against execution context."""

    capability_id: str
    status: str  # "PERMITTED" | "REFUSED" | "DEGRADED"
    permitted: bool
    violations: List[str]
    refusal_triggers: List[RefusalTrigger]
    remedies: List[str]
    evidence_card: EvidenceCard
    conclusion_maturity: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert evaluation result to dictionary."""
        return {
            "capability_id": self.capability_id,
            "status": self.status,
            "permitted": self.permitted,
            "violations": self.violations,
            "refusal_triggers": [asdict(r) for r in self.refusal_triggers],
            "remedies": self.remedies,
            "evidence_card": self.evidence_card.to_dict(),
            "conclusion_maturity": self.conclusion_maturity,
        }


# ==============================================================================
# Canonical Scientific Capability Contracts
# ==============================================================================

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
                remedy="Install via `pip install bionexus[deseq]` or `pip install pydeseq2`.",
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
            description="Scanpy single-cell analysis toolkit",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="missing_backend",
                description="Scanpy or anndata is not installed.",
                remedy="Install via `pip install bionexus[goldchain]` or `pip install scanpy anndata`.",
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
                remedy="Install via `pip install bionexus[spatial]` or `pip install squidpy spatialdata`.",
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
                remedy="Install via `pip install bionexus[survival]` or `pip install lifelines`.",
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
                remedy="Install via `pip install bionexus[scverse]` or `pip install scvi-tools torch`.",
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
                remedy="Install via `pip install bionexus[allotrope]` or `pip install allotropy`.",
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
        ],
        inputs={
            "sample_manifest": InputSpecification(
                name="sample_manifest",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=True,
                description="Directory of FASTQ/BAM files or raw sample CSV metadata.",
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
            description="nf-core sample generator and cluster launch compiler",
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
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "Generates deployment configurations; pipeline execution requires Nextflow runtime and container engine (Docker/Singularity).",
            ],
        ),
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
    ),
}


# ==============================================================================
# Helper Query Functions
# ==============================================================================

def get_capability(capability_id: str) -> CapabilityContract:
    """Retrieve capability contract by ID."""
    if capability_id not in CANONICAL_CAPABILITIES:
        raise KeyError(f"Unknown capability contract ID: '{capability_id}'. Available: {list(CANONICAL_CAPABILITIES.keys())}")
    return CANONICAL_CAPABILITIES[capability_id]


def list_capabilities(
    intent: Optional[str] = None,
    skill_name: Optional[str] = None
) -> List[CapabilityContract]:
    """Filter and list capability contracts by intent or skill."""
    caps = list(CANONICAL_CAPABILITIES.values())
    if skill_name:
        caps = [c for c in caps if c.skill_name == skill_name]
    if intent:
        caps = [c for c in caps if intent in c.intent]
    return caps


def find_capabilities_by_intent(intent: str) -> List[CapabilityContract]:
    """Find capabilities matching a specific scientific intent."""
    return list_capabilities(intent=intent)


def evaluate_capability_preconditions(
    capability_id: str,
    *,
    input_metadata: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> CapabilityEvaluationResult:
    """
    Evaluate whether a planned analysis satisfies all scientific preconditions.
    """
    contract = get_capability(capability_id)
    return contract.evaluate_viability(
        input_metadata=input_metadata,
        context=context,
    )
