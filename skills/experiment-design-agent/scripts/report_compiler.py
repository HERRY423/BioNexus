#!/usr/bin/env python3
"""
Preclinical Research Monograph & Study Report Compiler.
Compiles executive summaries, multi-omics analyses, 3D structural assessments,
into a research outline. Not a GxP or diagnostic document.
"""

import argparse
import datetime
import logging
from typing import Any, Dict, Optional

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("ReportCompiler")


def compile_research_monograph(
    plan: Dict[str, Any], evidence: Dict[str, Any], report_title: Optional[str] = None
) -> str:
    """Compile comprehensive preclinical research monograph in Markdown."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d")
    title = report_title or plan.get("study_title", "PRECLINICAL RESEARCH MONOGRAPH")
    target = plan.get("target_gene", "TARGET")
    disease = plan.get("disease_indication", "DISEASE")
    rec = evidence.get("recommendation", "GO")

    md = f"""# {title}
**BioNexus Preclinical Discovery & Translational Intelligence**
*Date: {now_str} | Target: {target} | Indication: {disease}*

---

## Executive Summary & Milestone Decision

### **Strategic Recommendation**: `{rec}`
- **Composite Preclinical Score**: `{evidence.get("composite_evidence_score", 0.0):.3f}`
- **Bayesian Posterior Success Probability**: `{evidence.get("bayesian_posterior_success", 0.0) * 100:.1f}%`
- **Strategic Rationale**: {evidence.get("rationale", "Comprehensive target validation completed.")}

---

## Multi-Dimensional Evidence Matrix

| Evidence Dimension | Score (0.0 - 1.0) | Weight | Status / Summary |
| :--- | :---: | :---: | :--- |
| **Genetics** | `{evidence.get("evidence_breakdown", {}).get("genetics", 0.0):.2f}` | 25% | Caller-supplied placeholder |
| **Structural tractability** | `{evidence.get("evidence_breakdown", {}).get("structural_druggability", 0.0):.2f}` | 20% | Caller-supplied placeholder |
| **Chemogenomics** | `{evidence.get("evidence_breakdown", {}).get("chemogenomics", 0.0):.2f}` | 15% | Caller-supplied placeholder |
| **Single-cell** | `{evidence.get("evidence_breakdown", {}).get("single_cell_specificity", 0.0):.2f}` | 15% | Caller-supplied placeholder |
| **Spatial** | `{evidence.get("evidence_breakdown", {}).get("spatial_microenvironment", 0.0):.2f}` | 15% | Caller-supplied placeholder |
| **Clinical genomics** | `{evidence.get("evidence_breakdown", {}).get("clinical_genomics", 0.0):.2f}` | 10% | Caller-supplied placeholder |

---

## 5-Phase Preclinical Investigation Roadmap

"""
    for phase in plan.get("phases", []):
        md += f"### Phase {phase.get('phase_number')}: {phase.get('phase_title')}\n"
        md += f"- **Objective**: {phase.get('objective')}\n"
        md += "- **Computational Methods**:\n"
        for m in phase.get("computational_methods", []):
            md += f"  - {m}\n"
        md += f"- **Go/No-Go Milestone**: `{phase.get('milestone_go_no_go')}`\n\n"

    md += f"""---

## Risk Assessment & Critical Mitigation

> **Critical Vulnerability**: {plan.get("risk_assessment", {}).get("critical_risk", "On-target toxicity")}
> **Mitigation Strategy**: {plan.get("risk_assessment", {}).get("mitigation_strategy", "Select prodrug or targeted delivery")}

---

## FAIR Data & Computational Provenance
- Outline only. Attach `bionexus.provenance.sidecar` hashes if files exist.
- Not 21 CFR Part 11 / GxP / ALCOA+.
"""
    return md


def main():
    parser = argparse.ArgumentParser(description="Preclinical Report Compiler")
    parser.add_argument("--target", "-t", required=True, help="Target gene symbol")
    parser.add_argument("--disease", "-d", required=True, help="Disease indication")
    parser.add_argument("--out", "-o", default="research_monograph.md", help="Output Markdown path")

    args = parser.parse_args()
    from evidence_synthesizer import synthesize_multimodal_evidence
    from research_planner import create_preclinical_research_plan

    plan = create_preclinical_research_plan(args.target, args.disease)
    evidence = synthesize_multimodal_evidence(args.target, args.disease)
    report_md = compile_research_monograph(plan, evidence)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(report_md)
    logger.info(f"Compiled research monograph to {args.out}")


if __name__ == "__main__":
    main()
