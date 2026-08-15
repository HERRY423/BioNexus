"""Doctor hard gate (no CellTypePilot coupling)."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bio_research.gate import require_doctor, write_doctor_report


def test_doctor_report_roundtrip():
    path = PROJECT_ROOT / "tests" / "_tmp_doctor_report.json"
    try:
        report = write_doctor_report(path)
        assert report["tier"] in {"full", "degraded", "refuse"}
        assert "ready" in report
        assert "scverse_ready" in report["ready"]
        loaded = require_doctor(path=path, skip=False)
        assert loaded["gate"] in {"cached", "fresh"}
    finally:
        if path.exists():
            path.unlink()


def test_require_doctor_skip_does_not_write():
    path = PROJECT_ROOT / "tests" / "_tmp_doctor_missing.json"
    if path.exists():
        path.unlink()
    report = require_doctor(path=path, skip=True)
    assert report["gate"] == "skipped"
    assert not path.exists()


def test_doctor_does_not_mention_celltypepilot():
    from bio_research.doctor import run_doctor

    report = run_doctor()
    blob = json_blob(report)
    assert "celltypepilot" not in blob
    assert "CellTypePilot" not in blob


def json_blob(obj) -> str:
    import json

    return json.dumps(obj, default=str)
