"""Versioned schema validation, migration, and historical envelope regression."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bionexus.cli import main
from bionexus.schema_registry import (
    SchemaError,
    load_and_migrate,
    migrate_document,
    parse_schema_version,
    validate_document,
)

HISTORY = Path(__file__).resolve().parents[1] / "fixtures" / "lab_exchange" / "history"


def test_historical_v1_envelope_migrates_and_validates():
    migrated = load_and_migrate(HISTORY / "envelope.v1.json", family="lab-exchange-envelope")
    assert migrated["schema_version"] == "bionexus.lab-exchange-envelope.v2"
    assert migrated["producer"]["product"] == "deseq2"
    assert migrated["scientific_authorization"] == "NONE"
    result = validate_document(migrated, family="lab-exchange-envelope")
    assert result.valid, result.errors
    assert migrated["source"]["files"][0]["relpath"] == "results.csv"
    assert migrated["source"]["files"][0]["sha256"] == "a" * 64
    assert migrated["source"]["files"][0]["integrity_status"] == "DECLARED_UNVERIFIED"
    assert migrated["data_classification"] == "UNKNOWN"


def test_unknown_schema_version_fails_closed():
    result = validate_document({"schema_version": "bionexus.lab-exchange-envelope.v99"})
    assert result.valid is False
    assert "unregistered" in result.errors[0]
    with pytest.raises(SchemaError):
        migrate_document({"schema_version": "bionexus.lab-exchange-envelope.v99"})


def test_family_mismatch_is_invalid():
    document = json.loads((HISTORY / "envelope.v1.json").read_text(encoding="utf-8"))
    result = validate_document(document, family="failure-report")
    assert result.valid is False
    assert "mismatch" in result.errors[0]


def test_parse_schema_version():
    family, version = parse_schema_version({"schema_version": "bionexus.lab-exchange-envelope.v2"})
    assert family == "lab-exchange-envelope"
    assert version == "v2"


def test_cli_migrate_historical_envelope(tmp_path, capsys):
    dest = tmp_path / "envelope.v2.json"
    code = main(["deploy", "migrate", str(HISTORY / "envelope.v1.json"), "-o", str(dest), "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "bionexus.lab-exchange-envelope.v2"
    written = json.loads(dest.read_text(encoding="utf-8"))
    assert written["producer"]["product"] == "deseq2"


def test_invalid_source_schema_is_not_repaired_by_migration():
    with pytest.raises(SchemaError, match="source document failed validation"):
        migrate_document({"schema_version": "bionexus.lab-exchange-envelope.v1", "files": [{"path": "missing.tsv"}]})


@pytest.mark.parametrize("digest", ["legacyhash", "sha256:" + "a" * 64, "g" * 64])
def test_unverifiable_historical_digest_is_not_hashed_into_fake_sha256(digest):
    document = {
        "schema_version": "bionexus.lab-exchange-envelope.v1", "tool": "scanpy",
        "files": [{"path": "counts.tsv", "hash": digest}],
    }
    assert validate_document(document).valid
    with pytest.raises(SchemaError, match="original bytes are required"):
        migrate_document(document)
