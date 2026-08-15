#!/usr/bin/env python3
"""Research-use variant interpretation summary.

Not a clinical diagnostic report. Does not claim CLIA/CAP accreditation.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
from typing import Any, Dict

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("ClinicalReportGenerator")


def generate_clinical_report_markdown(
    variant_eval: Dict[str, Any],
    patient_id: str = "UNSPECIFIED",
    indication: str = "Research interpretation",
    clinician_name: str = "Not applicable",
    report_title: str = "RESEARCH VARIANT INTERPRETATION SUMMARY",
) -> str:
    """Render a research summary from an ACMG combiner result."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    gene = variant_eval.get("gene_symbol", "UNKNOWN")
    variant = variant_eval.get("variant_id", "UNKNOWN")
    classification = variant_eval.get("deterministic_classification", "Uncertain Significance")
    posterior = float(variant_eval.get("posterior_probability_pathogenic", 0.0) or 0.0)
    criteria = variant_eval.get("criteria_breakdown", [])

    if "Pathogenic" in classification and "Likely" not in classification:
        badge = "PATHOGENIC (combiner output; research-use only)"
    elif "Likely Pathogenic" in classification:
        badge = "LIKELY PATHOGENIC (combiner output; research-use only)"
    elif "Benign" in classification:
        badge = "BENIGN / LIKELY BENIGN (combiner output; research-use only)"
    else:
        badge = "UNCERTAIN SIGNIFICANCE / INSUFFICIENT EVIDENCE"

    md = f"""# {report_title}

**Research-use only. This is not a clinical diagnostic report, not CLIA/CAP accredited, and not medical advice.**

| Field | Value |
| :--- | :--- |
| Record ID | `{patient_id}` |
| Context | {indication} |
| Prepared for | {clinician_name} |
| Generated | {now_str} |

## Variant summary

| Gene | Variant | Combiner class | Tavtigian posterior |
| :---: | :---: | :---: | :---: |
| **{gene}** | `{variant}` | **{classification}** | {posterior:.5f} |

Status: {badge}

## Supplied ACMG/AMP codes

Criteria below are **exactly those provided by the caller**. This tool does not independently verify them.

| Code | Strength | Name | Caller note |
| :--- | :--- | :--- | :--- |
"""
    for item in criteria:
        md += (
            f"| **{item.get('code')}** | `{item.get('strength')}` | "
            f"{item.get('name')} | {item.get('user_evidence')} |\n"
        )

    md += f"""
## Combiner arithmetic

- Odds of pathogenicity = {variant_eval.get("odds_of_pathogenicity", 1.0):.2f}
- Posterior uses prior 0.10 (Tavtigian et al. 2018) on the supplied codes only.

## Limitations

- Missing gnomAD, ClinVar, or VEP evidence is **not** treated as PM2 or PP3.
- PVS1 strength modification (Abou Tayoun 2018) is not applied automatically.
- Do not paste this text into a patient chart as a laboratory report.
"""
    return md


def main() -> None:
    parser = argparse.ArgumentParser(description="Research variant interpretation summary")
    parser.add_argument("--variant", "-v", required=True)
    parser.add_argument("--gene", "-g", required=True)
    parser.add_argument("--classification", "-c", default="Uncertain Significance")
    parser.add_argument("--output", "-o", default="research_variant_summary.md")
    args = parser.parse_args()
    eval_res = {
        "variant_id": args.variant,
        "gene_symbol": args.gene,
        "deterministic_classification": args.classification,
        "posterior_probability_pathogenic": None,
        "odds_of_pathogenicity": 1.0,
        "criteria_breakdown": [],
    }
    md = generate_clinical_report_markdown(eval_res)
    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(md)
    print(json.dumps({"output": args.output, "research_use_only": True}, indent=2))


if __name__ == "__main__":
    main()
