"""
Unit tests for BioNexus Standardized Run Artifact Contract & Capsule Engine.

Validates:
1. Creation and population of a complete RunBundle directory.
2. Generating run.json, inputs.json, parameters.json, evidence.json, provenance.json, environment.json, logs/.
3. Machine-readable agent handoff with downstream suggestions.
4. Cryptographic completeness and tamper verification.
5. CLI 'bionexus run inspect', 'bionexus run verify', 'bionexus run list'.
"""

import sys
import tempfile
from pathlib import Path

# Ensure src and repo root are on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.artifacts import RunBundle, load_run_bundle, verify_run_bundle
from bionexus.cli import main as cli_main
from bionexus.contracts import EvidenceCard, ExecutionState


def test_run_bundle_lifecycle():
    """Verify full RunBundle lifecycle from initialization to finalization."""
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        run_dir = tmp_path / "run_test_001"

        # 1. Create a dummy input file
        input_file = tmp_path / "raw_counts.h5ad"
        input_file.write_text("dummy_counts_data", encoding="utf-8")

        # 2. Initialize RunBundle
        bundle = RunBundle.create(
            run_dir=run_dir,
            capability_id="scrna.exploratory_clustering",
            skill_name="single-cell-rna-qc",
            run_id="run_test_001",
        )

        # 3. Record input and parameters
        bundle.record_input(
            name="expression_matrix",
            file_path=input_file,
            semantic_type="raw_counts",
            metadata={"n_cells": 1000, "n_genes": 2000},
        )
        bundle.record_parameters(
            resolution=0.8,
            n_top_genes=2000,
            random_seed=42,
        )

        # 4. Create dummy results and figures
        res_file = bundle.results_dir / "clustered.h5ad"
        res_file.write_text("clustered_data_binary", encoding="utf-8")
        bundle.add_result("clustered_anndata", res_file, semantic_type="clustered_counts", is_primary=True)

        fig_file = bundle.figures_dir / "umap_leiden.png"
        fig_file.write_text("fake_png_binary", encoding="utf-8")
        bundle.add_figure("UMAP Leiden Clusters", fig_file, description="UMAP visualization colored by Leiden clusters")

        # 5. Attach EvidenceCard
        card = EvidenceCard(
            execution_state=ExecutionState.EXECUTED.value,
            input_integrity="A",
            assumption_validity="A",
            statistical_support="A",
            details={"execution_backend": "scanpy"},
        )
        bundle.attach_evidence_card(card)

        # 6. Add downstream suggestions
        bundle.add_downstream_suggestion(
            intent="differential_expression",
            capability_id="scrna.pseudobulk_de",
            input_artifact="results/clustered.h5ad",
            recommended_command="python scripts/scrna_pseudobulk.py --input results/clustered.h5ad",
            rationale="Identify robust condition DE genes using PyDESeq2 with biological replicates.",
        )

        # 7. Finalize
        master_path = bundle.finalize(status="COMPLETED")
        assert master_path.exists()
        assert (run_dir / "run.json").exists()
        assert (run_dir / "inputs.json").exists()
        assert (run_dir / "parameters.json").exists()
        assert (run_dir / "evidence.json").exists()
        assert (run_dir / "provenance.json").exists()
        assert (run_dir / "environment.json").exists()
        assert (run_dir / "logs" / "pipeline.log").exists()

        # 8. Test load_run_bundle
        data = load_run_bundle(run_dir)
        assert data["run_id"] == "run_test_001"
        assert data["capability_id"] == "scrna.exploratory_clustering"
        assert data["status"] == "COMPLETED"
        assert data["execution_state"] == "EXECUTED"
        assert len(data["artifacts"]["results"]) == 1
        assert len(data["artifacts"]["figures"]) == 1
        assert len(data["downstream_suggestions"]) == 1

        # 9. Verify integrity
        ver = verify_run_bundle(run_dir)
        assert ver.valid is True
        assert len(ver.missing_files) == 0
        assert len(ver.tampered_files) == 0

        # 10. Tamper detection
        res_file.write_text("tampered_content", encoding="utf-8")
        ver_tampered = verify_run_bundle(run_dir)
        assert ver_tampered.valid is False
        assert len(ver_tampered.tampered_files) == 1


def test_cli_run_commands(capsys):
    """Verify CLI 'bionexus run inspect' and 'bionexus run verify'."""
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        run_dir = tmp_path / "run_cli_test"
        bundle = RunBundle.create(
            run_dir=run_dir,
            capability_id="scrna.exploratory_clustering",
            skill_name="single-cell-rna-qc",
            run_id="run_cli_test",
        )
        res_file = bundle.results_dir / "output.h5ad"
        res_file.write_text("data", encoding="utf-8")
        bundle.add_result("primary_data", res_file, is_primary=True)
        bundle.finalize()

        # Test inspect
        rc_insp = cli_main(["run", "inspect", str(run_dir)])
        assert rc_insp == 0
        out_insp = capsys.readouterr().out
        assert "BioNexus Run Capsule: run_cli_test" in out_insp
        assert "scrna.exploratory_clustering" in out_insp

        # Test verify
        rc_ver = cli_main(["run", "verify", str(run_dir)])
        assert rc_ver == 0
        out_ver = capsys.readouterr().out
        assert "[PASS]" in out_ver

        # Test list
        rc_list = cli_main(["run", "list", str(tmp_path)])
        assert rc_list == 0
        out_list = capsys.readouterr().out
        assert "Found 1 BioNexus Run Capsule(s)" in out_list
