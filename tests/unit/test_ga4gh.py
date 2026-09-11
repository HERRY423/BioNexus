"""Unit tests for GA4GH DRS v1.2.0 and Phenopackets v2 (BNS-016 §GA4GH)."""

import json

import pytest

from bionexus.cli import main as cli_main
from bionexus.ga4gh import (
    DRSChecksum,
    Individual,
    OntologyClass,
    create_drs_object,
    export_donor_phenopacket,
)


def test_drs_checksum_validation():
    # Valid sha-256
    c = DRSChecksum(type="sha-256", checksum="a" * 64)
    assert c.type == "sha-256"
    assert c.to_dict()["checksum"] == "a" * 64

    # Valid md5
    c_md5 = DRSChecksum(type="md5", checksum="b" * 32)
    assert c_md5.type == "md5"

    # Invalid type
    with pytest.raises(ValueError, match="Invalid checksum type"):
        DRSChecksum(type="crc32", checksum="12345678")

    # Invalid hex
    with pytest.raises(ValueError, match="not a valid hex digest"):
        DRSChecksum(type="sha-256", checksum="z" * 64)

    # Invalid length
    with pytest.raises(ValueError, match="sha-256 checksum must be 64 hex characters"):
        DRSChecksum(type="sha-256", checksum="a" * 60)


def test_drs_object_creation(tmp_path):
    test_file = tmp_path / "experiment_counts.h5ad"
    test_file.write_bytes(b"DATA-MATRIX-BYTES-12345678")

    drs = create_drs_object(
        file_path=test_file,
        drs_id="obj_exp_001",
        authority="ga4gh.bionexus.org",
        mime_type="application/x-hdf5",
        description="Single cell count matrix",
    )

    assert drs.id == "obj_exp_001"
    assert drs.self_uri == "drs://ga4gh.bionexus.org/obj_exp_001"
    assert drs.size == len(b"DATA-MATRIX-BYTES-12345678")
    assert len(drs.checksums) >= 2
    types = {c.type for c in drs.checksums}
    assert "sha-256" in types
    assert "md5" in types
    assert len(drs.access_methods) >= 1
    assert drs.access_methods[0].type == "file"

    drs_json = drs.to_dict()
    assert drs_json["id"] == "obj_exp_001"
    assert drs_json["size"] == 26
    assert drs_json["mime_type"] == "application/x-hdf5"


def test_drs_object_missing_file_fails_closed(tmp_path):
    missing_file = tmp_path / "non_existent.csv"
    with pytest.raises(FileNotFoundError):
        create_drs_object(missing_file, drs_id="missing_001")


def test_phenopacket_ontology_class():
    valid = OntologyClass(id="HP:0001250", label="Seizure")
    assert valid.id == "HP:0001250"
    assert valid.to_dict() == {"id": "HP:0001250", "label": "Seizure"}

    # Malformed CURIE
    with pytest.raises(ValueError, match="does not match standard CURIE pattern"):
        OntologyClass(id="NOT_A_CURIE", label="Invalid")

    # Empty label
    with pytest.raises(ValueError, match="label must be provided"):
        OntologyClass(id="HP:0001250", label="")


def test_phenopacket_individual_controlled_vocabulary():
    ind = Individual(id="DONOR-42", sex="FEMALE")
    assert ind.sex == "FEMALE"
    assert ind.to_dict()["id"] == "DONOR-42"
    assert ind.to_dict()["taxonomy"]["id"] == "NCBITaxon:9606"

    with pytest.raises(ValueError, match="Invalid sex"):
        Individual(id="DONOR-42", sex="NOT_CONTROLLED")

    with pytest.raises(ValueError, match="id must be a non-empty string"):
        Individual(id="")


def test_export_donor_phenopacket():
    pheno = export_donor_phenopacket(
        donor_id="PATIENT_IFNB_01",
        sex="FEMALE",
        disease_terms=[{"id": "MONDO:0005015", "label": "Diabetes mellitus"}],
        phenotype_terms=[{"id": "HP:0001250", "label": "Seizure", "excluded": False}],
    )

    doc = pheno.to_dict()
    assert doc["id"] == "phenopacket_PATIENT_IFNB_01"
    assert doc["subject"]["id"] == "PATIENT_IFNB_01"
    assert doc["subject"]["sex"] == "FEMALE"
    assert len(doc["diseases"]) == 1
    assert doc["diseases"][0]["term"]["id"] == "MONDO:0005015"
    assert len(doc["phenotypic_features"]) == 1
    assert doc["phenotypic_features"][0]["type"]["id"] == "HP:0001250"
    assert doc["meta_data"]["phenopacket_schema_version"] == "2.0"
    assert any(r["namespace_prefix"] == "HP" for r in doc["meta_data"]["resources"])
    assert any(r["namespace_prefix"] == "MONDO" for r in doc["meta_data"]["resources"])


def test_ga4gh_cli_drs_descriptor(tmp_path, capsys):
    f = tmp_path / "sample_reads.fastq"
    f.write_text("@read1\nACGT\n+\nIIII\n", encoding="utf-8")

    ret = cli_main(["ga4gh", "drs-descriptor", str(f), "--id", "DRS-READ-01"])
    assert ret == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["id"] == "DRS-READ-01"
    assert data["self_uri"] == "drs://bionexus.local/DRS-READ-01"
    assert any(c["type"] == "sha-256" for c in data["checksums"])


def test_ga4gh_cli_phenopacket(tmp_path, capsys):
    out_file = tmp_path / "phenopacket.json"
    ret = cli_main([
        "ga4gh",
        "phenopacket",
        "DONOR-99",
        "--sex",
        "MALE",
        "--disease",
        "MONDO:0005015:Diabetes",
        "--phenotype",
        "HP:0001250:Seizure",
        "-o",
        str(out_file),
    ])
    assert ret == 0
    assert out_file.is_file()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["subject"]["id"] == "DONOR-99"
    assert data["subject"]["sex"] == "MALE"
    assert data["diseases"][0]["term"]["id"] == "MONDO:0005015"
