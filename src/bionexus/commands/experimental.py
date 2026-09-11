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

