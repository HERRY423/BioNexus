"""Pilot evidence accounting: unresolved, negative and missing outcomes stay visible."""
import json

import pytest

from bionexus.cli import main
from bionexus.de_audit import audit_differential_expression
from bionexus.de_pilot import demo_inputs, summarize_reviews, write_bundle


def test_bundle_writer_accepts_an_independent_report_adapter(tmp_path):
    """The persistence boundary needs report methods, not engine inheritance."""
    from bionexus.de_bundle import verify_de_bundle

    payload = audit_differential_expression(**demo_inputs()).to_dict()

    class ImportedReport:
        def to_dict(self):
            return payload

        def to_markdown(self):
            return "# Imported audit\n\nUnverified external report.\n"

    path = write_bundle(ImportedReport(), tmp_path / "imported", inputs={}, claim=None)
    assert (path / "audit-full.md").read_text(encoding="utf-8").startswith("# Imported audit")
    assert verify_de_bundle(path)["status"] == "CONSISTENT"
    assert _read(path / "manifest.json")["scientific_authorization"] == "NONE"


def _bundle(tmp_path, name="case", synthetic=False):
    result = audit_differential_expression(**demo_inputs())
    directory = write_bundle(result, tmp_path / name, inputs={}, claim="synthetic test", synthetic=synthetic)
    return directory / "review.json"


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path, record):
    path.write_text(json.dumps(record), encoding="utf-8")


def _complete(path):
    record = _read(path)
    record.update(review_status="COMPLETE", site_id="TEST_SITE", reviewer_name="Test reviewer")
    record["reference_review"] = {
        "reviewer_name": "Test reference reviewer", "reviewed_before_audit": True,
        "issues": [{"issue_id": "R1", "description": "A planted missing correction"},
                   {"issue_id": "R2", "description": "A planted missed issue"}],
    }
    for item in record["finding_judgments"]:
        item.update(judgment="CONFIRMED", reference_issue_id="R1", note="Test fixture judgment")
    record["timing"].update(comparison="PAIRED_SAME_CASE", baseline_review_minutes=10,
                            assisted_review_minutes=15, setup_minutes=2, repair_minutes=3)
    record["would_reuse"] = False
    _save(path, record)
    return record


def test_pending_and_demo_never_become_benefit(tmp_path):
    pending = _bundle(tmp_path, "pending")
    demo = _bundle(tmp_path, "demo", synthetic=True)
    # Same audit at an explicitly different site is allowed; it remains excluded.
    record = _read(demo)
    record["site_id"] = "DEMO"
    _save(demo, record)
    report = summarize_reviews([pending, demo])
    assert report["included_cases"] == 0
    assert report["net_benefit"] == "NOT_ESTABLISHED"
    assert report["mean_review_minutes_saved"] is None
    assert {c["excluded_reason"] for c in report["cases"]} == {"pending_review", "synthetic_demo"}


def test_negative_time_and_missed_issue_retained(tmp_path):
    path = _bundle(tmp_path)
    _complete(path)
    report = summarize_reviews([path])
    assert report["mean_review_minutes_saved"] == -5
    assert report["mean_minutes_saved_after_setup_and_repair"] == -10
    assert report["counts"]["detected_reference_issues"] == 1
    assert report["counts"]["missed_reference_issues"] == 1
    assert report["feedback"]["would_reuse"] == {"answered": 1, "yes": 0, "no": 1}
    assert report["external_validation"] == "NOT_ESTABLISHED"
    assert report["fully_costed_cases"] == 0
    assert report["setup_and_repair_costed_cases"] == 1
    assert report["schema"] == "bionexus.de-pilot-summary.v2"


def test_full_costs_can_reverse_apparent_review_gain(tmp_path):
    from bionexus.pilot_costs import COST_FIELDS
    path = _bundle(tmp_path)
    record = _complete(path)
    record["costs"].update(comparison="PAIRED_SAME_CASE", allocation_note="one case; installation charged once")
    for arm in ("baseline", "assisted"):
        record["costs"][arm] = dict.fromkeys(COST_FIELDS, 0)
    record["costs"]["baseline"]["review"] = 20
    record["costs"]["assisted"].update(review=5, installation=5, repair=5, false_alarm_handling=5, communication=5)
    _save(path, record)
    report = summarize_reviews([path])
    assert report["mean_full_person_minutes_saved"] == -5
    assert report["fully_costed_cases"] == 1


def test_missing_costs_and_unpaired_times_are_unknown(tmp_path):
    path = _bundle(tmp_path)
    record = _complete(path)
    record["timing"]["setup_minutes"] = None
    _save(path, record)
    assert summarize_reviews([path])["mean_minutes_saved_after_setup_and_repair"] is None
    record["timing"]["comparison"] = "UNPAIRED"
    _save(path, record)
    assert summarize_reviews([path])["mean_review_minutes_saved"] is None


def test_unresolved_not_counted_as_false_alarm_or_miss(tmp_path):
    path = _bundle(tmp_path)
    record = _complete(path)
    for item in record["finding_judgments"]:
        item.update(judgment="UNRESOLVED", reference_issue_id="R1")
    _save(path, record)
    report = summarize_reviews([path])
    assert report["counts"]["false_alarm_findings"] == 0
    assert report["counts"]["unresolved_reference_issues"] == 1
    assert report["counts"]["missed_reference_issues"] == 1


@pytest.mark.parametrize("mutation", ["hash", "duplicate", "omit", "negative", "nan", "blind", "origin", "unknown_ref"])
def test_invalid_observations_cannot_enter_summary(tmp_path, mutation):
    path = _bundle(tmp_path)
    record = _complete(path)
    if mutation == "hash":
        record["audit_sha256"] = "0" * 64
    elif mutation == "duplicate":
        with pytest.raises(ValueError, match="Duplicate"):
            summarize_reviews([path, path])
        return
    elif mutation == "omit":
        record["finding_judgments"] = []
    elif mutation == "negative":
        record["timing"]["assisted_review_minutes"] = -1
    elif mutation == "nan":
        record["timing"]["assisted_review_minutes"] = float("nan")
    elif mutation == "blind":
        record["reference_review"]["reviewed_before_audit"] = False
    elif mutation == "origin":
        record["data_origin"] = "SYNTHETIC_DEMO"
    elif mutation == "unknown_ref":
        record["finding_judgments"][0]["reference_issue_id"] = "UNKNOWN"
    _save(path, record)
    with pytest.raises(ValueError):
        summarize_reviews([path])


def test_existing_bundle_never_overwritten(tmp_path):
    path = _bundle(tmp_path)
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        _bundle(tmp_path)
    assert path.read_bytes() == before


def test_cli_demo_to_pending_summary(tmp_path, capsys):
    directory = tmp_path / "demo"
    assert main(["audit-de", "--demo", "--bundle", str(directory)]) == 1
    assert (directory / "REVIEW.md").is_file()
    assert "合成教学示例" in (directory / "REVIEW.md").read_text(encoding="utf-8")
    assert "finding" not in (directory / "reference-review.json").read_text(encoding="utf-8")
    assert main(["audit-de-summary", str(directory / "review.json"), "--json"]) == 0
    assert '"included_cases": 0' in capsys.readouterr().out


def test_cli_rejects_demo_mixed_with_user_data(tmp_path):
    assert main(["audit-de", "--demo", "--de-table", "real.csv", "--bundle", str(tmp_path / "bad")]) == 1
    assert not (tmp_path / "bad").exists()


@pytest.mark.parametrize("numeric_donors", [False, True])
def test_cli_hashes_inputs_and_keeps_them_readonly(tmp_path, numeric_donors):
    table, samples = tmp_path / "de.csv", tmp_path / "samples.csv"
    data = demo_inputs()
    if numeric_donors:
        data["sample_metadata"]["donor"] = list(range(1, 7))
    data["de_table"].to_csv(table, index=False)
    data["sample_metadata"].to_csv(samples, index=False)
    before = (table.read_bytes(), samples.read_bytes())
    directory = tmp_path / "review"
    assert main(["audit-de", "--de-table", str(table), "--sample-sheet", str(samples), "--bundle", str(directory), "--json"]) == 1
    assert before == (table.read_bytes(), samples.read_bytes())
    manifest = _read(directory / "manifest.json")
    assert set(manifest["inputs"]) == {"de_table", "sample_sheet"}
    assert not (directory / "de.csv").exists()


def test_false_alarm_on_clean_reference_and_unanswered_feedback(tmp_path):
    path = _bundle(tmp_path)
    record = _complete(path)
    record["reference_review"]["issues"] = []
    record["would_reuse"] = None
    for item in record["finding_judgments"]:
        item.update(judgment="FALSE_ALARM", reference_issue_id=None, note="Correct analysis in this test reference")
    _save(path, record)
    report = summarize_reviews([path])
    assert report["reference_negative_cases"] == 1
    assert report["reference_negative_cases_with_false_alarms"] == 1
    assert report["counts"]["missed_reference_issues"] == 0
    assert report["feedback"]["would_reuse"]["answered"] == 0


def test_cli_summary_does_not_overwrite_or_promote_pending(tmp_path):
    path = _bundle(tmp_path)
    output = tmp_path / "observations.md"
    assert main(["audit-de-summary", str(path), "--out", str(output)]) == 0
    before = output.read_bytes()
    assert main(["audit-de-summary", str(path), "--out", str(output)]) == 1
    assert output.read_bytes() == before


def test_input_change_during_audit_refuses_bundle(tmp_path, monkeypatch):
    from bionexus import de_audit

    table = tmp_path / "de.csv"
    demo_inputs()["de_table"].to_csv(table, index=False)
    original = de_audit.audit_differential_expression

    def changed(**kwargs):
        result = original(**kwargs)
        table.write_text("changed", encoding="utf-8")
        return result

    monkeypatch.setattr(de_audit, "audit_differential_expression", changed)
    directory = tmp_path / "changed"
    assert main(["audit-de", "--de-table", str(table), "--bundle", str(directory)]) == 1
    assert not directory.exists()
