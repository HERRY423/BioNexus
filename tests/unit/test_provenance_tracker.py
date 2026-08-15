"""
Unit tests for FAIR Provenance Tracker and Publication Methods Generator.
"""

import shutil
import tempfile
from pathlib import Path

# Add skill script directories to path
SKILL_ROOT = Path(__file__).parent.parent.parent / "skills" / "provenance-and-audit" / "scripts"
import sys

sys.path.insert(0, str(SKILL_ROOT))

from methods_generator import generate_methods_text
from provenance_tracker import ProvenanceTracker, capture_environment_snapshot


def test_environment_snapshot_capture():
    """Verify capture of OS, Python version, and core packages."""
    env = capture_environment_snapshot()
    assert "os_name" in env
    assert "python_version" in env
    assert "packages" in env
    assert isinstance(env["packages"], dict)


def test_provenance_tracking_and_w3c_provo():
    """Verify input/output tracking, hashing, and W3C PROV-O JSON-LD generation."""
    temp_dir = tempfile.mkdtemp()
    dummy_input = Path(temp_dir) / "raw_input.txt"
    dummy_input.write_text("dummy single cell counts")
    dummy_output = Path(temp_dir) / "filtered_output.txt"
    dummy_output.write_text("filtered counts data")

    tracker = ProvenanceTracker(
        activity_name="Single-Cell QC Analysis",
        operator="Test Scientist",
        notes="Automated unit test"
    )

    tracker.record_input_file(str(dummy_input), role="raw_matrix")
    tracker.record_parameters({"mad_counts": 5.0, "mt_threshold": 8.0, "run_doublets": True})
    tracker.record_output_file(str(dummy_output), role="cleaned_matrix")

    prov_record = tracker.finalize(output_dir=temp_dir)

    assert prov_record["activity_name"] == "Single-Cell QC Analysis"
    assert len(prov_record["input_files"]) == 1
    assert len(prov_record["output_files"]) == 1

    # Check W3C PROV-O structure
    prov_o = prov_record["w3c_prov_o"]
    assert "@context" in prov_o
    assert "@graph" in prov_o
    assert any(item.get("@type") == "prov:Activity" for item in prov_o["@graph"])
    assert any(item.get("@type") == "prov:Entity" for item in prov_o["@graph"])

    # Test Methods text generation
    methods_text = generate_methods_text(prov_record)
    assert "Methods: Single-Cell QC Analysis" in methods_text
    assert "Median Absolute Deviation" in methods_text
    assert "SHA-256 Checksum" in methods_text

    shutil.rmtree(temp_dir, ignore_errors=True)
