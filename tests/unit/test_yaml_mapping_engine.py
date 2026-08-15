"""
Unit tests for Declarative YAML Instrument Mapping Engine.
"""

import pytest
import os
from pathlib import Path
from yaml_mapping_engine import (
    load_mapping_configs,
    match_instrument_rule,
    extract_metadata_from_rules,
    parse_with_yaml_mapping
)


def test_load_mapping_configs():
    """Verify that default instrument_mappings.yml loads cleanly."""
    config = load_mapping_configs()
    assert "instruments" in config
    instruments = config["instruments"]
    assert "tecan_infinite_m200" in instruments
    assert "biotek_synergy_h1" in instruments
    assert "thermo_nanodrop_one" in instruments


def test_extract_metadata_from_rules():
    """Verify metadata extraction across fixed, cell, and regex rules."""
    lines = [
        "Tecan Magellan Data Export",
        "Device: Tecan-Infinite-M200-SN1234",
        "User: Dr. Alice Smith",
        "Date: 2026-08-14"
    ]
    rules = {
        "device": {"strategy": "cell", "target": "A2"},
        "operator": {"strategy": "regex", "pattern": "^User:\\s*(.*)$"},
        "version": {"strategy": "fixed", "value": "1.0"}
    }
    extracted = extract_metadata_from_rules(lines, rules)
    assert extracted["operator"] == "Dr. Alice Smith"
    assert extracted["version"] == "1.0"


def test_parse_sample_plate_reader_csv(sample_plate_reader_csv):
    """Test full parsing of a sample Tecan plate reader export into ASM JSON."""
    asm = parse_with_yaml_mapping(sample_plate_reader_csv)
    assert asm is not None
    assert "$asm.manifest" in asm
    assert "measurement aggregate document" in asm

    meas_agg = asm["measurement aggregate document"]
    assert "device system document" in meas_agg
    assert "measurement document" in meas_agg

    meas_docs = meas_agg["measurement document"]
    assert len(meas_docs) > 0
    # Check first well measurement
    first_meas = meas_docs[0]
    assert "location identifier" in first_meas
    assert "sample identifier" in first_meas

    # Check custom provenance
    assert "custom metadata" in asm
    prov = asm["custom metadata"]["conversion provenance"]
    assert prov["matched_rule"] == "tecan_infinite_m200"
    assert prov["vendor"] == "Tecan"
