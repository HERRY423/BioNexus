"""Verify the frozen bilingual panels, scoring and publication contract."""
import csv
import hashlib
import json
from collections import Counter

import pytest

from bionexus.claim_semantics import detect_assertive_causal_language
from evals import inv009
from evals.metrics import wilson_interval

REPORT = inv009.CORPUS.parents[2] / "reports" / "inv009_metrics.json"


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def test_independent_panels_reproduce_checked_in_metrics():
    published = json.loads(REPORT.read_bytes())
    texts = set()
    for file_name, expected in (("inv009.tsv", published), ("inv009_panel1.tsv", published["earlier_panel_regression"])):
        path = inv009.CORPUS.with_name(file_name)
        raw = path.read_bytes()
        rows = list(csv.DictReader(raw.decode().splitlines(), delimiter="\t", quoting=csv.QUOTE_NONE))
        counts = Counter((r["language"], r["phenomenon"], r["label"]) for r in rows)
        assert len(counts) == 20 and set(counts.values()) == {5}
        assert not texts.intersection(r["statement"] for r in rows)
        texts.update(r["statement"] for r in rows)

        measured = inv009.score_panel(path)
        assert measured["corpus_sha256"] == expected["corpus_sha256"] == digest(raw)
        assert all(measured[k] == expected[k] for k in measured)
        assert measured["overall"]["evaluated"] == measured["overall"]["total"] == 100
        assert {k: v["total"] for k, v in measured["by_language"].items()} == {"en": 50, "zh": 50}
        assert {k: v["total"] for k, v in measured["by_phenomenon"].items()} == dict.fromkeys(inv009.PHENOMENA, 20)
        assert len(measured["errors"]) == measured["overall"]["false_positives"] + measured["overall"]["false_negatives"]
        assert measured["gate"]["passed"] == (measured["overall"]["recall_wilson_95"][0] >= .8)


def test_labels_and_original_measurements_remain_bound():
    root = inv009.CORPUS.parents[3]
    data = inv009.CORPUS.read_bytes()
    lock = json.loads(inv009.CORPUS.with_name("inv009_panel_lock.json").read_bytes())
    assert digest(data) == lock["corpus_sha256"]
    rows = list(csv.DictReader(data.decode().splitlines(), delimiter="\t", quoting=csv.QUOTE_NONE))
    for lang, sha in lock["original_sha256_by_language"].items():
        lines = ["\t".join(r[k] for k in lock["original_tsv_fields"]) + "\n" for r in rows if r["language"] == lang]
        assert digest("".join(lines).encode()) == sha
    earlier = json.loads(inv009.CORPUS.with_name("inv009_panel1_manifest.json").read_bytes())
    assert digest((root / earlier["panel"]).read_bytes()) == earlier["corpus_sha256"]
    assert digest((root / earlier["first_report"]).read_bytes()) == earlier["first_report_sha256"]
    assert digest((root / earlier["detector_patch"]).read_bytes()) == earlier["detector_patch_sha256"]


def test_cli_writes_report_and_propagates_gates(tmp_path, monkeypatch):
    output, summary = tmp_path / "metrics.json", tmp_path / "summary.md"
    rc = inv009.run_panel(output, summary)
    report = json.loads(output.read_bytes())
    assert rc == int(not report["passed_all_panels"])
    assert "Wilson 95%" in summary.read_text()
    assert report["passed_all_panels"] == (report["gate"]["passed"] and report["earlier_panel_regression"]["gate"]["passed"])
    monkeypatch.setattr(inv009, "MIN_RECALL_LOWER_95", 1.0)
    assert inv009.run_panel(output, summary) == 1
    assert output.is_file()


def test_published_rates_use_two_sided_wilson_intervals():
    assert wilson_interval(5, 5) == pytest.approx((.565517535217, 1))
    assert wilson_interval(9, 10) == pytest.approx((.5958499732, .9821237869))


@pytest.mark.parametrize(("statement", "asserted"), [
    ("The filter let the particles leave the chamber.", True),
    ("The manuscript removed the phrase “salinity drives growth”.", False),
    ("We conclude that excess moisture accelerated the decay.", True),
    ("Moisture could have resulted from colder storage.", False),
    pytest.param("The delay could have resulted from colder storage.", False, marks=pytest.mark.xfail(
        reason="INV-009 still reads the noun 'delay' as a resultative verb before an auxiliary", strict=True,
    )),
    ("这里的温差是因为保温层阻碍了散热。", True),
    ("原摘要删除了“光照导致弯曲”的表述。", False),
    ("微球的破裂使载荷释放出来。", True),
    ("蓝光可能加速了色素的衰变。", False),
])
def test_assertion_scope_and_event_predicates(statement, asserted):
    assert bool(detect_assertive_causal_language(statement)) == asserted
