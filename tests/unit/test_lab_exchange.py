"""End-to-end lab import/export acceptance against committed product fixtures."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from bionexus.cli import main
from bionexus.lab_exchange import accept_lab_roundtrip, detect_lab_product, export_lab_capsule, import_lab_source
from bionexus.schema_registry import SchemaError, canonical_json_sha256

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "lab_exchange"

PRODUCT_PATHS = {
    "cellranger": FIXTURES / "cellranger" / "outs",
    "seurat": FIXTURES / "seurat",
    "scanpy": FIXTURES / "scanpy",
    "deseq2": FIXTURES / "deseq2" / "results.csv",
    "edger": FIXTURES / "edger" / "results.tsv",
    "nf-core": FIXTURES / "nfcore",
}


@pytest.mark.parametrize("product,source", list(PRODUCT_PATHS.items()))
def test_detect_each_lab_product(product, source):
    detection = detect_lab_product(source)
    assert detection.product == product
    assert detection.confidence in {"HIGH", "MEDIUM"}


@pytest.mark.parametrize("product,source", list(PRODUCT_PATHS.items()))
def test_accept_lab_roundtrip_for_each_product(product, source, tmp_path):
    report = accept_lab_roundtrip(source, tmp_path / product)
    assert report.passed, json.dumps(report.to_dict(), indent=2)
    assert report.product == product
    assert report.scientific_authorization == "NONE"
    assert Path(report.envelope_path).is_file()
    assert Path(report.capsule_path).is_file()
    assert Path(report.ro_crate_path).is_file()
    assert Path(report.bco_path).is_file()
    names = [gate.name for gate in report.gates]
    assert names == ["DETECT", "IMPORT", "CAPSULE", "RO_CRATE", "BCO", "REIMPORT", "COMPAT"]


def test_legacy_deseq2_column_aliases_still_import():
    detection, envelope = import_lab_source(FIXTURES / "history" / "deseq2_results_legacy.csv")
    assert detection.product == "deseq2"
    assert envelope["schema_version"] == "bionexus.lab-exchange-envelope.v2"
    assert envelope["summary"]["n_rows"] == 2


def test_native_seurat_rds_is_refused(tmp_path):
    rds = tmp_path / "object.rds"
    rds.write_bytes(b"not-a-seurat-object")
    with pytest.raises(SchemaError, match="unable to detect"):
        detect_lab_product(rds)


def test_export_refuses_path_escape(tmp_path):
    from bionexus.lab_exchange import export_lab_capsule

    secret = tmp_path / "secret.txt"
    secret.write_text("phi", encoding="utf-8")
    lab = tmp_path / "lab"
    lab.mkdir()
    (lab / "counts.tsv").write_text("gene\tc1\nA\t1\n", encoding="utf-8")
    (lab / "obs.tsv").write_text("cell\tcondition\nc1\tctrl\n", encoding="utf-8")
    _detection, envelope = import_lab_source(lab)
    envelope["source"]["files"].append(
        {
            "role": "escape",
            "relpath": "../secret.txt",
            "sha256": "b" * 64,
            "size_bytes": 3,
        }
    )
    envelope["payload_sha256"] = canonical_json_sha256(envelope["source"]["files"])
    with pytest.raises(SchemaError, match="outside lab root"):
        export_lab_capsule(envelope, lab, tmp_path / "out", ro_crate=False, bco=False)


def test_cli_accept_cellranger(tmp_path, capsys):
    dest = tmp_path / "accept"
    code = main(["deploy", "accept", str(PRODUCT_PATHS["cellranger"]), "-o", str(dest), "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 0
    assert payload["passed"] is True
    assert payload["product"] == "cellranger"


def test_corruption_after_copy_refuses_acceptance(monkeypatch, tmp_path):
    copy = shutil.copy2

    def corrupt_copy(source, dest, *args, **kwargs):
        result = copy(source, dest, *args, **kwargs)
        Path(dest).write_bytes(b"corrupted exported data")
        return result

    monkeypatch.setattr("bionexus.lab_exchange.shutil.copy2", corrupt_copy)
    report = accept_lab_roundtrip(PRODUCT_PATHS["scanpy"], tmp_path / "out")
    assert not report.passed
    assert any(not gate.passed and "bytes do not match" in gate.detail for gate in report.gates)
    receipt = json.loads(Path(report.receipt_path).read_text(encoding="utf-8"))
    assert receipt["passed"] is False


def test_mutated_source_refused_before_capsule_creation(tmp_path):
    source = tmp_path / "scanpy"
    shutil.copytree(PRODUCT_PATHS["scanpy"], source)
    _, envelope = import_lab_source(source)
    (source / "counts.tsv").write_bytes(b"different source bytes")
    with pytest.raises(SchemaError, match="bytes do not match"):
        export_lab_capsule(envelope, source, tmp_path / "out")
    assert not (tmp_path / "out" / "run.json").exists()


def test_capsule_inputs_survive_source_removal_and_directory_move(tmp_path):
    from bionexus.artifacts import verify_run_bundle

    source = tmp_path / "scanpy"
    shutil.copytree(PRODUCT_PATHS["scanpy"], source)
    _, envelope = import_lab_source(source)
    capsule = tmp_path / "capsule"
    export_lab_capsule(envelope, source, capsule)
    # Removing a single source file models an unavailable originating lab; no recursive delete.
    (source / "counts.tsv").unlink()
    relocated = tmp_path / "relocated"
    capsule.rename(relocated)
    assert verify_run_bundle(relocated).valid


def test_cellranger_parent_and_nested_files_roundtrip(tmp_path):
    report = accept_lab_roundtrip(PRODUCT_PATHS["cellranger"].parent, tmp_path / "out")
    assert report.passed, report.to_dict()
    assert (tmp_path / "out/capsule/results/imported/filtered_feature_bc_matrix/matrix.mtx").is_file()


def test_explicit_rds_never_imports_adjacent_tables(tmp_path):
    shutil.copytree(PRODUCT_PATHS["scanpy"], tmp_path / "adjacent")
    rds = tmp_path / "adjacent/object.rds"
    rds.write_bytes(b"unsupported object")
    with pytest.raises(SchemaError, match="unsupported"):
        import_lab_source(rds)


@pytest.mark.parametrize("classification", ["UNKNOWN", "CONTROLLED_ACCESS_GENOMIC", "PUBLIC_BENCHMARK"])
def test_classification_survives_entire_archive(classification, tmp_path):
    report = accept_lab_roundtrip(PRODUCT_PATHS["scanpy"], tmp_path / "out", data_classification=classification)
    assert report.passed, report.to_dict()
    capsule = Path(report.capsule_path).parent
    envelope = json.loads(Path(report.envelope_path).read_text(encoding="utf-8"))
    parameters = json.loads((capsule / "parameters.json").read_text(encoding="utf-8"))
    crate = json.loads(Path(report.ro_crate_path).read_text(encoding="utf-8"))
    bco = json.loads(Path(report.bco_path).read_text(encoding="utf-8"))
    receipt = json.loads(Path(report.receipt_path).read_text(encoding="utf-8"))
    assert envelope["data_classification"] == classification
    assert parameters["data_classification"] == classification
    assert next(item for item in crate["@graph"] if item["@id"] == "./")["conditionsOfAccess"] == classification
    assert json.loads(next(item for item in bco["parametric_domain"] if item["param"] == "data_classification")["value"]) == classification
    assert receipt["data_classification"] == classification
    assert receipt["scope"] == "LOCAL_FILE_ROUNDTRIP_ONLY"
    assert receipt["producer_version_verification"] == "NOT_ASSESSED"


def test_unclassified_import_is_unknown():
    _, envelope = import_lab_source(PRODUCT_PATHS["scanpy"])
    assert envelope["data_classification"] == "UNKNOWN"


@pytest.mark.parametrize("status", ["DECLARED", "LIVE_VENDOR_UNVERIFIED", "UNSUPPORTED", "UNKNOWN"])
def test_unverified_adapter_status_cannot_pass_acceptance(status, monkeypatch, tmp_path):
    monkeypatch.setattr("bionexus.lab_exchange.get_product", lambda _: {"id": "scanpy", "status": status})
    report = accept_lab_roundtrip(PRODUCT_PATHS["scanpy"], tmp_path / "out")
    assert not report.passed
    assert report.gates[-1].name == "COMPAT" and not report.gates[-1].passed


def test_acceptance_reimports_exported_product(monkeypatch, tmp_path):
    calls = []
    actual_import = import_lab_source

    def observe_import(path, **kwargs):
        calls.append(Path(path))
        return actual_import(path, **kwargs)

    monkeypatch.setattr("bionexus.lab_exchange.import_lab_source", observe_import)
    report = accept_lab_roundtrip(PRODUCT_PATHS["scanpy"], tmp_path / "out")
    assert report.passed
    assert calls == [PRODUCT_PATHS["scanpy"], tmp_path / "out/capsule/results/imported"]


def test_acceptance_refuses_overwriting_previous_receipt(tmp_path):
    report = accept_lab_roundtrip(PRODUCT_PATHS["scanpy"], tmp_path / "out")
    original = Path(report.receipt_path).read_bytes()
    with pytest.raises(FileExistsError, match="overwrite"):
        accept_lab_roundtrip(PRODUCT_PATHS["scanpy"], tmp_path / "out")
    assert Path(report.receipt_path).read_bytes() == original


def test_duplicate_envelope_paths_refused(tmp_path):
    _, envelope = import_lab_source(PRODUCT_PATHS["scanpy"])
    duplicated = dict(envelope["source"]["files"][0], role="other")
    envelope["source"]["files"].append(duplicated)
    envelope["payload_sha256"] = canonical_json_sha256(envelope["source"]["files"])
    with pytest.raises(SchemaError, match="duplicate"):
        export_lab_capsule(envelope, PRODUCT_PATHS["scanpy"], tmp_path / "out")


def test_relative_output_persists_valid_receipt(monkeypatch, tmp_path):
    from bionexus.schema_registry import validate_document

    monkeypatch.chdir(tmp_path)
    report = accept_lab_roundtrip(PRODUCT_PATHS["scanpy"], "relative-out")
    assert report.passed, report.to_dict()
    receipt = json.loads(Path(report.receipt_path).read_text(encoding="utf-8"))
    assert validate_document(receipt).valid
    assert "capsule/run.json" in receipt["artifact_sha256"]


def test_nfcore_same_basename_in_distinct_directories_is_preserved(tmp_path):
    source = tmp_path / "nfcore"
    (source / "pipeline_info").mkdir(parents=True)
    (source / "samplesheet.csv").write_text("sample,fastq\ns1,input.fastq.gz\n", encoding="utf-8")
    nested = source / "pipeline_info/software_versions.yml"
    outer = source / "software_versions.yml"
    nested.write_text("nested_producer: 1.0\n", encoding="utf-8")
    outer.write_text("root_producer: 2.0\n", encoding="utf-8")
    _, envelope = import_lab_source(source)
    records = {item["relpath"]: item for item in envelope["source"]["files"]}
    assert {"pipeline_info/software_versions.yml", "software_versions.yml"} <= records.keys()
    assert records["pipeline_info/software_versions.yml"]["sha256"] != records["software_versions.yml"]["sha256"]
    report = accept_lab_roundtrip(source, tmp_path / "out")
    assert report.passed, report.to_dict()
    imported = Path(report.capsule_path).parent / "results/imported"
    assert (imported / "pipeline_info/software_versions.yml").read_bytes() == nested.read_bytes()
    assert (imported / "software_versions.yml").read_bytes() == outer.read_bytes()
    inputs = json.loads((Path(report.capsule_path).parent / "inputs.json").read_text(encoding="utf-8"))
    assert len(inputs) == 3
