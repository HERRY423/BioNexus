"""Execution command handlers, extracted without changing command semantics."""


from __future__ import annotations

import argparse
import json
from pathlib import Path

from bionexus.bigdata import (
    StreamingPseudobulkAggregator,
    audit_dataset_storage,
    estimate_memory_requirements,
    generate_streaming_plan,
)
from bionexus.cluster import (
    CloudNativeBatchProfile,
    ElasticScalePolicy,
    JobResourceConfig,
    diagnose_job_failure,
    generate_job_script,
    generate_tes_task,
    get_job_status,
    probe_cluster_environment,
    submit_job,
)


def handle_run(args: argparse.Namespace) -> int:
    """Handle 'run' subcommands (inspect, verify, list) for Run Capsule Artifact Contracts."""
    from bionexus.artifacts import load_run_bundle, verify_run_bundle

    action = getattr(args, "run_action", None)
    if action == "inspect":
        target = Path(args.path)
        try:
            data = load_run_bundle(target)
        except Exception as e:
            print(f"[ERROR] Failed to load run capsule: {e}")
            return 1

        if getattr(args, "json", False):
            print(json.dumps(data, indent=2))
            return 0

        print("\n============================================================")
        print(f"📦 BioNexus Run Capsule: {data.get('run_id')}")
        print("============================================================")
        print(f"• Capability ID:       {data.get('capability_id')}")
        print(f"• Skill Name:          {data.get('skill_name')}")
        print(f"• Status:              {data.get('status')} ({data.get('execution_state')})")
        print(f"• Conclusion Maturity: {data.get('conclusion_maturity')}")
        print(f"• Duration:            {data.get('duration_seconds')}s")
        print(f"• Start Time:          {data.get('timestamp_start')}")

        artifacts = data.get("artifacts", {})
        print("\n📂 Core Descriptors:")
        for k in (
            "inputs_manifest",
            "parameters_manifest",
            "evidence_card",
            "provenance_sidecar",
            "environment_snapshot",
            "execution_log",
        ):
            val = artifacts.get(k)
            if val:
                print(f"  - {k}: {val}")

        results = artifacts.get("results", [])
        print(f"\n📊 Result Artifacts ({len(results)}):")
        for r in results:
            prim = " [PRIMARY]" if r.get("path") == artifacts.get("primary_result") else ""
            print(f"  - {r.get('name')}: {r.get('path')} ({r.get('semantic_type')}){prim}")

        figures = artifacts.get("figures", [])
        if figures:
            print(f"\n📈 Visualizations ({len(figures)}):")
            for fig in figures:
                print(f"  - {fig.get('title')}: {fig.get('path')} ({fig.get('format')})")

        suggestions = data.get("downstream_suggestions", [])
        if suggestions:
            print(f"\n🤖 Next Agent Actionable Suggestions ({len(suggestions)}):")
            for i, sug in enumerate(suggestions, 1):
                print(f"  {i}. Intent: {sug.get('intent')} -> {sug.get('capability_id')}")
                print(f"     Input:   {sug.get('input_artifact')}")
                print(f"     Command: {sug.get('recommended_command')}")
                if sug.get("rationale"):
                    print(f"     Why:     {sug.get('rationale')}")

        print("============================================================\n")
        return 0

    elif action == "verify":
        target = Path(args.path)
        res = verify_run_bundle(target)
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
            return 0 if res.valid else 1

        print(f"\n=== Verifying Run Capsule: {res.run_id} ===")
        if res.valid:
            print("[PASS] Run capsule is complete, structurally intact, and cryptographically verified.")
            return 0
        else:
            print("[FAIL] Integrity verification failed:")
            for m in res.missing_files:
                print(f"  - MISSING: {m}")
            for t in res.tampered_files:
                print(f"  - TAMPERED: {t}")
            for n in res.notes:
                print(f"  - Note: {n}")
            return 1

    elif action == "list":
        parent = Path(args.path or ".")
        runs = sorted(parent.glob("**/run.json"))
        if not runs:
            print(f"No BioNexus run capsules found in '{parent}'.")
            return 0

        print(f"\nFound {len(runs)} BioNexus Run Capsule(s) in '{parent}':")
        for r_file in runs:
            r_dir = r_file.parent
            try:
                d = json.loads(r_file.read_text(encoding="utf-8"))
                print(
                    f"  • {d.get('run_id')} | Cap: {d.get('capability_id')} | Status: {d.get('status')} | Dir: {r_dir}"
                )
            except Exception:
                print(f"  • [Invalid] Dir: {r_dir}")
        return 0

    return 0


def handle_cluster(args: argparse.Namespace) -> int:
    """Handle bionexus cluster subcommands."""
    action = getattr(args, "cluster_action", None)
    if action == "probe":
        report = probe_cluster_environment()
        if getattr(args, "json", False):
            print(json.dumps(report.to_dict(), indent=2))
            return 0
        print("\n=== BioNexus HPC & Cloud Cluster Environment Probe ===")
        print(f"Default Scheduler:   {report.default_scheduler.upper()}")
        print(f"Available Schedulers: {', '.join(report.available_schedulers) or 'None (local only)'}")
        print(f"Slurm (sbatch):      {'[READY]' if report.has_slurm else '[NOT DETECTED]'}")
        print(f"PBS/Torque (qsub):   {'[READY]' if report.has_pbs else '[NOT DETECTED]'}")
        print(f"LSF (bsub):          {'[READY]' if report.has_lsf else '[NOT DETECTED]'}")
        print(f"Kubernetes (kubectl):{'[READY]' if report.has_kubernetes else '[NOT DETECTED]'}")
        print(f"AWS Batch CLI:       {'[READY]' if report.has_aws_cli else '[NOT DETECTED]'}")
        print(f"GCP Batch CLI:       {'[READY]' if report.has_gcp_cli else '[NOT DETECTED]'}")
        print(f"Singularity/Apptainer: {'[READY]' if report.has_singularity else '[NOT DETECTED]'}")
        print(f"Docker:              {'[READY]' if report.has_docker else '[NOT DETECTED]'}")
        print(f"Host System Cores:   {report.system_cores}")
        print(f"Host System RAM:     {report.system_ram_gb} GB")
        print(f"GPU Accelerators:    {report.gpu_count} ({', '.join(report.gpu_devices) if report.gpu_devices else 'None'})")
        return 0

    elif action == "generate":
        res = JobResourceConfig(
            job_name=args.job_name,
            cpus=args.cpus,
            memory=args.memory,
            time_limit=args.time_limit,
            partition=args.partition,
            account=args.account,
            qos=args.qos,
            gpus=args.gpus,
            gpu_type=args.gpu_type,
            container_image=args.image,
            workdir=args.workdir,
            output_log=args.output_log,
            error_log=args.error_log,
        )
        script_text = generate_job_script(
            scheduler=args.scheduler,
            command=args.job_command,
            resources=res,
        )
        if args.output:
            dest = Path(args.output)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(script_text, encoding="utf-8")
            print(f"Generated {args.scheduler.upper()} job script saved to: {dest.resolve()}")
        else:
            print(script_text)
        return 0

    elif action == "submit":
        res = submit_job(
            script_path=args.script,
            scheduler=args.scheduler,
            dry_run=args.dry_run,
        )
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
            return 0 if res.success else 1
        print(f"\n=== Submitting Job to {res.scheduler.upper()} ===")
        if res.success:
            print(f"[PASS] Job ID: {res.job_id}")
            print(f"Command: {res.submission_command}")
            print(f"Message: {res.message}")
            return 0
        else:
            print(f"[FAIL] {res.message}")
            return 1

    elif action == "status":
        state, msg = get_job_status(args.job_id, scheduler=args.scheduler)
        if getattr(args, "json", False):
            print(json.dumps({"job_id": args.job_id, "state": state.value, "message": msg}, indent=2))
            return 0
        print(f"Job {args.job_id} on {args.scheduler.upper()}: [{state.value}] - {msg}")
        return 0

    elif action == "diagnose":
        log_txt = ""
        if args.log:
            p = Path(args.log)
            if p.is_file():
                log_txt = p.read_text(encoding="utf-8", errors="ignore")
        diag = diagnose_job_failure(
            exit_code=args.exit_code,
            log_content=log_txt,
            current_memory_gb=args.memory_gb,
            current_cpus=args.cpus,
        )
        if getattr(args, "json", False):
            print(json.dumps(diag.to_dict(), indent=2))
            return 0
        print("\n=== BioNexus Job Post-Mortem Failure Diagnosis ===")
        print(f"Exit Code:     {diag.exit_code}")
        print(f"Primary Cause: {diag.primary_cause}")
        print(f"Action Remedy: {diag.remedy}")
        if diag.suggested_resource_adjustment:
            print(f"Suggested Adjustments: {diag.suggested_resource_adjustment}")
        return 0

    elif action == "tes-task":
        res = JobResourceConfig(
            job_name=args.job_name,
            cpus=args.cpus,
            memory=args.memory,
            workdir=args.workdir,
            container_image=args.image,
        )
        cmd_list = [args.job_command] if isinstance(args.job_command, str) else args.job_command
        task = generate_tes_task(
            name=args.job_name,
            command=cmd_list,
            image=args.image or "quay.io/biocontainers/scanpy:1.10.0",
            resources=res,
        )
        task_json = task.to_json(indent=2)
        if args.output:
            dest = Path(args.output)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(task_json, encoding="utf-8")
            print(f"Generated GA4GH TES task saved to: {dest.resolve()}")
        else:
            print(task_json)
        return 0

    elif action == "elastic-profile":
        policy = ElasticScalePolicy(
            min_nodes=args.min_nodes,
            max_nodes=args.max_nodes,
            max_retries_on_oom=args.max_retries,
            oom_memory_multiplier=args.oom_multiplier,
        )
        prof = CloudNativeBatchProfile(
            provider=args.provider,
            container_engine=args.container_engine,
            image_uri=args.image or "quay.io/biocontainers/scanpy:1.10.0",
            elastic_policy=policy,
        )
        prof_json = json.dumps(prof.to_dict(), indent=2)
        if args.output:
            dest = Path(args.output)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(prof_json, encoding="utf-8")
            print(f"Generated CloudNativeBatchProfile saved to: {dest.resolve()}")
        else:
            print(prof_json)
        return 0

    return 0


def handle_bigdata(args: argparse.Namespace) -> int:
    """Handle bionexus bigdata subcommands."""
    action = getattr(args, "bigdata_action", None)
    if action == "estimate":
        est = estimate_memory_requirements(
            n_cells=args.n_cells,
            n_genes=args.n_genes,
            is_sparse=not args.dense,
            sparsity=args.sparsity,
            n_layers=args.layers,
            n_pcs=args.pcs,
            precision=args.precision,
            available_ram_gb=args.ram_gb,
        )
        if getattr(args, "json", False):
            print(json.dumps(est.to_dict(), indent=2))
            return 0
        print("\n=== BioNexus Matrix Memory Estimation & Safeguard ===")
        print(f"Dataset Shape:       {est.n_cells:,} cells x {est.n_genes:,} genes")
        print(f"Matrix Format:       {'Dense' if args.dense else f'Sparse CSR (~{int(est.sparsity*100)}% zeros)'}")
        print(f"Base Matrix Size:    {est.sparse_csr_gb if not args.dense else est.dense_matrix_gb} GB")
        print(f"PCA/Graph Overhead:  {est.graph_and_pca_overhead_gb} GB")
        print(f"Recommended RAM:     {est.recommended_ram_gb} GB (with safety multiplier)")
        print(f"Host System RAM:     {est.available_system_ram_gb} GB")
        print(f"Safety Verdict:      [{est.safety_verdict}]")
        print(f"Strategy:            {est.recommended_strategy}")
        print(f"Actionable Remedy:   {est.actionable_remedy}")
        return 0

    elif action == "audit":
        rep = audit_dataset_storage(args.path)
        if getattr(args, "json", False):
            print(json.dumps(rep.to_dict(), indent=2))
            return 0
        print("\n=== BioNexus Dataset Storage & Streaming Feasibility Audit ===")
        print(f"Path:                {rep.path}")
        print(f"Detected Format:     {rep.format.upper()}")
        print(f"File/Store Size:     {rep.file_size_mb} MB")
        print(f"Chunked Layout:      {'Yes' if rep.is_chunked else 'No'}")
        print(f"Out-of-Core Ready:   {'Yes' if rep.supports_out_of_core else 'No'}")
        print(f"Streaming Rating:    {rep.streaming_compatibility}")
        for note in rep.notes:
            print(f"Note: {note}")
        return 0

    elif action == "plan":
        plan = generate_streaming_plan(
            total_cells=args.n_cells,
            total_genes=args.n_genes,
            target_ram_mb=args.target_ram_mb,
        )
        if getattr(args, "json", False):
            print(json.dumps(plan.to_dict(), indent=2))
            return 0
        print("\n=== BioNexus Out-of-Core Streaming Execution Plan ===")
        print(f"Total Cells:         {plan.total_cells:,} | Genes: {args.n_genes:,}")
        print(f"Optimal Chunk Size:  {plan.chunk_size:,} cells/chunk")
        print(f"Total Chunks:        {plan.num_chunks}")
        print(f"RAM Peak per Chunk:  ~{plan.estimated_memory_per_chunk_mb} MB")
        print("\nStreaming Execution Workflow:")
        for step in plan.streaming_pipeline_steps:
            print(f"  {step}")
        return 0

    elif action == "stream-aggregate":
        import pandas as pd

        counts_p = Path(args.counts)
        obs_p = Path(args.obs)
        if not counts_p.is_file() or not obs_p.is_file():
            print(f"Error: Counts '{counts_p}' or Obs '{obs_p}' not found.")
            return 1

        counts_df = pd.read_csv(counts_p, index_col=0)
        obs_df = pd.read_csv(obs_p, index_col=0)
        genes = list(counts_df.columns)
        group_cols = [c.strip() for c in args.groupby.split(",")]

        agg = StreamingPseudobulkAggregator(gene_names=genes, group_keys=group_cols)
        chunk_sz = args.chunk_size
        n_rows = len(counts_df)
        for i in range(0, n_rows, chunk_sz):
            sub_c = counts_df.iloc[i : i + chunk_sz]
            sub_o = obs_df.iloc[i : i + chunk_sz]
            agg.add_chunk(sub_c.to_numpy(), sub_o)

        pb_counts, pb_design = agg.to_dataframe()
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        pb_counts.to_csv(out_dir / "pseudobulk_counts.csv")
        pb_design.to_csv(out_dir / "pseudobulk_design.csv")
        print(
            f"Streaming Pseudobulk completed: {len(pb_counts)} aggregate samples x {len(genes)} genes saved to {out_dir.resolve()}"
        )
        return 0

    return 0


def handle_scfm(args: argparse.Namespace) -> int:
    import json

    import anndata as ad

    from bionexus.scfm import (
        FoundationModelFamily,
        SCFMConfig,
        extract_rank_proxy_embeddings,
        extract_scfm_embeddings,
        simulate_gene_perturbation,
    )

    action = getattr(args, "scfm_action", None)
    if action == "embed":
        adata = ad.read_h5ad(args.input)
        if getattr(args, "proxy", False):
            res = extract_rank_proxy_embeddings(adata, embedding_dim=args.dim)
        else:
            family = FoundationModelFamily.GENEFORMER if args.model == "geneformer" else FoundationModelFamily.SCGPT
            cfg = SCFMConfig(
                model_family=family,
                model_name_or_path=args.checkpoint,
                device=args.device,
                embedding_dim=args.dim,
            )
            res = extract_scfm_embeddings(adata, config=cfg, allow_proxy_fallback=getattr(args, "allow_proxy", False))

        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
            return 0 if res.success else 1
        print("\n=== BioNexus Single-Cell Foundation Model Embedding ===")
        print(f"Status:              {res.status}")
        print(f"Model Family:        {res.model_family.upper()}")
        print(f"Cells / Genes:       {res.n_cells:,} cells / {res.n_genes:,} genes")
        print(f"Embedding Dimension: {res.embedding_dim}")
        print(f"Backend Used:        {res.backend_used}")
        print(f"Obsm Key:            adata.obsm['{res.obsm_key}']")
        for note in res.execution_notes:
            print(f"  Note: {note}")
        if not res.success and res.remedy_if_failed:
            print(f"  Remedy: {res.remedy_if_failed}")
        if args.output and res.success:
            adata.write_h5ad(args.output)
            print(f"Saved dataset with embeddings to: {args.output}")
        return 0 if res.success else 1

    elif action == "perturb":
        adata = ad.read_h5ad(args.input)
        family = FoundationModelFamily.GENEFORMER if args.model == "geneformer" else FoundationModelFamily.SCGPT
        cfg = SCFMConfig(model_family=family, model_name_or_path=args.checkpoint, device=args.device)
        res = simulate_gene_perturbation(
            adata=adata,
            target_gene=args.gene,
            mode=args.mode,
            config=cfg,
            allow_proxy_fallback=getattr(args, "allow_proxy", False),
        )
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
            return 0 if res.success else 1
        print("\n=== BioNexus In Silico Gene Perturbation Analysis ===")
        print(f"Status:              {res.status}")
        print(f"Model Family:        {res.model_family.upper()}")
        print(f"Target Gene:         {res.target_gene}")
        print(f"Perturbation Mode:   {res.perturbation_mode.upper()}")
        print(f"Cells Evaluated:     {res.n_cells_evaluated:,}")
        print(f"Mean Shift Delta:    {res.mean_displacement_magnitude:.4f}")
        print(f"Backend Used:        {res.backend_used}")
        for note in res.execution_notes:
            print(f"  Note: {note}")
        if not res.success and res.remedy_if_failed:
            print(f"  Remedy: {res.remedy_if_failed}")
        return 0 if res.success else 1

    return 0

