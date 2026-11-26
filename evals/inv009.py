"""Score BioFailureBench's fixed bilingual INV-009 panel against the verify detector."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from evals.metrics import compute_causal_language_metrics
from evals.runner import run_single_case
from evals.schema import EvalCase, EvalCategory, EvalLevel, ExpectedStatus

CORPUS = Path(__file__).parent / "datasets" / "benchmarks" / "inv009.tsv"
MIN_RECALL_LOWER_95 = 0.80
PHENOMENA = {"direct", "negation", "quotation", "paraphrase", "hedging"}


def score_panel(path: Path = CORPUS) -> dict:
    """Include both classes in every language and every linguistic stratum."""
    raw = path.read_bytes()
    rows = list(csv.DictReader(raw.decode("utf-8").splitlines(), delimiter="\t", quoting=csv.QUOTE_NONE))
    if len(rows) < 100:
        raise ValueError("INV-009 requires at least 100 statements")
    seen_ids = set()
    seen_texts = set()
    strata = Counter()
    scores = []
    for row in rows:
        cid, lang, phenomenon, label, statement = (row[k] for k in ("id", "language", "phenomenon", "label", "statement"))
        normalized = " ".join(statement.casefold().split())
        if not cid or cid in seen_ids or not normalized or normalized in seen_texts:
            raise ValueError(f"Empty or duplicate INV-009 ID or statement: {cid}")
        if lang not in {"en", "zh"} or phenomenon not in PHENOMENA or label not in {"positive", "negative"}:
            raise ValueError(f"Invalid INV-009 annotation: {cid}")
        seen_ids.add(cid)
        seen_texts.add(normalized)
        strata[lang, phenomenon, label] += 1
        expected = ExpectedStatus.ABSTAIN if label == "positive" else ExpectedStatus.PERMITTED
        case = EvalCase(id=cid, category=EvalCategory.CAUSAL_LANGUAGE, level=EvalLevel.L2_AGENT,
                        prompt=statement, expected_status=expected)
        scores.append(run_single_case(case))
    for lang in ("en", "zh"):
        for phenomenon in PHENOMENA:
            pos = strata[lang, phenomenon, "positive"]
            neg = strata[lang, phenomenon, "negative"]
            if min(pos, neg) == 0 or min(pos, neg) / (pos + neg) < .4:
                raise ValueError(f"Missing or unbalanced INV-009 labels for {lang}/{phenomenon}")

    overall = compute_causal_language_metrics(scores)
    recall_interval = overall["recall_wilson_95"]
    passed = (overall["evaluated"] == overall["total"] and recall_interval is not None
              and recall_interval[0] >= MIN_RECALL_LOWER_95)
    return {
        "schema": "bionexus.inv009_metrics.v1",
        "corpus_sha256": hashlib.sha256(raw).hexdigest(),
        "detector_source_sha256": hashlib.sha256(
            (Path(__file__).resolve().parents[1] / "src/bionexus/claims/parser.py").read_bytes()
        ).hexdigest(),
        "positive_class": "The author asserts a causal relationship in the submitted statement.",
        "scope": "Fixed bilingual sentences labeled for causal assertion. Evidence sufficiency is outside this score.",
        "overall": overall,
        "by_language": {
            lang: compute_causal_language_metrics([r for item, r in zip(rows, scores) if item["language"] == lang])
            for lang in ("en", "zh")
        },
        "by_phenomenon": {
            kind: compute_causal_language_metrics([r for item, r in zip(rows, scores) if item["phenomenon"] == kind])
            for kind in sorted(PHENOMENA)
        },
        "errors": [
            {**item, "predicted_label": "positive" if r.actual_status == "ABSTAIN" else "negative"}
            for item, r in zip(rows, scores) if not r.passed
        ],
        "gate": {"metric": "overall.recall_wilson_95[0]", "minimum": MIN_RECALL_LOWER_95, "passed": passed},
    }


def run_panel(output: Path, summary: Path | None = None) -> int:
    report = score_panel()
    first_panel = score_panel(CORPUS.with_name("inv009_panel1.tsv"))
    report["earlier_panel_regression"] = first_panel
    report["passed_all_panels"] = report["gate"]["passed"] and first_panel["gate"]["passed"]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["## BioFailureBench INV-009", "",
             "| Language | Scored | Precision (Wilson 95%) | Recall (Wilson 95%) | TP | FP | FN | TN |",
             "|---|---|---|---|---|---|---|---|"]
    for label, metrics in [("All", report["overall"]), *report["by_language"].items()]:
        cells = [label, f"{metrics['evaluated']}/{metrics['total']}"]
        for name in ("precision", "recall"):
            interval = metrics[name + "_wilson_95"]
            cells.append(f"{metrics[name]:.1%} [{interval[0]:.1%}, {interval[1]:.1%}]" if interval else "N/A")
        cells.extend(str(metrics[k]) for k in ("true_positives", "false_positives", "false_negatives", "true_negatives"))
        lines.append("| " + " | ".join(cells) + " |")
    lines.extend(["", f"Required recall lower bound ≥ {MIN_RECALL_LOWER_95:.0%} for each panel.",
                  "Final panel: " + ("PASS" if report["gate"]["passed"] else "FAIL"),
                  "Earlier panel regression: " + ("PASS" if first_panel["gate"]["passed"] else "FAIL")])
    markdown = "\n".join(lines) + "\n"
    print(markdown)
    if summary is not None:
        with summary.open("a", encoding="utf-8") as out:
            out.write(markdown)
    return 0 if report["passed_all_panels"] else 1
