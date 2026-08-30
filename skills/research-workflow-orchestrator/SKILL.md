---
name: research-workflow-orchestrator
description: Chain BioNexus stages into a multi-step research workflow using Run Capsules. Topological execution, one verified capsule per stage, fail-closed abort. Does not validate stage science, does not replace Nextflow/Airflow/Snakemake, and never reports a partially executed chain as complete.
---

# Run Capsule Chain Orchestration

The kernel implementation lives in `bionexus.orchestrator`; this skill is its agent-facing
surface. Each stage of a chain declares an argv command (no shell), optional inputs, and
explicit `depends_on` edges. Every executed stage produces a full Run Capsule
(`run.json`, `inputs.json`, `evidence.json`, `provenance.json`, logs) that downstream
stages, agents, or `bionexus project register-run` can consume.

## When to use

- Multi-stage workflows that already run as BioNexus-compatible commands and need
  handoff-grade artifacts between stages.
- Cross-session continuation: register stage capsules into the project ledger
  (`bionexus project register-run`) so the next session resumes from verified state.

## When NOT to use

- Sequencing pipelines with real compute profiles: use `nextflow-development` (nf-core).
- Heavy DAG scheduling, retries, or cloud orchestration: Nextflow / Airflow / Snakemake.

## Quick start

```bash
# 1. Plan without executing (validates DAG, detects cycles, checks structure)
bionexus chain workflow.yaml --dry-run

# 2. Execute; each stage gets its own capsule under --workdir
bionexus chain workflow.yaml --workdir chain_runs

# 3. Register the completed capsules into the project ledger
bionexus project register-run chain_runs/<step_id>
```

### Chain spec (YAML)

```yaml
name: scrna_qc_to_de
steps:
  - id: qc
    name: Single-cell QC
    command: ["python", "skills/single-cell-rna-qc/scripts/scrna_gold_chain.py", "sample.h5ad", "--outdir", "runs/qc"]
    inputs: ["sample.h5ad"]
  - id: de
    name: Pseudobulk differential expression
    command: ["python", "skills/single-cell-rna-qc/scripts/scrna_pseudobulk_de.py", "runs/qc/results/qc.h5ad", "-o", "runs/de/de.csv"]
    depends_on: ["qc"]
    inputs: ["runs/qc/results/qc.h5ad"]
```

## Honesty invariants

- **Fail-closed**: a failing stage aborts the chain; downstream stages are recorded as
  `SKIPPED_FAIL_CLOSED`. The chain result must never be reported as a completed
  analysis in that case.
- **Execution fidelity only**: the orchestrator guarantees that the declared command ran
  and captured its provenance. It does not check whether the stage's science was valid —
  that remains each stage's capability contract and EvidenceCard.
- **No shell**: commands are argv lists executed with `shell=False`. Privilege escalation
  (`sudo`) is rejected at spec-validation time.
- Stage EvidenceCards record `execution_state=EXECUTED` with all scientific dimensions
  `UNTESTED` — an orchestrator capsule never pretends to be scientific evidence.

## Legacy runner

The previous in-process YAML DAG engine is retained as `SKILL.legacy.md` and its scripts
remain importable, but new workflows should use the capsule-chain CLI above.
