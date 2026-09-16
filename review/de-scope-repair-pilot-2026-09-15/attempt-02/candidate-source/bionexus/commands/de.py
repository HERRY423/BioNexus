"""De command handlers, extracted without changing command semantics."""


from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bionexus.integrity import audit_expression_matrix


def handle_audit_de(args: argparse.Namespace) -> int:
    """Audit multi-donor single-cell differential expression before lab meetings, submission, or sharing."""
    from bionexus.de_audit import audit_differential_expression

    adata_path = getattr(args, "h5ad", None)
    pos_path = getattr(args, "path", None)
    if pos_path:
        p = Path(pos_path)
        if p.suffix.lower() == ".h5ad":
            adata_path = pos_path
        elif p.suffix.lower() in (".csv", ".tsv", ".txt") and not getattr(args, "de_table", None):
            args.de_table = pos_path
        elif p.suffix.lower() in (".ipynb", ".py", ".r", ".rmd") and not getattr(args, "script", None):
            args.script = pos_path

    de_table = getattr(args, "de_table", None) or getattr(args, "results", None)
    sample_sheet = getattr(args, "sample_sheet", None) or getattr(args, "design", None)
    code_path = getattr(args, "script", None) or getattr(args, "notebook", None)
    execution_record = getattr(args, "execution", None) or getattr(args, "execution_record", None)
    claim_text = getattr(args, "claim", None) or getattr(args, "statement", None)

    donor_col = getattr(args, "donor_col", None)
    condition_col = getattr(args, "condition_col", None)
    cell_type_col = getattr(args, "cell_type_col", None)
    batch_col = getattr(args, "batch_col", None)

    out_path = getattr(args, "out", None) or getattr(args, "output", None)
    as_json = getattr(args, "json", False)

    try:
        from bionexus.de_pilot import demo_inputs, render_review, snapshot_inputs, write_bundle

        bundle = getattr(args, "bundle", None)
        demo = getattr(args, "demo", False)
        supplied_files = {"anndata": adata_path, "de_table": de_table, "sample_sheet": sample_sheet,
                          "analysis_code": code_path, "execution_record": execution_record}
        if bundle and (Path(bundle).exists() or out_path):
            raise ValueError("--bundle requires a new directory and cannot be combined with --out")
        if demo and (any(supplied_files.values()) or claim_text or not bundle):
            raise ValueError("--demo requires --bundle and cannot be mixed with research inputs or a claim")
        if bundle and not demo and not any(supplied_files.values()):
            raise ValueError("Supply at least a DE table, sample sheet, .h5ad or script; use --demo for a teaching example")
        fingerprints = snapshot_inputs(supplied_files) if bundle else {}
        audit_kwargs = dict(
            adata_path=adata_path,
            de_table=de_table,
            sample_metadata=sample_sheet,
            code_path=code_path,
            execution_record=execution_record,
            claim_text=claim_text,
            donor_col=donor_col,
            condition_col=condition_col,
            cell_type_col=cell_type_col,
            batch_col=batch_col,
        )
        if demo:
            audit_kwargs.update(demo_inputs())
        result = audit_differential_expression(**audit_kwargs)
        if bundle:
            if snapshot_inputs(supplied_files) != fingerprints:
                raise ValueError("Input files changed during audit; rerun into a new directory")
            write_bundle(result, bundle, inputs=fingerprints, claim=audit_kwargs.get("claim_text"), synthetic=demo)
    except Exception as e:
        print(f"[ERROR] Differential expression evidence audit failed: {e}", file=sys.stderr)
        return 1

    if as_json:
        print((Path(bundle) / "audit.json").read_text(encoding="utf-8") if bundle
              else json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    elif bundle:
        print(render_review(result.to_dict(), Path(bundle).name, demo, audit_kwargs.get("claim_text")))
        print(f"[OK] Review bundle saved to {Path(bundle) / 'REVIEW.md'}")
    else:
        print(result.summary_text(use_color=True))

    if out_path:
        out_p = Path(out_path)
        if out_p.suffix.lower() == ".json":
            out_p.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            out_p.write_text(result.to_markdown(), encoding="utf-8")
        print(f"[OK] Audit report saved to {out_p}")

    return 0 if result.passed else 1


def handle_audit_de_summary(args: argparse.Namespace) -> int:
    from bionexus.de_pilot import render_summary, summarize_reviews

    try:
        summary = summarize_reviews(args.reviews)
        text = json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) if args.json else render_summary(summary)
        if args.out:
            # Preserve previous pilot observations and summaries.
            with Path(args.out).open("x", encoding="utf-8") as stream:
                stream.write(text + "\n")
        print(text)
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f"[ERROR] Pilot summary could not be produced: {exc}", file=sys.stderr)
        return 1


def handle_audit_de_verify(args: argparse.Namespace) -> int:
    from bionexus.de_bundle import EXIT_CODES, verify_de_bundle

    report = verify_de_bundle(args.bundle, expected_manifest_sha256=args.expected_manifest_sha256)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return EXIT_CODES[report["status"]]


def handle_audit(args: argparse.Namespace) -> int:
    """Audit data semantics OR static scientific analysis flaws (BNS-013)."""
    if getattr(args, "de", False):
        return handle_audit_de(args)

    from bionexus.analysis_audit import audit_analysis, render_analysis_audit

    path = Path(args.path)
    if not path.is_file():
        print(f"[ERROR] Target file not found: {path}", file=sys.stderr)
        return 1

    # Code artifacts (notebooks / scripts) -> static scientific analysis audit
    if path.suffix.lower() in {".ipynb", ".py", ".r", ".rmd", ".qmd", ".jl"}:
        result = audit_analysis(path)
        if getattr(args, "json", False):
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(render_analysis_audit(result))
        return 0 if result.passed else 1

    print(f"=== Auditing Biological Data File: {path} ===")
    if path.suffix == ".h5ad":
        try:
            import anndata as ad

            adata = ad.read_h5ad(path)
            grade, notes, stats = audit_expression_matrix(adata.X, expected_type=args.expected_type)
            print(f" [MATRIX AUDIT] Grade: {grade}")
            for note in notes:
                print(f"  - {note}")
            print(f" [STATS] Shape: {stats.get('shape')} | Min: {stats.get('min')} | Max: {stats.get('max')}")
            return 0 if grade in ("A", "B") else 1
        except ImportError:
            print("[ERROR] anndata package required for .h5ad audit. Install: pip install anndata", file=sys.stderr)
            return 1
    else:
        print(f"[NOTE] Reading text/csv matrix: {path}")
        import numpy as np

        data = np.genfromtxt(path, delimiter=",")
        grade, notes, stats = audit_expression_matrix(data, expected_type=args.expected_type)
        print(f" [MATRIX AUDIT] Grade: {grade}")
        for note in notes:
            print(f"  - {note}")
        return 0 if grade in ("A", "B") else 1


def register_audit_arguments(subparsers: argparse._SubParsersAction) -> None:
    # 5. audit (data files AND notebooks/scripts -> static scientific audit)
    p_audit = subparsers.add_parser(
        "audit",
        help="Audit a notebook/script for scientific flaws, or audit data matrix semantics",
    )
    p_audit.add_argument(
        "path",
        help="Path to notebook (.ipynb), script (.py/.R/.Rmd/.qmd), or data file (.h5ad/csv)",
    )
    p_audit.add_argument("--expected-type", choices=["counts", "normalized"], default="counts")
    p_audit.add_argument("--de", action="store_true", help="Perform comprehensive multi-donor single-cell differential expression audit")
    p_audit.add_argument("--json", action="store_true", help="Output audit result as JSON")


def register_audit_de_arguments(subparsers: argparse._SubParsersAction) -> None:
    # 5.1 audit-de (Multi-donor single-cell DE evidence audit for lab meeting / submission / sharing)
    p_audit_de = subparsers.add_parser(
        "audit-de",
        aliases=["de-audit"],
        help="Evidence audit for multi-donor single-cell differential expression before lab meetings, submission, or sharing",
    )
    p_audit_de.add_argument("path", nargs="?", default=None, help="Path to .h5ad, DE table (.csv), or analysis script")
    p_audit_de.add_argument("--h5ad", "--data", dest="h5ad", default=None, help="Path to AnnData (.h5ad) file")
    p_audit_de.add_argument("--de-table", "--results", dest="de_table", default=None, help="Path to DEG results table (CSV/TSV)")
    p_audit_de.add_argument("--sample-sheet", "--design", dest="sample_sheet", default=None, help="Path to sample/donor metadata CSV/TSV")
    p_audit_de.add_argument("--script", "--notebook", dest="script", default=None, help="Path to analysis script (.py/.R) or notebook (.ipynb)")
    p_audit_de.add_argument("--execution", "--execution-record", dest="execution", default=None, help="Path to execution record JSON or verification bundle")
    p_audit_de.add_argument("--claim", "--statement", dest="claim", default=None, help="Free-text scientific claim statement to verify")
    p_audit_de.add_argument("--donor-col", dest="donor_col", default=None, help="Column name for biological donors (auto-detected if omitted)")
    p_audit_de.add_argument("--condition-col", dest="condition_col", default=None, help="Column name for experimental conditions (auto-detected if omitted)")
    p_audit_de.add_argument("--cell-type-col", dest="cell_type_col", default=None, help="Column name for cell types/clusters (auto-detected if omitted)")
    p_audit_de.add_argument("--batch-col", dest="batch_col", default=None, help="Column name for technical batches (auto-detected if omitted)")
    p_audit_de.add_argument("-o", "--out", "--output", dest="out", default=None, help="Export audit report to Markdown (.md) or JSON (.json)")
    p_audit_de.add_argument("--json", action="store_true", help="Output audit result as JSON")
    p_audit_de.add_argument("--bundle", default=None, help="New directory for concise review, evidence and human pilot observation template")
    p_audit_de.add_argument("--demo", action="store_true", help="Use synthetic teaching inputs with --bundle; excluded from pilot outcomes")

    p_de_summary = subparsers.add_parser("audit-de-summary", help="Summarize human-reported DE pilot observations without certifying benefit")
    p_de_summary.add_argument("reviews", nargs="+", help="Paths to completed or pending bundle review.json files")
    p_de_summary.add_argument("--json", action="store_true", help="Output descriptive observations as JSON")
    p_de_summary.add_argument("-o", "--out", default=None, help="Write a new summary file; existing files are never replaced")

    p_de_verify = subparsers.add_parser("audit-de-verify", help="Read-only DE bundle file verification; never scientific approval")
    p_de_verify.add_argument("bundle", help="Existing DE shadow-review directory")
    p_de_verify.add_argument("--expected-manifest-sha256", default=None, help="Manifest digest retained independently by the caller")
