"""Experimental command handlers, extracted without changing command semantics."""


from __future__ import annotations

import argparse
import json


def handle_closed_loop(args: argparse.Namespace) -> int:
    import json

    import anndata as ad

    from bionexus.closed_loop import (
        GEARSPerturbationConfig,
        NicheFormerConfig,
        forecast_spatial_niche,
        predict_gears_perturbation,
        run_perturbation_to_niche_closed_loop,
    )

    action = getattr(args, "closed_loop_action", None)
    if action == "gears":
        adata = ad.read_h5ad(args.input)
        target_genes = [g.strip() for g in args.genes.split(",") if g.strip()]
        cfg = GEARSPerturbationConfig(target_genes=target_genes, mode=args.mode)
        adata_pert, res = predict_gears_perturbation(adata, target_genes=target_genes, mode=args.mode, config=cfg)
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
            return 0 if res.success else 1
        print("\n=== BioNexus GEARS Perturbation Prediction ===")
        print(f"Status:               {res.status}")
        print(f"Target Gene(s):       {', '.join(res.target_genes)} ({res.perturbation_mode.upper()})")
        print(f"Cells Predicted:      {res.n_cells_predicted:,}")
        print(f"Top Upregulated:      {', '.join(res.top_upregulated_genes)}")
        print(f"Top Downregulated:    {', '.join(res.top_downregulated_genes)}")
        print(f"Backend Used:         {res.backend_used}")
        for note in res.execution_notes:
            print(f"  Note: {note}")
        if args.output:
            adata_pert.write_h5ad(args.output)
            print(f"Saved perturbed dataset to: {args.output}")
        return 0 if res.success else 1

    elif action == "nicheformer":
        adata_cells = ad.read_h5ad(args.cells)
        adata_spatial = ad.read_h5ad(args.spatial)
        cfg = NicheFormerConfig(n_niche_classes=args.niches)
        ad_sp, res = forecast_spatial_niche(adata_cells, adata_spatial, config=cfg)
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
            return 0 if res.success else 1
        print("\n=== BioNexus NicheFormer Spatial Niche Forecast ===")
        print(f"Status:               {res.status}")
        print(f"Spots Evaluated:      {res.n_spots:,}")
        print(f"Niche Types:          {res.n_niche_types}")
        print(f"Dominant Breakdown:   {res.dominant_niche_distribution}")
        print(f"Backend Used:         {res.backend_used}")
        for note in res.execution_notes:
            print(f"  Note: {note}")
        if args.output:
            ad_sp.write_h5ad(args.output)
            print(f"Saved spatial dataset with niches to: {args.output}")
        return 0 if res.success else 1

    elif action == "run":
        adata_cells = ad.read_h5ad(args.cells)
        adata_spatial = ad.read_h5ad(args.spatial)
        target_genes = [g.strip() for g in args.genes.split(",") if g.strip()]
        res = run_perturbation_to_niche_closed_loop(
            adata_cells=adata_cells,
            adata_spatial=adata_spatial,
            target_genes=target_genes,
            mode=args.mode,
        )
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
            return 0 if res.success else 1
        print("\n=== BioNexus Dry-Wet Closed-Loop Evaluation Pipeline ===")
        print(f"Status:               {res.status}")
        print(f"Target Perturbation:  {', '.join(res.target_perturbation)} ({res.perturbation_mode.upper()})")
        print("\nSpatial Niche Remodeling Shifts:")
        for niche, score in res.top_remodeled_niches:
            print(f"  * {niche:<32}: {score:+.2%}")
        print("\nWet-Lab Hypothesis & Validation Protocol:")
        for hyp in res.wet_lab_hypothesis_card.get("primary_hypotheses", []):
            print(f"  [Hypothesis] {hyp}")
        for assay in res.wet_lab_hypothesis_card.get("recommended_wet_lab_assays", []):
            print(f"  [Assay]      {assay}")
        for note in res.execution_notes:
            print(f"  Note: {note}")
        return 0 if res.success else 1

    return 0


def handle_causal(args: argparse.Namespace) -> int:
    from bionexus.causal_dag import CausalDAG, NodeType

    action = getattr(args, "causal_action", "check")
    if action != "check":
        print(f"Unknown causal action: {action}")
        return 2

    dag = CausalDAG()
    treatment = args.treatment.strip()
    outcome = args.outcome.strip()
    dag.add_node(treatment, NodeType.TREATMENT)
    dag.add_node(outcome, NodeType.OUTCOME)
    dag.add_edge(treatment, outcome, directed=True)

    if getattr(args, "confounders", ""):
        for c in args.confounders.split(","):
            c = c.strip()
            if c:
                dag.add_node(c, NodeType.OBSERVED_CONFOUNDER)
                dag.add_edge(c, treatment, directed=True)
                dag.add_edge(c, outcome, directed=True)

    conditioned_set = set()
    if getattr(args, "conditioned", ""):
        for z in args.conditioned.split(","):
            z = z.strip()
            if z:
                conditioned_set.add(z)
                if z not in dag.nodes:
                    dag.add_node(z, NodeType.COVARIATE)

    claim_class = getattr(args, "claim_class", "causal")
    res = dag.evaluate_causal_claim(
        treatment=treatment,
        outcome=outcome,
        conditioned_set=conditioned_set,
        requested_claim_class=claim_class,
    )

    if getattr(args, "json", False):
        print(json.dumps(res.to_dict(), indent=2, ensure_ascii=False))
    else:
        print("=" * 60)
        print("BioNexus Structural Causal Identifiability Evaluation")
        print("=" * 60)
        print(f"Treatment: {treatment} -> Outcome: {outcome}")
        print(f"Requested Claim: {res.requested_claim_class.upper()}")
        print(f"Warranted Status: {'WARRANTED' if res.is_warranted else 'NOT_WARRANTED_AS_REQUESTED'}")
        print(f"Warranted Claim: {res.warranted_claim_class.upper()} (Ceiling: {res.maturity_ceiling})")
        if res.violations:
            print("\nViolations / Open Biases:")
            for v in res.violations:
                print(f"  [!] {v}")
        if res.recommended_adjustment_set:
            print(f"\nRecommended Adjustment Set: {res.recommended_adjustment_set}")
        print(f"\nRationale: {res.rationale}")
        print("=" * 60)
    return 0 if res.is_warranted else 1


def handle_remediate(args: argparse.Namespace) -> int:
    from bionexus.remediation import generate_prescription_for_violation

    violation_id = getattr(args, "violation", "BN-F006")
    n_samples = getattr(args, "n_samples", 2)
    log2fc = getattr(args, "log2fc", 1.0)
    disp = getattr(args, "dispersion", 0.25)

    meta = {
        "n_donors_min": n_samples,
        "target_log2fc": log2fc,
        "dispersion": disp,
    }
    prescription = generate_prescription_for_violation(violation_id, meta)

    if getattr(args, "json", False):
        print(json.dumps(prescription.to_dict(), indent=2, ensure_ascii=False))
    else:
        print("=" * 60)
        print("BioNexus Prescriptive Study Design Remediation")
        print("=" * 60)
        print(f"Violation: {prescription.violation_id}")
        print(f"Primary Strategy: {prescription.primary_strategy}")
        print(f"Current State: {prescription.current_state_summary}")
        print(f"Target Maturity: {prescription.target_maturity}")
        if prescription.minimum_required_samples > 0:
            print(f"Required Samples: N={prescription.minimum_required_samples} (Need +{prescription.additional_samples_needed} more)")
        if prescription.power_assessment:
            p = prescription.power_assessment
            print(f"Statistical Power: {p.power:.1%} (alpha={p.alpha}, log2FC={p.target_log2fc}, dispersion={p.dispersion})")
        print("\nPrescription Recipe:")
        print(f"  {prescription.remediation_text}")
        if prescription.analytical_remedies:
            print("\nAnalytical Remedies:")
            for r in prescription.analytical_remedies:
                print(f"  - {r}")
        if prescription.academic_citations:
            print("\nAcademic Citations:")
            for c in prescription.academic_citations:
                print(f"  * {c}")
        print("=" * 60)
    return 0


def register_closed_loop_arguments(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    # 14. closed-loop (Dry-Wet Closed Loop: GEARS Perturbation to NicheFormer Spatial Niche)
    p_closed = subparsers.add_parser("closed-loop", aliases=["closed_loop"], help="Dry-Wet closed loop perturbation to spatial niche tools")
    closed_subs = p_closed.add_subparsers(dest="closed_loop_action", help="Closed-loop actions")

    # closed-loop gears
    p_cl_gears = closed_subs.add_parser("gears", help="Simulate combinatorial in silico genetic perturbation with GEARS")
    p_cl_gears.add_argument("input", help="Path to single-cell .h5ad baseline dataset")
    p_cl_gears.add_argument("--genes", required=True, help="Comma-separated target gene symbols (e.g. TP53 or MYC,CDKN1A)")
    p_cl_gears.add_argument("--mode", default="knockout", choices=["knockout", "overexpression"], help="Perturbation mode")
    p_cl_gears.add_argument("--output", "-o", default=None, help="Optional output path to save perturbed .h5ad dataset")
    p_cl_gears.add_argument("--json", action="store_true", help="Output result as JSON")

    # closed-loop nicheformer
    p_cl_niche = closed_subs.add_parser("nicheformer", help="Forecast spatial microenvironment / niche distributions with NicheFormer")
    p_cl_niche.add_argument("--cells", required=True, help="Path to single-cell .h5ad dataset")
    p_cl_niche.add_argument("--spatial", required=True, help="Path to spatial .h5ad dataset with obsm['spatial']")
    p_cl_niche.add_argument("--niches", type=int, default=5, help="Number of spatial niche classes")
    p_cl_niche.add_argument("--output", "-o", default=None, help="Optional output path to save updated spatial dataset")
    p_cl_niche.add_argument("--json", action="store_true", help="Output forecast result as JSON")

    # closed-loop run
    p_cl_run = closed_subs.add_parser("run", help="Run full closed-loop pipeline from perturbation to spatial niche remodeling")
    p_cl_run.add_argument("--cells", required=True, help="Path to single-cell .h5ad baseline dataset")
    p_cl_run.add_argument("--spatial", required=True, help="Path to spatial reference .h5ad dataset")
    p_cl_run.add_argument("--genes", required=True, help="Comma-separated target gene symbols (e.g. TP53,CDKN1A)")
    p_cl_run.add_argument("--mode", default="knockout", choices=["knockout", "overexpression"], help="Perturbation mode")
    return p_closed


def register_causal_arguments(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    # 17. causal (Structural Causal DAG & Identifiability)
    p_causal = subparsers.add_parser("causal", help="Structural Causal DAG, d-separation, and backdoor identification")
    causal_subs = p_causal.add_subparsers(dest="causal_action", help="Causal actions")
    p_causal_check = causal_subs.add_parser("check", help="Evaluate if a causal claim is warranted given DAG structure")
    p_causal_check.add_argument("--treatment", "-t", required=True, help="Treatment variable name")
    p_causal_check.add_argument("--outcome", "-y", required=True, help="Outcome variable name")
    p_causal_check.add_argument("--confounders", "-c", default="", help="Comma-separated observed confounders")
    p_causal_check.add_argument("--conditioned", "-z", default="", help="Comma-separated conditioned variables")
    p_causal_check.add_argument(
        "--claim-class",
        default="causal",
        choices=["causal", "mechanistic", "association", "population_effect", "descriptive"],
        help="Requested claim class",
    )
    p_causal_check.add_argument("--json", action="store_true", help="Output result as JSON")
    return p_causal


def register_remediate_arguments(subparsers: argparse._SubParsersAction) -> None:
    # 18. remediate (Prescriptive Power & Study Design Remediation)
    p_remediate = subparsers.add_parser("remediate", help="Prescriptive study design and power remediation calculations")
    p_remediate.add_argument("--violation", "-v", default="BN-F006", help="Violation ID (e.g. BN-F006, BN-F001, BN-F005)")
    p_remediate.add_argument("--n-samples", "-n", type=int, default=2, help="Current replicates per group")
    p_remediate.add_argument("--log2fc", type=float, default=1.0, help="Target effect size log2FC")
    p_remediate.add_argument("--dispersion", type=float, default=0.25, help="Biological dispersion")
    p_remediate.add_argument("--power", action="store_true", help="Perform quantitative power calculation")
    p_remediate.add_argument("--json", action="store_true", help="Output prescription as JSON")
