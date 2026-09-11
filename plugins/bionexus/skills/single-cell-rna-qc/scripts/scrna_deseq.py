#!/usr/bin/env python3
"""pydeseq2 on a pseudobulk counts table + design TSV. Refuses if pydeseq2 is missing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.backends import require
from bionexus.contracts import GRADE_A, attach_meta
from bionexus.integrity import ScientificInputError, require_replicate_design


def run_pydeseq2(
    counts,
    design,
    *,
    condition: str,
    donor: str | None = None,
    reference: str | None = None,
    contrast_level: str | None = None,
):
    counts, design, replicate_counts = require_replicate_design(
        counts,
        design,
        condition=condition,
        min_replicates_per_level=2,
    )
    # Conversion is lossless only after the fail-closed integer-count gate.
    counts = counts.astype(int)

    if donor is not None:
        if donor not in design.columns:
            raise ScientificInputError(f"donor '{donor}' not found in design columns {list(design.columns)}")
        if design[donor].isna().any():
            raise ScientificInputError(f"donor '{donor}' contains missing values")
        if design[donor].nunique() < 2:
            raise ScientificInputError(
                f"donor '{donor}' must contain at least two unique levels; found {design[donor].nunique()}"
            )
        import pandas as pd

        design[donor] = design[donor].astype(str)
        design[condition] = design[condition].astype(str)

        # Check unidentifiable / rank-deficient / completely collinear design
        ct = pd.crosstab(design[donor], design[condition])
        conditions_per_donor = (ct > 0).sum(axis=1)
        if (conditions_per_donor <= 1).all():
            raise ScientificInputError(
                f"donor '{donor}' is completely collinear with condition '{condition}'; "
                "each donor is observed in only one condition level, making the paired design unidentifiable"
            )

    require("pydeseq2", for_method="run_pydeseq2")
    from pydeseq2.dds import DeseqDataSet
    from pydeseq2.ds import DeseqStats

    levels = list(design[condition].astype(str).unique())
    if len(levels) < 2:
        raise ValueError(f"condition '{condition}' has <2 levels")
    ref = reference or levels[0]
    alt = contrast_level or next(lv for lv in levels if lv != ref)

    if donor is not None:
        design_str = f"~ {donor} + {condition}"
        design_factors_arg = [donor, condition]
    else:
        design_str = f"~ {condition}"
        design_factors_arg = condition

    try:
        dds = DeseqDataSet(counts=counts, metadata=design, design=design_str, refit_cooks=True)
    except TypeError:
        dds = DeseqDataSet(counts=counts, metadata=design, design_factors=design_factors_arg, refit_cooks=True)
    dds.deseq2()
    stats = DeseqStats(dds, contrast=[condition, alt, ref])
    stats.summary()
    table = stats.results_df.reset_index().rename(columns={"index": "gene"})

    meta = {
        "n_samples": int(counts.shape[0]),
        "n_genes": int(counts.shape[1]),
        "condition": condition,
        "contrast": [condition, alt, ref],
        "replicates_per_level": replicate_counts,
        "raw_integer_counts_verified": True,
        "n_tested": int(len(table)),
        "paired": donor is not None,
        "design_formula": design_str,
    }
    if donor is not None:
        meta["donor"] = donor
        meta["n_donors"] = int(design[donor].nunique())

    return table, attach_meta(
        meta,
        method="pydeseq2.DeseqStats",
        backend="pydeseq2",
        evidence_grade=GRADE_A,
        limitations=["Wald tests on aggregated counts. This is not DESeq2-in-R and not rank_genes_groups."],
    )


def _read_table(path: Path):
    import pandas as pd

    if path.suffix.lower() == ".tsv":
        return pd.read_csv(path, sep="\t", index_col=0)
    return pd.read_csv(path, index_col=0)


def main() -> None:
    parser = argparse.ArgumentParser(description="pydeseq2 on pseudobulk counts")
    parser.add_argument("counts", help="Counts CSV/TSV (samples x genes)")
    parser.add_argument("--design", required=True, help="Design TSV/CSV with the same sample index")
    parser.add_argument("--condition", required=True, help="Design column to test")
    parser.add_argument("--donor", default=None, help="Donor / blocking factor column for paired multi-donor designs")
    parser.add_argument("--reference", default=None)
    parser.add_argument("--contrast-level", default=None)
    parser.add_argument("-o", "--output", required=True, help="DE results CSV")
    parser.add_argument("--skip-doctor", action="store_true")
    args = parser.parse_args()
    from bionexus.gate import require_doctor

    require_doctor(skip=args.skip_doctor)
    counts = _read_table(Path(args.counts))
    design = _read_table(Path(args.design))
    table, contract = run_pydeseq2(
        counts,
        design,
        condition=args.condition,
        donor=args.donor,
        reference=args.reference,
        contrast_level=args.contrast_level,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out, index=False)
    print(json.dumps(contract, indent=2, default=str))


if __name__ == "__main__":
    main()
