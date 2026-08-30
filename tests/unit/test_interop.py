"""
Unit tests for BioNexus standards interoperability projections (BNS-016):
RO-Crate 1.1 (+ Workflow Run Crate), IEEE 2791-2020 BioCompute Objects,
fail-closed exports, and the CLI surface.
"""

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from bionexus.cli import main as cli_main
from bionexus.contracts import ConclusionMaturity
from bionexus.interop import (
    BCO_SPEC_VERSION,
    PROCESS_RUN_CRATE_PROFILE,
    RO_CRATE_CONTEXT,
    RO_CRATE_PROFILE,
    WORKFLOW_RO_CRATE_PROFILE,
    export_bco,
    export_ro_crate,
    ledger_to_ro_crate,
    load_interop_source,
    run_bundle_to_bco,
    run_bundle_to_ro_crate,
    validate_bco,
    validate_ro_crate,
    validate_workflow_run_crate,
)
from bionexus.ledger import ClaimLedger, ClaimRecord, EvidenceRef
from bionexus.verification import write_example_ledger


def _demo_manifest():
    return {
        "run_id": "run_20260817_demo_scrna_pseudobulk_de",
        "bionexus_version": "0.10.0",
        "capability_id": "scrna.pseudobulk_de",
        "skill_name": "single-cell-rna-qc",
        "status": "COMPLETED",
        "execution_state": "EXECUTED",
        "conclusion_maturity": "SUPPORTED",
        "timestamp_start": "2026-08-17T10:00:00+00:00",
        "timestamp_end": "2026-08-17T10:02:30+00:00",
        "duration_seconds": 150.0,
        "artifacts": {
            "primary_result": "results/de_table.csv",
            "results": [
                {"name": "de_table", "path": "results/de_table.csv", "semantic_type": "differential_expression_table", "sha256": "a" * 64}
            ],
            "figures": [
                {"title": "volcano", "path": "figures/volcano.png", "format": "png", "sha256": "b" * 64}
            ],
        },
        "downstream_suggestions": [],
    }


def _demo_siblings():
    return {
        "inputs": {
            "counts": {"name": "counts", "path": "data/counts.h5ad", "semantic_type": "raw_counts", "sha256": "c" * 64},
        },
        "parameters": {"condition": "treated_vs_control", "fdr_alpha": 0.05},
        "environment": {"packages": {"pydeseq2": "0.4.9"}},
    }


def _make_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    (run_dir / "results").mkdir(parents=True)
    (run_dir / "figures").mkdir(parents=True)
    (run_dir / "logs").mkdir(parents=True)
    (run_dir / "run.json").write_text(json.dumps(_demo_manifest()), encoding="utf-8")
    (run_dir / "inputs.json").write_text(json.dumps(_demo_siblings()["inputs"]), encoding="utf-8")
    (run_dir / "parameters.json").write_text(json.dumps(_demo_siblings()["parameters"]), encoding="utf-8")
    (run_dir / "environment.json").write_text(json.dumps(_demo_siblings()["environment"]), encoding="utf-8")
    for rel in ("evidence.json", "provenance.json"):
        (run_dir / rel).write_text("{}", encoding="utf-8")
    (run_dir / "logs" / "pipeline.log").write_text("log\n", encoding="utf-8")
    return run_dir


# ==============================================================================
# RO-Crate projections
# ==============================================================================


def test_run_bundle_to_ro_crate_structure():
    doc = run_bundle_to_ro_crate(_demo_manifest(), _demo_siblings())
    assert doc["@context"] == RO_CRATE_CONTEXT
    assert validate_ro_crate(doc) == []

    by_id = {e["@id"]: e for e in doc["@graph"]}
    assert by_id["ro-crate-metadata.json"]["conformsTo"]["@id"] == RO_CRATE_PROFILE
    root = by_id["./"]
    assert "Dataset" in root["@type"]
    assert root["mainEntity"]["@id"] == "#workflow/scrna.pseudobulk_de"

    workflow = by_id["#workflow/scrna.pseudobulk_de"]
    assert "ComputationalWorkflow" in workflow["@type"]
    assert workflow["conformsTo"]["@id"] == WORKFLOW_RO_CRATE_PROFILE

    action = by_id["#run/run_20260817_demo_scrna_pseudobulk_de"]
    assert "CreateAction" in action["@type"]
    assert action["conformsTo"]["@id"] == PROCESS_RUN_CRATE_PROFILE
    assert action["instrument"]["@id"] == "#workflow/scrna.pseudobulk_de"
    assert action["startTime"] and action["endTime"]
    assert {"@id": "#input/counts"} in action["object"]
    assert {"@id": "results/de_table.csv"} in action["result"]

    # evidence maturity rides inside the crate
    assert "SUPPORTED" in by_id["#evidence-card"]["description"]


def test_failed_run_gets_error_entity():
    manifest = dict(_demo_manifest())
    manifest["status"] = "FAILED"
    doc = run_bundle_to_ro_crate(manifest, {})
    by_id = {e["@id"]: e for e in doc["@graph"]}
    assert "#error" in by_id
    assert "error" in by_id["#run/run_20260817_demo_scrna_pseudobulk_de"]


def test_ledger_to_ro_crate():
    ledger = ClaimLedger()
    ledger.add_evidence(EvidenceRef("E1", "method_run", "pseudobulk DE", ConclusionMaturity.SUPPORTED.value))
    ledger.add_evidence(EvidenceRef("E2", "dataset", "cohort", ConclusionMaturity.SUPPORTED.value))
    ledger.add_claim(
        ClaimRecord(
            claim_id="C1",
            statement="Gene X is upregulated",
            capability_id="scrna.pseudobulk_de",
            supported_by=["E1", "E2"],
        )
    )
    doc = ledger_to_ro_crate(ledger)
    assert validate_ro_crate(doc) == []
    by_id = {e["@id"]: e for e in doc["@graph"]}
    claim = by_id["#claim/C1"]
    assert claim["name"] == "Gene X is upregulated"
    assert {"@id": "#evidence/E1"} in claim["isBasedOn"]


def test_validate_ro_crate_catches_corruption():
    doc = run_bundle_to_ro_crate(_demo_manifest(), _demo_siblings())
    doc["@context"] = "https://example.org/wrong"
    errors = validate_ro_crate(doc)
    assert any("@context" in e for e in errors)

    doc2 = run_bundle_to_ro_crate(_demo_manifest(), _demo_siblings())
    doc2["@graph"] = [e for e in doc2["@graph"] if e.get("@id") != "ro-crate-metadata.json"]
    assert any("descriptor" in e for e in validate_ro_crate(doc2))

    doc3 = run_bundle_to_ro_crate(_demo_manifest(), _demo_siblings())
    for e in doc3["@graph"]:
        if e.get("@id") == "./":
            e["@type"] = "Person"
    assert any("root" in e.lower() for e in validate_ro_crate(doc3))


# ==============================================================================
# BioCompute Object projections
# ==============================================================================


def test_run_bundle_to_bco_six_domains():
    bco = run_bundle_to_bco(_demo_manifest(), _demo_siblings())
    assert bco["spec_version"] == BCO_SPEC_VERSION
    assert validate_bco(bco) == []
    for domain in (
        "provenance_domain",
        "usability_domain",
        "description_domain",
        "execution_domain",
        "io_domain",
        "parametric_domain",
    ):
        assert domain in bco
    assert any("fdr_alpha" == p["param"] for p in bco["parametric_domain"])
    assert bco["io_domain"]["input_subdomain"][0]["uri"]["filename"] == "data/counts.h5ad"
    assert any(sp["name"] == "BioNexus" for sp in bco["execution_domain"]["software_prerequisites"])
    assert any(sp["name"] == "pydeseq2" and sp["version"] == "0.4.9" for sp in bco["execution_domain"]["software_prerequisites"])
    assert "Research Use Only" in " ".join(bco["usability_domain"])


def test_bco_etag_rejects_tampering():
    bco = run_bundle_to_bco(_demo_manifest(), _demo_siblings())
    assert validate_bco(bco) == []
    bco["parametric_domain"][0]["value"] = "0.5"
    errors = validate_bco(bco)
    assert any("etag" in e for e in errors)


def test_validate_bco_catches_missing_domains():
    bco = run_bundle_to_bco(_demo_manifest(), _demo_siblings())
    del bco["io_domain"]
    assert any("io_domain" in e for e in validate_bco(bco))


# ==============================================================================
# Fail-closed exports + CLI
# ==============================================================================


def test_export_ro_crate_and_bco_write_validated_files(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    crate_path, errors = export_ro_crate(run_dir, tmp_path / "out" / "ro-crate-metadata.json")
    assert errors == [] and crate_path.is_file()
    doc = json.loads(crate_path.read_text(encoding="utf-8"))
    assert validate_ro_crate(doc) == []

    bco_path, errors = export_bco(run_dir, tmp_path / "out" / "bco.json")
    assert errors == [] and bco_path.is_file()
    assert validate_bco(json.loads(bco_path.read_text(encoding="utf-8"))) == []


def test_export_bco_refuses_ledger(tmp_path):
    ledger_path = write_example_ledger(tmp_path / "results" / "bionexus.ledger.json")
    with pytest.raises(ValueError):
        export_bco(ledger_path, tmp_path / "nope.json")
    assert not (tmp_path / "nope.json").exists()  # nothing written (BNS-IO-004)


def test_load_interop_source_detection(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    kind, manifest, siblings = load_interop_source(run_dir)
    assert kind == "run" and manifest["run_id"].startswith("run_2026")
    assert "inputs" in siblings and "environment" in siblings

    kind2, data2, _ = load_interop_source(run_dir / "run.json")
    assert kind2 == "run"

    ledger_path = write_example_ledger(tmp_path / "l2" / "bionexus.ledger.json")
    kind3, data3, _ = load_interop_source(ledger_path.parent)
    assert kind3 == "ledger" and "claims" in data3

    with pytest.raises(FileNotFoundError):
        load_interop_source(tmp_path / "nothing_here")


def test_interop_cli(tmp_path, capsys):
    run_dir = _make_run_dir(tmp_path)

    assert cli_main(["interop", "check", str(run_dir)]) == 0
    out = capsys.readouterr().out
    assert "RO-Crate 1.1 structural validation: PASS" in out
    assert "IEEE 2791-2020 BCO structural validation: PASS" in out

    assert cli_main(["interop", "ro-crate", str(run_dir)]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert validate_ro_crate(doc) == []

    assert cli_main(["interop", "bco", str(run_dir), "--out", str(tmp_path / "b.json")]) == 0
    assert "written to" in capsys.readouterr().out

    assert cli_main(["interop", "bco", str(run_dir)]) == 0
    assert cli_main(["interop", "check", str(tmp_path / "nope")]) == 1
    capsys.readouterr()

    ledger_dir = write_example_ledger(tmp_path / "l3" / "bionexus.ledger.json").parent
    assert cli_main(["interop", "ro-crate", str(ledger_dir)]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert validate_ro_crate(doc) == []

    # Workflow Run RO-Crate bundle export (BNS-IO-014). The hand-written demo
    # capsule carries no v2 integrity seal, so the fail-closed exporter refuses.
    assert cli_main(["interop", "wfrun-crate", str(run_dir), "--out", str(tmp_path / "wfc")]) == 1
    assert "failed integrity verification" in capsys.readouterr().err
    assert not (tmp_path / "wfc").exists()

    # Sealed capsule: build a real RunBundle and export it.
    from bionexus.artifacts import RunBundle

    sealed_dir = tmp_path / "sealed_run"
    counts_file = tmp_path / "counts.h5ad"
    counts_file.write_bytes(b"counts-bytes")
    bundle = RunBundle.create(sealed_dir, "scrna.pseudobulk_de", "single-cell-rna-qc", run_id="run_cli_wfrun")
    bundle.record_input("counts", counts_file, "raw_counts")
    (sealed_dir / "results").mkdir(parents=True, exist_ok=True)
    out_csv = sealed_dir / "results" / "de.csv"
    out_csv.write_text("gene,p\nCXCL13,0.01\n", encoding="utf-8")
    bundle.add_result("de", out_csv, "de_table")
    bundle.record_step("de", "pydeseq2", inputs=["counts"], outputs=["de"])
    bundle.finalize()

    assert cli_main(["interop", "wfrun-crate", str(sealed_dir), "--out", str(tmp_path / "wfc")]) == 0
    out_wfc = capsys.readouterr().out
    assert "Workflow Run RO-Crate written to" in out_wfc
    assert "post-write verification: PASS" in out_wfc
    assert (tmp_path / "wfc" / "ro-crate-metadata.json").is_file()
    assert (tmp_path / "wfc" / "data" / "inputs" / "counts").is_file()
    wfc_doc = json.loads((tmp_path / "wfc" / "ro-crate-metadata.json").read_text(encoding="utf-8"))
    assert validate_workflow_run_crate(wfc_doc) == []

    assert cli_main(["interop", "wfrun-crate", str(sealed_dir)]) == 0
    wfc_stdout = json.loads(capsys.readouterr().out)
    assert validate_workflow_run_crate(wfc_stdout) == []

    assert cli_main(["interop", "check", str(run_dir)]) == 0
    check_out = capsys.readouterr().out
    assert "Workflow Run RO-Crate (bundle projection): PASS" in check_out


def test_no_proprietary_interchange_format_claim():
    """BNS-IO-005: the interop surface exposes only standard formats."""
    import bionexus.interop as interop

    public = [n for n in dir(interop) if not n.startswith("_")]
    exporters = [n for n in public if n.startswith("export_")]
    # export_workflow_run_crate (BNS-IO-014) is the Workflow Run RO-Crate
    # Research Object bundle export -- still a published community standard.
    assert set(exporters) == {"export_ro_crate", "export_bco", "export_workflow_run_crate"}
