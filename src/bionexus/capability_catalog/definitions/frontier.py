"""
Static contract definitions for Frontier Bioinformatics Capabilities.
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

FRONTIER_CAPABILITIES: Dict[str, CapabilityContract] = {
    # 14. Single-Cell Foundation Model Geneformer Official Inference (Frontier)
    "scfm.geneformer_canonical": CapabilityContract(
        id="scfm.geneformer_canonical",
        version=1,
        display_name="Single-Cell Geneformer Foundation Model Official Inference (Checkpoint Required)",
        skill_name="single-cell-rna-qc",
        summary="Canonical Geneformer rank-value Transformer inference using official pretrained checkpoints (ctheodoris/Geneformer).",
        intent=[
            "geneformer_canonical",
            "geneformer_embedding",
            "geneformer_inference",
            "geneformer_perturbation",
            "foundation_model_embedding",
        ],
        inputs={
            "expression": InputSpecification(
                name="expression",
                semantic_type=SemanticInputType.RAW_COUNTS.value,
                required=True,
                description="Single-cell expression matrix (.h5ad / counts).",
            ),
            "model_checkpoint": InputSpecification(
                name="model_checkpoint",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=True,
                description="Path to official pretrained Geneformer checkpoint (e.g. 'ctheodoris/Geneformer' or local weights dir).",
            ),
        },
        preconditions=[
            Precondition(
                id="non_empty_matrix",
                rule="n_cells > 0 and n_genes > 0",
                description="Input single-cell dataset must not be empty.",
                fatal_if_violated=True,
            ),
            Precondition(
                id="checkpoint_specified",
                rule="model_checkpoint is not None",
                description="Canonical Geneformer execution strictly requires an official pretrained model checkpoint.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="geneformer-transformers",
            import_name="transformers",
            minimum_version="4.30.0",
            extra="scverse",
            entry_points=("transformers.AutoModel", "transformers.AutoConfig"),
            description="Geneformer rank-value Transformer neural network with official checkpoint weights",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="missing_checkpoint",
                description="No official Geneformer model checkpoint or weights directory was provided.",
                remedy="Provide official model checkpoint via `model_name_or_path` (e.g. 'ctheodoris/Geneformer' or local dir), or invoke `scfm.rank_proxy_embedding` for Grade C heuristic proxy.",
                violated_rule="Official model checkpoint invariant (BNS-EF-002)",
            ),
            RefusalTrigger(
                condition_id="empty_matrix",
                description="Dataset contains 0 cells or 0 genes.",
                remedy="Provide valid single-cell AnnData count matrix.",
                violated_rule="Matrix non-emptiness rule",
            ),
        ],
        outputs=[
            "cell_embeddings (adata.obsm['X_geneformer'])",
            "perturbation_report (JSON/CSV)",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "Zero-shot embeddings and in silico perturbation shifts are computational hypotheses.",
                "Official model weights must be loaded and disclosed in provenance.",
                "Research Use Only. Not for clinical diagnosis.",
            ],
        ),
        forbidden_claims=[
            "model_substitution",
            "clinical_diagnosis",
            "causal_interaction",
            "cell_type_identity_without_reference",
        ],
        evidence_ceiling_without_external_validation="PRELIMINARY",
    ),
    # 15. Single-Cell Foundation Model scGPT Official Inference (Frontier)
    "scfm.scgpt_canonical": CapabilityContract(
        id="scfm.scgpt_canonical",
        version=1,
        display_name="Single-Cell scGPT Foundation Model Official Inference (Checkpoint Required)",
        skill_name="single-cell-rna-qc",
        summary="Canonical scGPT Generative Transformer inference using official pretrained checkpoints.",
        intent=[
            "scgpt_canonical",
            "scgpt_embedding",
            "scgpt_inference",
            "scgpt_representation",
        ],
        inputs={
            "expression": InputSpecification(
                name="expression",
                semantic_type=SemanticInputType.RAW_COUNTS.value,
                required=True,
                description="Single-cell expression matrix (.h5ad / counts).",
            ),
            "model_checkpoint": InputSpecification(
                name="model_checkpoint",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=True,
                description="Path to official pretrained scGPT checkpoint weights.",
            ),
        },
        preconditions=[
            Precondition(
                id="non_empty_matrix",
                rule="n_cells > 0 and n_genes > 0",
                description="Input single-cell dataset must not be empty.",
                fatal_if_violated=True,
            ),
            Precondition(
                id="checkpoint_specified",
                rule="model_checkpoint is not None",
                description="Canonical scGPT execution strictly requires an official pretrained model checkpoint.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="scgpt-transformers",
            import_name="transformers",
            minimum_version="4.30.0",
            extra="scverse",
            entry_points=("transformers.AutoModel", "transformers.AutoConfig"),
            description="scGPT generative Transformer neural network with official checkpoint weights",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="missing_checkpoint",
                description="No official scGPT model checkpoint or weights directory was provided.",
                remedy="Provide official scGPT weights directory, or invoke `scfm.rank_proxy_embedding` for Grade C heuristic proxy.",
                violated_rule="Official model checkpoint invariant (BNS-EF-002)",
            ),
        ],
        outputs=[
            "cell_embeddings (adata.obsm['X_scgpt'])",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "scGPT representations are high-dimensional latent embeddings.",
                "Research Use Only. Not for clinical diagnosis.",
            ],
        ),
        forbidden_claims=[
            "model_substitution",
            "clinical_diagnosis",
            "causal_interaction",
            "cell_type_identity_without_reference",
        ],
        evidence_ceiling_without_external_validation="PRELIMINARY",
    ),
    # 16. Single-Cell Rank-Value SVD Embedding Proxy (Grade C Experimental Frontier)
    "scfm.rank_proxy_embedding": CapabilityContract(
        id="scfm.rank_proxy_embedding",
        version=1,
        display_name="Single-Cell Rank-Value SVD Embedding Proxy (Grade C Experimental)",
        skill_name="single-cell-rna-qc",
        summary="Grade C Experimental: Rank-weighted Truncated SVD embedding proxy for exploratory zero-shot manifold visualization without neural network checkpoints.",
        intent=[
            "rank_proxy_embedding",
            "rank_embedding",
            "scfm_proxy",
            "rank_value_svd",
            "heuristic_rank_embedding",
        ],
        inputs={
            "expression": InputSpecification(
                name="expression",
                semantic_type=SemanticInputType.RAW_COUNTS.value,
                required=True,
                description="Single-cell expression matrix (.h5ad / counts).",
            ),
        },
        preconditions=[
            Precondition(
                id="non_empty_matrix",
                rule="n_cells > 0 and n_genes > 0",
                description="Input single-cell dataset must not be empty.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="local rank-svd heuristic proxy (bionexus)",
            import_name="bionexus.scfm",
            minimum_version="0.9.0",
            entry_points=("bionexus.scfm",),
            description="Deterministic rank-weighted Truncated SVD heuristic proxy (Grade C)",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="model_substitution_attempt",
                description="Attempting to cite or present Rank-SVD proxy output as official Geneformer or scGPT Transformer output.",
                remedy="Acknowledge output as a Grade C experimental rank-weighted SVD proxy, not an official foundation model checkpoint.",
                violated_rule="Epistemic honesty and model attribution invariant (BNS-EF-002)",
            ),
        ],
        outputs=[
            "cell_embeddings (adata.obsm['X_rank_proxy'])",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "Grade C Experimental proxy only. Does not execute deep Transformer attention mechanisms.",
                "Research Use Only. Not for clinical diagnosis.",
            ],
        ),
        forbidden_claims=[
            "model_substitution",
            "clinical_diagnosis",
            "causal_interaction",
            "cell_type_identity_without_reference",
        ],
        evidence_ceiling_without_external_validation="PRELIMINARY",
    ),
    # 17. GEARS Combinatorial Genetic Perturbation Prediction (Frontier)
    "perturbation.gears_prediction": CapabilityContract(
        id="perturbation.gears_prediction",
        version=1,
        display_name="GEARS Graph-Enhanced Single-Cell Genetic Perturbation Modeling",
        skill_name="single-cell-rna-qc",
        summary="Predict post-perturbation transcriptomic states and downstream gene shifts under genetic knockouts or overexpressions using GNNs.",
        intent=[
            "gears_perturbation",
            "genetic_perturbation_prediction",
            "combinatorial_knockout",
            "in_silico_crispr",
        ],
        inputs={
            "expression": InputSpecification(
                name="expression",
                semantic_type=SemanticInputType.RAW_COUNTS.value,
                required=True,
                description="Baseline single-cell expression matrix (.h5ad / counts).",
            ),
        },
        preconditions=[
            Precondition(
                id="non_empty_matrix",
                rule="n_cells > 0 and n_genes > 0",
                description="Input single-cell dataset must not be empty.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="gears",
            import_name="gears",
            minimum_version="0.1.0",
            extra="scverse",
            entry_points=("gears",),
            description="GEARS Graph-Enhanced Perturbation Prediction GNN",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="empty_matrix",
                description="Dataset contains 0 cells or 0 genes.",
                remedy="Provide valid single-cell AnnData count matrix.",
                violated_rule="Matrix non-emptiness rule",
            ),
            RefusalTrigger(
                condition_id="missing_target_genes",
                description="Target perturbation genes are not present in dataset.",
                remedy="Check gene symbol spelling or provide full transcriptome matrix.",
                violated_rule="Target gene presence rule",
            ),
        ],
        outputs=[
            "predicted_perturbed_matrix (adata_perturbed.X)",
            "top_upregulated_genes (List[str])",
            "top_downregulated_genes (List[str])",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "GEARS in silico perturbation shifts are computational predictions.",
                "Experimental validation via CRISPR knockout or qPCR is mandatory.",
                "Research Use Only. Not for clinical diagnosis.",
            ],
        ),
        forbidden_claims=[
            "model_substitution",
            "clinical_diagnosis",
            "causal_interaction",
            "cell_type_identity_without_reference",
        ],
        evidence_ceiling_without_external_validation="PRELIMINARY",
    ),
    # 18. NicheFormer Spatial Niche Forecasting (Frontier)
    "spatial.nicheformer_forecasting": CapabilityContract(
        id="spatial.nicheformer_forecasting",
        version=1,
        display_name="NicheFormer Spatial Microenvironment & Niche Forecasting",
        skill_name="spatial-transcriptomics",
        summary="Forecast spatial niche composition, microenvironment boundaries, and cellular neighborhood shifts using foundation models.",
        intent=[
            "nicheformer_forecasting",
            "spatial_niche_prediction",
            "microenvironment_forecasting",
            "spatial_niche_remodeling",
        ],
        inputs={
            "expression": InputSpecification(
                name="expression",
                semantic_type=SemanticInputType.RAW_COUNTS.value,
                required=True,
                description="Single-cell or spot expression matrix (.h5ad).",
            ),
            "spatial_coordinates": InputSpecification(
                name="spatial_coordinates",
                semantic_type=SemanticInputType.SPATIAL_COORDINATES.value,
                required=True,
                description="Spatial coordinates in adata.obsm['spatial'].",
            ),
        },
        preconditions=[
            Precondition(
                id="spatial_coordinates_present",
                rule="'spatial' in adata.obsm",
                description="Spatial reference must contain 2D coordinates.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="nicheformer",
            import_name="nicheformer",
            minimum_version="0.1.0",
            extra="scverse",
            entry_points=("nicheformer",),
            description="NicheFormer Spatial Microenvironment Foundation Model",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="missing_coordinates",
                description="Dataset lacks 2D coordinates in obsm['spatial'].",
                remedy="Provide spatial AnnData with valid obsm['spatial'] matrix.",
                violated_rule="Spatial geometry requirement",
            ),
        ],
        outputs=[
            "niche_proportions (adata_spatial.obsm['nicheformer_niche_pred'])",
            "dominant_niche (adata_spatial.obs['dominant_niche'])",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "NicheFormer spatial compositions are in silico exploratory forecasts.",
                "Research Use Only. Not for clinical diagnosis.",
            ],
        ),
        forbidden_claims=[
            "model_substitution",
            "clinical_diagnosis",
            "causal_interaction",
            "cell_type_identity_without_reference",
        ],
        evidence_ceiling_without_external_validation="PRELIMINARY",
    ),
    # 19. Dry-Wet Closed Loop Perturbation to Spatial Niche (Frontier)
    "closed_loop.perturbation_to_niche": CapabilityContract(
        id="closed_loop.perturbation_to_niche",
        version=1,
        display_name="Dry-Wet Closed Loop: Perturbation -> Spatial Niche Remodeling",
        skill_name="spatial-transcriptomics",
        summary="Chains GEARS genetic perturbation with NicheFormer spatial microenvironment forecasting into an actionable wet-lab validation card.",
        intent=[
            "dry_wet_closed_loop",
            "perturbation_to_spatial_niche",
            "niche_remodeling_closed_loop",
            "wet_lab_validation_handoff",
        ],
        inputs={
            "expression": InputSpecification(
                name="expression",
                semantic_type=SemanticInputType.RAW_COUNTS.value,
                required=True,
                description="Baseline single-cell expression matrix (.h5ad).",
            ),
            "spatial_coordinates": InputSpecification(
                name="spatial_coordinates",
                semantic_type=SemanticInputType.SPATIAL_COORDINATES.value,
                required=True,
                description="Spatial reference coordinates in adata_spatial.obsm['spatial'].",
            ),
        },
        preconditions=[
            Precondition(
                id="non_empty_matrix",
                rule="n_cells > 0 and n_genes > 0",
                description="Input single-cell dataset must not be empty.",
                fatal_if_violated=True,
            ),
            Precondition(
                id="spatial_coordinates_present",
                rule="'spatial' in adata_spatial.obsm",
                description="Spatial reference must contain 2D coordinates.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="bionexus-closed-loop",
            import_name="gears",
            minimum_version="0.1.0",
            extra="scverse",
            entry_points=("gears", "bionexus.closed_loop"),
            description="BioNexus GEARS + NicheFormer Closed-Loop Integration Pipeline",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="empty_matrix",
                description="Dataset contains 0 cells or 0 genes.",
                remedy="Provide valid single-cell AnnData count matrix.",
                violated_rule="Matrix non-emptiness rule",
            ),
            RefusalTrigger(
                condition_id="missing_coordinates",
                description="Spatial reference lacks 2D coordinates.",
                remedy="Provide spatial AnnData with valid obsm['spatial'] matrix.",
                violated_rule="Spatial geometry requirement",
            ),
        ],
        outputs=[
            "remodeling_scores (Dict[str, float])",
            "wet_lab_hypothesis_card (JSON/Markdown)",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "Closed-loop perturbation-to-niche forecasts are computational hypotheses.",
                "Wet-lab validation is required prior to translational claims.",
                "Research Use Only. Not for clinical diagnosis.",
            ],
        ),
        forbidden_claims=[
            "model_substitution",
            "clinical_diagnosis",
            "causal_interaction",
            "cell_type_identity_without_reference",
        ],
        evidence_ceiling_without_external_validation="PRELIMINARY",
    ),
}


