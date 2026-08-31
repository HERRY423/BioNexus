"""
Unit tests for the Workflow Run RO-Crate bundle export (BNS-016 / BNS-IO-014).

Validates:
1. The crate is a real Research Object directory: inputs, software, execution,
   steps, outputs, EvidenceCard, and Claim Ledger packaged under standard
   Workflow Run RO-Crate profiles (Process/Workflow/Provenance Run Crate 0.5,
   Workflow RO-Crate 1.0).
2. Profile conformance declarations (root conformsTo chain + CreativeWork
   profile entities) and schema.org wiring (CreateAction / ControlAction /
   OrganizeAction / HowToStep / FormalParameter).
3. Fail-closed behavior: unsealed capsules are never exported; the exported
   crate is re-verified on disk (structure + SHA-256 of every data entity).
4. Determinism: repeated exports of the same capsule are byte-identical.
"""

import json
import sys
import zipfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from bionexus.artifacts import RunBundle, verify_run_bundle
from bionexus.contracts import EvidenceCard
from bionexus.interop import (
    FORMAL_PARAMETER_PROFILE,
    PROCESS_RUN_CRATE_PROFILE,
    PROVENANCE_RUN_CRATE_PROFILE,
    RO_CRATE_CONTEXT,
    WORKFLOW_RO_CRATE_PROFILE_1_0,
    WORKFLOW_RUN_CRATE_CONTEXT,
    WORKFLOW_RUN_CRATE_PROFILE,
    export_workflow_run_crate,
    run_bundle_to_workflow_run_crate,
    validate_workflow_run_crate,
    verify_workflow_run_crate,
)
from bionexus.ledger import ClaimLedger, ClaimRecord, EvidenceRef


def _build_capsule(
    tmp_path: Path,
    *,
    run_id: str = "run_wfrun_demo",
    with_steps: bool = True,
    status: str = "COMPLETED",
    step_status: str = "COMPLETED",
) -> Path:
    """Build a real sealed run capsule with inputs, results, and a figure."""
    input_file = tmp_path / "counts.h5ad"
    input_file.write_bytes(b"fake-ann-data-bytes")
    run_dir = tmp_path / "run"
    bundle = RunBundle.create(run_dir, "scrna.pseudobulk_de", "single-cell-rna-qc", run_id=run_id)
    bundle.record_input("counts", input_file, "raw_counts")
    bundle.record_parameters(condition="treated_vs_control", fdr_alpha=0.05)
    (run_dir / "results").mkdir(parents=True, exist_ok=True)
    out_file = run_dir / "results" / "de_table.csv"
    out_file.write_text("gene,log2fc\nCXCL13,2.1\n", encoding="utf-8")
    (run_dir / "figures").mkdir(parents=True, exist_ok=True)
    fig_file = run_dir / "figures" / "volcano.png"
    fig_file.write_bytes(b"\x89PNG-fake")
    bundle.add_result("de_table", out_file, "differential_expression_table", is_primary=True)
    bundle.add_figure("volcano", fig_file)
    if with_steps:
        bundle.record_step(
            "normalize",
            "scanpy.pp.normalize_total",
            description="Library-size normalize",
            inputs=["counts"],
        )
        bundle.record_step(
            "pseudobulk_de",
            "pydeseq2",
            tool_version="0.4.9",
            inputs=["counts"],
            outputs=["de_table"],
            status=step_status,
            error="group has one replicate" if step_status != "COMPLETED" else "",
        )
    bundle.attach_evidence_card(EvidenceCard())
    bundle.finalize(status=status)
    return run_dir


def _save_ledger(path: Path) -> Path:
    ledger = ClaimLedger()
    ledger.add_evidence(
        EvidenceRef("E-METHOD-1", "method_run", "pseudobulk DE", "SUPPORTED")
    )
    ledger.add_claim(
        ClaimRecord(
            claim_id="CLAIM-1",
            statement="CXCL13 is enriched in the treated arm",
            capability_id="scrna.pseudobulk_de",
            supported_by=["E-METHOD-1"],
        )
    )
    return ledger.save(path)


def _types(entity) -> list:
    t = entity.get("@type")
    return [t] if isinstance(t, str) else list(t or [])


def _by_id(doc) -> dict:
    return {e["@id"]: e for e in doc["@graph"]}


# ==============================================================================
# Structure and profile conformance
# ==============================================================================


def test_full_bundle_is_materialized_research_object(tmp_path):
    run_dir = _build_capsule(tmp_path)
    _save_ledger(run_dir / "bionexus.ledger.json")
    result = export_workflow_run_crate(run_dir, tmp_path / "crate", zip_archive=True)
    assert result.verified and result.validation_errors == []
    assert result.steps_projected == 2 and result.ledger_included
    crate = result.crate_dir

    # the crate is a real directory Research Object with the standard layout
    for rel in (
        "ro-crate-metadata.json",
        "workflows/scrna.pseudobulk_de.json",
        "data/inputs/counts",
        "data/results/de_table.csv",
        "data/figures/volcano.png",
        "metadata/run.json",
        "metadata/inputs.json",
        "metadata/parameters.json",
        "metadata/evidence.json",
        "metadata/provenance.json",
        "metadata/environment.json",
        "metadata/claim-ledger.json",
        "logs/pipeline.log",
    ):
        assert (crate / rel).is_file(), f"missing crate file: {rel}"
    assert result.zip_path.is_file()
    with zipfile.ZipFile(result.zip_path) as zf:
        assert "crate/ro-crate-metadata.json" in zf.namelist()

    # input bytes are packaged (a Research Object carries its data)
    assert (crate / "data" / "inputs" / "counts").read_bytes() == b"fake-ann-data-bytes"


def test_profile_chain_and_graph_wiring(tmp_path):
    run_dir = _build_capsule(tmp_path)
    _save_ledger(run_dir / "bionexus.ledger.json")
    result = export_workflow_run_crate(run_dir, tmp_path / "crate")
    doc = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert validate_workflow_run_crate(doc) == []
    assert doc["@context"] == WORKFLOW_RUN_CRATE_CONTEXT

    by_id = _by_id(doc)
    root = by_id["./"]
    declared = {c["@id"] for c in root["conformsTo"]}
    assert {
        PROCESS_RUN_CRATE_PROFILE,
        WORKFLOW_RUN_CRATE_PROFILE,
        PROVENANCE_RUN_CRATE_PROFILE,
        WORKFLOW_RO_CRATE_PROFILE_1_0,
    } <= declared
    for profile in declared - {"https://w3id.org/ro/crate/1.1"}:
        assert _types(by_id[profile]) == ["CreativeWork"]

    # Workflow RO-Crate conventions: mainEntity is a crate File + workflow types
    workflow = by_id[root["mainEntity"]["@id"]]
    assert {"File", "SoftwareSourceCode", "ComputationalWorkflow", "HowTo"} <= set(_types(workflow))

    # Provenance Run Crate conventions: tool -> HowToStep -> ControlAction ->
    # OrganizeAction chain
    assert [s["@id"] for s in workflow["step"]] == ["#step/1-normalize", "#step/2-pseudobulk_de"]
    assert {t["@id"] for t in workflow["hasPart"]} == {"#tool/scanpy.pp.normalize_total", "#tool/pydeseq2"}
    tool_runs = [e for e in doc["@graph"] if "CreateAction" in _types(e) and e["@id"].startswith("#tool-run/")]
    assert len(tool_runs) == 2
    de_run = by_id["#tool-run/2-pseudobulk_de"]
    assert de_run["instrument"] == {"@id": "#tool/pydeseq2"}
    assert by_id["#tool/pydeseq2"]["softwareVersion"] == "0.4.9"
    assert de_run["object"] == [{"@id": "data/inputs/counts"}]
    assert de_run["result"] == [{"@id": "data/results/de_table.csv"}]
    control = by_id["#step-run/1-normalize"]
    assert control["instrument"] == {"@id": "#step/1-normalize"}
    assert control["object"] == [{"@id": "#tool-run/1-normalize"}]
    engine_run = by_id["#engine-run/run_wfrun_demo"]
    assert engine_run["instrument"] == {"@id": "https://github.com/HERRY423/BioNexus"}
    assert engine_run["result"] == {"@id": "#run/run_wfrun_demo"}

    # Workflow Run Crate conventions: main run CreateAction + FormalParameters
    main_action = by_id["#run/run_wfrun_demo"]
    assert {"@id": "data/inputs/counts"} in main_action["object"]
    assert {"@id": "data/results/de_table.csv"} in main_action["result"]
    assert main_action["actionStatus"] == {"@id": "http://schema.org/ActionStatusType/CompletedActionStatus"}
    param = by_id["#param/fdr_alpha"]
    assert param["additionalType"] == "Float"
    assert param["conformsTo"] == {"@id": FORMAL_PARAMETER_PROFILE}
    pv = by_id["#param-value/fdr_alpha"]
    assert pv["exampleOfWork"] == {"@id": "#param/fdr_alpha"}
    assert json.loads(pv["value"]) == 0.05
    file_param = by_id["#input-param/counts"]
    assert file_param["additionalType"] == "File"
    assert file_param["workExample"] == {"@id": "data/inputs/counts"}

    # software: engine + pinned packages from the environment snapshot
    engine = by_id["https://github.com/HERRY423/BioNexus"]
    assert "SoftwareApplication" in _types(engine)
    assert isinstance(engine.get("softwareRequirements"), list)

    # EvidenceCard rides inside the crate with BNS extension terms
    card = by_id["#evidence-card"]
    assert card["bnsExecutionState"] == "EXECUTED"
    assert card["about"] == {"@id": "#run/run_wfrun_demo"}

    # Claim Ledger claims are contextual entities with isBasedOn edges
    claim = by_id["#claim/CLAIM-1"]
    assert claim["isBasedOn"] == [{"@id": "#evidence/E-METHOD-1"}]
    assert claim["bnsEvidenceStatus"] == "SUPPORTED"


def test_exported_sha256_matches_crate_bytes(tmp_path):
    """Crate checksums must match what a standard RO-Crate consumer computes."""
    run_dir = _build_capsule(tmp_path)
    result = export_workflow_run_crate(run_dir, tmp_path / "crate")
    doc = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    crate = result.crate_dir
    import hashlib

    for entity in doc["@graph"]:
        eid = str(entity.get("@id", ""))
        if eid.startswith("#") or eid in ("./", "ro-crate-metadata.json") or "://" in eid:
            continue
        data = (crate / eid).read_bytes()
        assert entity.get("sha256") == hashlib.sha256(data).hexdigest(), eid


def test_bundle_without_steps_is_workflow_run_crate(tmp_path):
    run_dir = _build_capsule(tmp_path, with_steps=False)
    result = export_workflow_run_crate(run_dir, tmp_path / "crate")
    doc = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert validate_workflow_run_crate(doc) == []
    by_id = _by_id(doc)
    declared = {c["@id"] for c in by_id["./"]["conformsTo"]}
    assert WORKFLOW_RUN_CRATE_PROFILE in declared
    assert PROVENANCE_RUN_CRATE_PROFILE not in declared  # honestly undeclared
    assert not any("ControlAction" in _types(e) for e in doc["@graph"])
    assert not any("OrganizeAction" in _types(e) for e in doc["@graph"])
    assert "HowTo" not in _types(by_id[by_id["./"]["mainEntity"]["@id"]])
    assert result.steps_projected == 0


def test_failed_run_and_failed_step_action_status(tmp_path):
    run_dir = _build_capsule(tmp_path, status="FAILED", step_status="FAILED")
    result = export_workflow_run_crate(run_dir, tmp_path / "crate")
    doc = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    by_id = _by_id(doc)
    failed = "http://schema.org/ActionStatusType/FailedActionStatus"
    main_action = by_id["#run/run_wfrun_demo"]
    assert main_action["actionStatus"] == {"@id": failed}
    assert main_action["error"] == {"@id": "#error"}
    assert by_id["#tool-run/2-pseudobulk_de"]["actionStatus"] == {"@id": failed}
    assert "one replicate" in by_id["#tool-run/2-pseudobulk_de"]["error"]
    assert by_id["#engine-run/run_wfrun_demo"]["actionStatus"] == {"@id": failed}


def test_document_only_projection(tmp_path):
    """run_bundle_to_workflow_run_crate works offline on manifest dicts."""
    run_dir = _build_capsule(tmp_path)
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    siblings = {
        "inputs": json.loads((run_dir / "inputs.json").read_text(encoding="utf-8")),
        "parameters": json.loads((run_dir / "parameters.json").read_text(encoding="utf-8")),
        "environment": json.loads((run_dir / "environment.json").read_text(encoding="utf-8")),
    }
    doc = run_bundle_to_workflow_run_crate(manifest, siblings)
    assert validate_workflow_run_crate(doc) == []


# ==============================================================================
# Fail-closed behavior
# ==============================================================================


def test_export_refuses_unsealed_capsule(tmp_path):
    run_dir = _build_capsule(tmp_path)
    (run_dir / "results" / "de_table.csv").write_text("tampered\n", encoding="utf-8")
    assert not verify_run_bundle(run_dir).valid
    with pytest.raises(ValueError, match="failed integrity verification"):
        export_workflow_run_crate(run_dir, tmp_path / "crate")
    assert not (tmp_path / "crate").exists()  # nothing written (BNS-IO-004)


def test_export_refuses_missing_input_bytes(tmp_path):
    run_dir = _build_capsule(tmp_path)
    # unseal deterministically: rebuild a capsule whose input disappears
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"]["results"]
    inputs = json.loads((run_dir / "inputs.json").read_text(encoding="utf-8"))
    Path(inputs["counts"]["path"]).unlink()
    assert not verify_run_bundle(run_dir).valid
    with pytest.raises(ValueError, match="failed integrity verification"):
        export_workflow_run_crate(run_dir, tmp_path / "crate")


def test_export_refuses_ledger_source(tmp_path):
    ledger_path = _save_ledger(tmp_path / "bionexus.ledger.json")
    with pytest.raises(ValueError, match="run capsule"):
        export_workflow_run_crate(ledger_path, tmp_path / "crate")


def test_export_refuses_overwrite_and_bad_ledger(tmp_path):
    run_dir = _build_capsule(tmp_path)
    export_workflow_run_crate(run_dir, tmp_path / "crate")
    with pytest.raises(ValueError, match="non-empty"):
        export_workflow_run_crate(run_dir, tmp_path / "crate")

    not_a_ledger = tmp_path / "not-a-ledger.json"
    not_a_ledger.write_text(json.dumps({"hello": "world"}), encoding="utf-8")
    with pytest.raises(ValueError, match="Claim–Evidence Ledger"):
        export_workflow_run_crate(run_dir, tmp_path / "crate2", ledger_path=not_a_ledger)


def test_post_write_verification_detects_tampering(tmp_path):
    run_dir = _build_capsule(tmp_path)
    result = export_workflow_run_crate(run_dir, tmp_path / "crate")
    crate = result.crate_dir
    (crate / "data" / "results" / "de_table.csv").write_text("tampered\n", encoding="utf-8")
    errors = verify_workflow_run_crate(crate)
    assert any("checksum mismatch" in e for e in errors)

    (crate / "data" / "inputs" / "counts").unlink()
    assert any("missing on disk" in e for e in verify_workflow_run_crate(crate))


def test_validator_catches_profile_and_wiring_corruption(tmp_path):
    run_dir = _build_capsule(tmp_path)
    result = export_workflow_run_crate(run_dir, tmp_path / "crate")
    doc = json.loads(result.metadata_path.read_text(encoding="utf-8"))

    bad_context = json.loads(json.dumps(doc))
    bad_context["@context"] = RO_CRATE_CONTEXT
    assert any("@context" in e for e in validate_workflow_run_crate(bad_context))

    no_provenance_profile = json.loads(json.dumps(doc))
    no_provenance_profile["@graph"] = [
        e for e in no_provenance_profile["@graph"] if e.get("@id") != PROVENANCE_RUN_CRATE_PROFILE
    ]
    for e in no_provenance_profile["@graph"]:
        if e.get("@id") == "./":
            e["conformsTo"] = [c for c in e["conformsTo"] if c["@id"] != PROVENANCE_RUN_CRATE_PROFILE]
    assert any(PROVENANCE_RUN_CRATE_PROFILE in e for e in validate_workflow_run_crate(no_provenance_profile))

    broken_control = json.loads(json.dumps(doc))
    for e in broken_control["@graph"]:
        if e.get("@id") == "#step-run/1-normalize":
            e["instrument"] = {"@id": "#nonexistent"}
    assert any("HowToStep" in e for e in validate_workflow_run_crate(broken_control))

    bad_status = json.loads(json.dumps(doc))
    for e in bad_status["@graph"]:
        if e.get("@id") == "#run/run_wfrun_demo":
            e["actionStatus"] = {"@id": "http://schema.org/ActionStatusType/TotallyMadeUp"}
    assert any("ActionStatusType" in e for e in validate_workflow_run_crate(bad_status))


# ==============================================================================
# Determinism and ledger handling
# ==============================================================================


def test_exports_are_deterministic(tmp_path):
    run_dir = _build_capsule(tmp_path)
    _save_ledger(run_dir / "bionexus.ledger.json")
    r1 = export_workflow_run_crate(run_dir, tmp_path / "a" / "crate", zip_archive=True)
    r2 = export_workflow_run_crate(run_dir, tmp_path / "b" / "crate", zip_archive=True)
    m1 = (r1.crate_dir / "ro-crate-metadata.json").read_bytes()
    m2 = (r2.crate_dir / "ro-crate-metadata.json").read_bytes()
    assert m1 == m2
    assert r1.zip_path.read_bytes() == r2.zip_path.read_bytes()


def test_ledger_auto_detection_and_explicit_path(tmp_path):
    run_dir = _build_capsule(tmp_path)
    # no adjacent ledger -> not included
    r = export_workflow_run_crate(run_dir, tmp_path / "crate1")
    assert not r.ledger_included
    assert not (r.crate_dir / "metadata" / "claim-ledger.json").exists()

    # explicit ledger path -> embedded
    (tmp_path / "elsewhere").mkdir()
    ledger_path = _save_ledger(tmp_path / "elsewhere" / "bionexus.ledger.json")
    r2 = export_workflow_run_crate(run_dir, tmp_path / "crate2", ledger_path=ledger_path)
    assert r2.ledger_included
    doc = json.loads(r2.metadata_path.read_text(encoding="utf-8"))
    assert any(e.get("@id") == "#claim/CLAIM-1" for e in doc["@graph"])

    # adjacent ledger -> auto-embedded
    _save_ledger(run_dir / "bionexus.ledger.json")
    r3 = export_workflow_run_crate(run_dir, tmp_path / "crate3")
    assert r3.ledger_included
