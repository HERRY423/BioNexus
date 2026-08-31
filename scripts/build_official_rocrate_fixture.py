"""Build the deterministic Workflow Run RO-Crate used by official CI validation."""

from __future__ import annotations

import argparse
from pathlib import Path

from bionexus.artifacts import RunBundle
from bionexus.contracts import EvidenceCard
from bionexus.interop import export_workflow_run_crate


def build_fixture(output_dir: Path) -> Path:
    """Create a sealed capsule and export its complete Research Object."""
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"Output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    input_file = output_dir / "counts.csv"
    input_file.write_text("cell,gene,count\ncell-1,CXCL13,7\n", encoding="utf-8")
    run_dir = output_dir / "run"
    bundle = RunBundle.create(
        run_dir,
        "scrna.pseudobulk_de",
        "single-cell-rna-qc",
        run_id="official-validator-fixture",
    )
    bundle.record_input("counts", input_file, "raw_counts")
    bundle.record_parameters(condition="treated_vs_control", fdr_alpha=0.05)
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    result_file = results_dir / "de_table.csv"
    result_file.write_text("gene,log2fc\nCXCL13,2.1\n", encoding="utf-8")
    bundle.add_result(
        "de_table",
        result_file,
        "differential_expression_table",
        is_primary=True,
    )
    bundle.record_step(
        "pseudobulk_de",
        "pydeseq2",
        tool_version="0.4.9",
        inputs=["counts"],
        outputs=["de_table"],
    )
    bundle.attach_evidence_card(EvidenceCard())
    bundle.finalize(status="COMPLETED")

    result = export_workflow_run_crate(run_dir, output_dir / "crate", zip_archive=True)
    if not result.verified:
        raise RuntimeError(f"BioNexus preflight failed: {result.validation_errors}")
    return result.crate_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(build_fixture(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
