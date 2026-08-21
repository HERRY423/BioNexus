from __future__ import annotations

import pandas as pd

from scripts.validate_c04_lims_pairing import validate


def _manifest() -> pd.DataFrame:
    rows = []
    for donor in range(12):
        participant = f"{donor + 1:064x}"
        for arm, reagent in (("ARM_A", "recombinant human IFN-beta-1a"), ("ARM_B", "vehicle")):
            index = len(rows)
            rows.append(
                {
                    "participant_id_hash": participant,
                    "aliquot_id": f"aliquot-{index}",
                    "opaque_arm_id": arm,
                    "collection_timestamp_utc": "2026-01-01T00:00:00Z",
                    "stimulation_start_utc": "2026-01-01T01:00:00Z",
                    "stimulation_stop_utc": "2026-01-01T07:00:00Z",
                    "reagent_name": reagent,
                    "reagent_lot": "LOT-1",
                    "pbmc_handling_mode": "fresh",
                    "pre_split_viability_percent": "95",
                    "library_id": f"library-{index}",
                    "sequencing_run_id": f"run-{index}",
                    "source_lims_record_sha256": f"{index + 1:064x}",
                }
            )
    return pd.DataFrame(rows)


def test_c04_lims_pairing_passes_without_emitting_identifiers(tmp_path):
    path = tmp_path / "manifest.csv"
    _manifest().to_csv(path, index=False)
    report = validate(path)
    assert report["status"] == "PASS"
    assert report["authoritative_pair_count"] == 12
    assert report["participant_identifiers_in_report"] is False


def test_c04_lims_pairing_abstains_on_bad_duration(tmp_path):
    path = tmp_path / "manifest.csv"
    frame = _manifest()
    frame.loc[0, "stimulation_stop_utc"] = "2026-01-01T08:00:00Z"
    frame.to_csv(path, index=False)
    report = validate(path)
    assert report["status"] == "ABSTAIN"
    assert any("duration" in issue for issue in report["issues"])
