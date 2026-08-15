#!/usr/bin/env python3
"""
Instrument Data to ASM Converter (High-Performance Parallel Batch Edition)

Converts laboratory instrument output files to Allotrope Simple Model (ASM) JSON format.
Supports auto-detection of instrument types, flexible fallback parsing, and multi-core
parallel batch processing for high-throughput laboratory datasets.

Usage:
    # Single file conversion
    python convert_to_asm.py <input_file> [--vendor VENDOR] [--output OUTPUT] [--flatten]

    # High-throughput batch conversion across multiple CPU cores
    python convert_to_asm.py --batch-dir /path/to/plates/ --workers 8 --flatten
"""

import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Lazy imports to avoid errors if not installed
def get_allotropy():
    try:
        from allotropy.parser_factory import Vendor
        from allotropy.to_allotrope import allotrope_from_file, allotrope_from_io

        return Vendor, allotrope_from_file, allotrope_from_io
    except ImportError:
        return None, None, None


def get_pandas():
    try:
        import pandas as pd

        return pd
    except ImportError:
        return None


def get_polars():
    try:
        import polars as pl

        return pl
    except ImportError:
        return None


# Detection patterns for instrument identification
DETECTION_PATTERNS = {
    # ---- Cell Counting ----
    "BECKMAN_VI_CELL_BLU": {
        "columns": [
            "Sample ID",
            "Viable cells",
            "Viability",
            "Total cells",
            "Average diameter",
        ],
        "keywords": ["Vi-CELL BLU", "Beckman Coulter"],
        "file_patterns": [r".*\.csv$"],
        "confidence_boost": 20,
    },
    "BECKMAN_VI_CELL_XR": {
        "columns": ["Sample", "Total cells/ml", "Viable cells/ml", "Viability (%)"],
        "keywords": ["Vi-CELL XR", "Cell Viability Analyzer"],
        "file_patterns": [r".*\.(txt|xls|xlsx)$"],
        "confidence_boost": 20,
    },
    "CHEMOMETEC_NUCLEOVIEW": {
        "columns": ["Sample ID", "Total cells/ml", "Viability (%)", "Live cells/ml"],
        "keywords": ["NucleoView", "NC-200", "ChemoMetec"],
        "file_patterns": [r".*\.xlsx$"],
        "confidence_boost": 15,
    },
    "REVVITY_MATRIX": {
        "columns": ["Sample", "Cell Count", "Viability", "Diameter"],
        "keywords": ["Revvity", "Matrix", "Cell Counting"],
        "file_patterns": [r".*\.csv$"],
        "confidence_boost": 10,
    },
    # ---- Spectrophotometry ----
    "THERMO_FISHER_NANODROP_EIGHT": {
        "columns": ["Sample Name", "Nucleic Acid Conc.", "A260", "A280", "260/280"],
        "keywords": ["NanoDrop Eight", "NanoDrop 8"],
        "file_patterns": [r".*\.(tsv|txt)$"],
        "confidence_boost": 15,
    },
    "THERMO_FISHER_NANODROP_ONE": {
        "columns": ["Sample Name", "Nucleic Acid(ng/uL)", "A260", "A280"],
        "keywords": ["NanoDrop One", "NanoDrop"],
        "file_patterns": [r".*\.(csv|xlsx)$"],
        "confidence_boost": 15,
    },
    "THERMO_FISHER_NANODROP_8000": {
        "columns": ["Sample Name", "Nucleic Acid Conc.", "A260", "A280", "260/280", "260/230"],
        "keywords": ["NanoDrop 8000", "ND-8000"],
        "file_patterns": [r".*\.csv$"],
        "confidence_boost": 15,
    },
    "UNCHAINED_LABS_LUNATIC": {
        "columns": ["Sample", "Concentration", "A260", "A280"],
        "keywords": ["Lunatic", "Unchained Labs"],
        "file_patterns": [r".*\.(csv|xlsx)$"],
        "confidence_boost": 10,
    },
    # ---- Plate Readers ----
    "AGILENT_GEN5": {
        "columns": ["Well", "Absorbance", "Wavelength", "Read"],
        "keywords": ["Gen5", "BioTek", "Synergy"],
        "file_patterns": [r".*\.(xlsx|txt)$"],
        "confidence_boost": 15,
    },
    "BMG_MARS": {
        "columns": ["Well", "Content", "Raw Data", "Signal"],
        "keywords": ["MARS", "BMG LABTECH", "CLARIOstar", "PHERAstar"],
        "file_patterns": [r".*\.csv$"],
        "confidence_boost": 15,
    },
    "MOLECULAR_DEVICES_SOFTMAX_PRO": {
        "columns": ["Well", "Sample", "Abs", "OD", "Wavelength"],
        "keywords": ["SoftMax Pro", "SpectraMax", "Molecular Devices"],
        "file_patterns": [r".*\.(txt|xlsx)$"],
        "confidence_boost": 15,
    },
    "PERKIN_ELMER_ENVISION": {
        "columns": ["Plate", "Well", "MeasA", "MeasB", "Repeats"],
        "keywords": ["EnVision", "PerkinElmer", "Revvity"],
        "file_patterns": [r".*\.csv$"],
        "confidence_boost": 15,
    },
    "THERMO_FISHER_SKANIT": {
        "columns": ["Well", "Result", "Concentration", "A450"],
        "keywords": ["SkanIt", "Varioskan", "Multiskan"],
        "file_patterns": [r".*\.(xlsx|txt)$"],
        "confidence_boost": 15,
    },
    "TECAN_MAGELLAN": {
        "columns": ["Well", "Pos", "Raw", "OD"],
        "keywords": ["Magellan", "Sunrise", "Infinite", "Tecan"],
        "file_patterns": [r".*\.xlsx$"],
        "confidence_boost": 15,
    },
    # ---- qPCR ----
    "APPLIED_BIOSYSTEMS_7500": {
        "columns": ["Well", "Sample Name", "Target Name", "CT", "Ct", "C_T", "Tm"],
        "keywords": ["7500", "Applied Biosystems", "QuantStudio"],
        "file_patterns": [r".*\.(csv|txt|xlsx)$"],
        "confidence_boost": 15,
    },
    "APPLIED_BIOSYSTEMS_DESIGN_ANALYSIS": {
        "columns": ["Well", "Sample", "Target", "Cq", "Cq Conf"],
        "keywords": ["Design and Analysis", "QuantStudio 6", "QuantStudio 7"],
        "file_patterns": [r".*\.xlsx$"],
        "confidence_boost": 15,
    },
    "BIO_RAD_CFX_MAESTRO": {
        "columns": ["Well", "Fluor", "Target", "Cq", "SQ"],
        "keywords": ["CFX Maestro", "Bio-Rad", "CFX96", "CFX384"],
        "file_patterns": [r".*\.csv$"],
        "confidence_boost": 15,
    },
    "ROCHE_LIGHTCYCLER": {
        "columns": ["Pos", "Name", "Cp", "Concentration", "Standard"],
        "keywords": ["LightCycler", "Roche", "LC480"],
        "file_patterns": [r".*\.txt$"],
        "confidence_boost": 15,
    },
    # ---- ELISA / Immunoassay ----
    "MESO_SCALE_DISCOVERY_WORKBENCH": {
        "columns": ["Well", "Spot", "Assay", "Signal", "Calc. Concentration"],
        "keywords": ["DISCOVERY WORKBENCH", "MSD", "Meso Scale"],
        "file_patterns": [r".*\.txt$"],
        "confidence_boost": 15,
    },
    # ---- Electrophoresis ----
    "AGILENT_TAPESTATION": {
        "columns": ["Sample", "Well", "Size [bp]", "Conc. [ng/ul]", "RINe", "DIN"],
        "keywords": ["TapeStation", "ScreenTape", "Agilent Technologies"],
        "file_patterns": [r".*\.csv$"],
        "confidence_boost": 15,
    },
    "PERKIN_ELMER_LABCHIP": {
        "columns": ["Well", "Sample Name", "Size", "Conc (ng/ul)", "Molarity"],
        "keywords": ["LabChip", "GX Touch", "PerkinElmer"],
        "file_patterns": [r".*\.csv$"],
        "confidence_boost": 15,
    },
    # ---- Chromatography & Mass Spec ----
    "WATERS_EMPOWER": {
        "columns": ["Sample Name", "Vial", "Injection", "Peak Name", "RT", "Area", "Height", "% Area"],
        "keywords": ["Empower", "Waters", "ACQUITY"],
        "file_patterns": [r".*\.(txt|csv)$"],
        "confidence_boost": 15,
    },
    "THERMO_FISHER_CHROMELEON": {
        "columns": ["No.", "Peak Name", "Ret.Time", "Area", "Height", "Amount"],
        "keywords": ["Chromeleon", "Dionex", "Thermo Scientific"],
        "file_patterns": [r".*\.(txt|csv)$"],
        "confidence_boost": 15,
    },
    "AGILENT_CHEMSTATION": {
        "columns": ["Peak #", "RetTime", "Type", "Width", "Area", "Height", "Area %"],
        "keywords": ["ChemStation", "OpenLab", "Agilent Technologies"],
        "file_patterns": [r".*\.txt$"],
        "confidence_boost": 15,
    },
    # ---- Flow Cytometry ----
    "BD_FACSDIVA": {
        "columns": ["Tube", "Population", "#Events", "%Parent", "%Total", "Mean", "Median"],
        "keywords": ["FACSDiva", "BD Biosciences", "LSRFortessa", "FACSCanto"],
        "file_patterns": [r".*\.(csv|txt)$"],
        "confidence_boost": 15,
    },
}


def read_file_sample(file_path: str, max_lines: int = 50) -> Tuple[str, List[str]]:
    """Read a sample of text from file for header detection."""
    content = ""
    lines = []
    encodings = ["utf-8", "latin-1", "cp1252", "iso-8859-1"]

    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                for i, line in enumerate(f):
                    if i >= max_lines:
                        break
                    lines.append(line)
                    content += line
            return content, lines
        except (UnicodeDecodeError, Exception):
            continue

    return "", []


def detect_instrument_type(file_path: str) -> Tuple[str, int]:
    """Auto-detect instrument vendor from file contents and headers."""
    content, lines = read_file_sample(file_path)
    file_name = Path(file_path).name

    scores: Dict[str, int] = {}

    for vendor, pattern in DETECTION_PATTERNS.items():
        score = 0

        # Check file pattern
        file_match = any(re.match(fp, file_name, re.IGNORECASE) for fp in pattern.get("file_patterns", []))
        if file_match:
            score += 10

        # Check column matches
        col_matches = sum(1 for col in pattern.get("columns", []) if col.lower() in content.lower())
        score += col_matches * 15

        # Check keyword matches
        kw_matches = sum(1 for kw in pattern.get("keywords", []) if kw.lower() in content.lower())
        score += kw_matches * pattern.get("confidence_boost", 15)

        scores[vendor] = score

    if not scores:
        return "UNKNOWN", 0

    best_vendor = max(scores, key=scores.get)
    max_score = scores[best_vendor]
    confidence = min(100, int((max_score / 60) * 100))

    return best_vendor, confidence


def convert_with_allotropy(file_path: str, vendor: str) -> Optional[Dict[str, Any]]:
    """Attempt conversion using native allotropy library."""
    Vendor, allotrope_from_file, _ = get_allotropy()
    if not allotrope_from_file:
        return None

    try:
        vendor_enum = getattr(Vendor, vendor)
    except AttributeError:
        return None

    try:
        asm_dict = allotrope_from_file(file_path, vendor_enum)
        return asm_dict
    except Exception:
        return None


def flexible_parse(file_path: str, vendor_hint: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fallback parser for tabular instrument files."""
    pd = get_pandas()
    if not pd:
        return None

    try:
        suffix = Path(file_path).suffix.lower()
        if suffix in [".xlsx", ".xls"]:
            df = pd.read_excel(file_path)
        elif suffix in [".tsv", ".txt"]:
            df = pd.read_csv(file_path, sep=r"\s+|\t", engine="python")
        else:
            df = pd.read_csv(file_path)
    except Exception:
        return None

    measurements = []
    for _, row in df.iterrows():
        meas: Dict[str, Any] = {}
        for col, val in row.items():
            if pd.notna(val):
                clean_col = str(col).strip()
                if isinstance(val, (int, float)):
                    meas[clean_col] = {"value": float(val), "unit": "(unitless)"}
                else:
                    meas[clean_col] = str(val)
        if meas:
            measurements.append(meas)

    asm = {
        "$asm.manifest": "http://purl.allotrope.org/manifests/measurement/BENCHMARK/V1.0",
        "measurement aggregate document": {
            "measurement identifier": hashlib.sha256(Path(file_path).name.encode()).hexdigest()[:16],
            "measurement time": datetime.utcnow().isoformat() + "Z",
            "measurement document": measurements,
        },
    }
    return asm


def add_provenance_metadata(
    asm: Dict[str, Any], input_file: str, vendor: str, confidence: int, used_fallback: bool, warnings: List[str]
) -> Dict[str, Any]:
    """Attach data lineage and parser execution metadata."""
    if "custom metadata" not in asm:
        asm["custom metadata"] = {}

    asm["custom metadata"]["conversion provenance"] = {
        "source_file": Path(input_file).name,
        "source_file_hash": hashlib.sha256(Path(input_file).read_bytes()).hexdigest(),
        "detected_vendor": vendor,
        "detection_confidence": f"{confidence}%",
        "parser_used": "flexible_fallback" if used_fallback else "allotropy_native",
        "conversion_timestamp": datetime.utcnow().isoformat() + "Z",
        "warnings": warnings,
    }
    return asm


def convert_single_file(
    input_path: Path,
    vendor: Optional[str] = None,
    output_path: Optional[Path] = None,
    flatten: bool = False,
    allow_fallback: bool = True,
    skip_validation: bool = False,
    force: bool = False,
) -> Dict[str, Any]:
    """Worker function to convert a single instrument file."""
    start_time = time.time()
    res = {
        "file": str(input_path),
        "success": False,
        "vendor": "UNKNOWN",
        "confidence": 0,
        "output": "",
        "used_fallback": False,
        "error": None,
        "duration_s": 0.0,
    }

    try:
        warnings = []
        if vendor:
            detected_vendor = vendor.upper()
            confidence = 100
        else:
            detected_vendor, confidence = detect_instrument_type(str(input_path))

        res["vendor"] = detected_vendor
        res["confidence"] = confidence

        if confidence < 30 and not force:
            res["error"] = f"Low detection confidence ({confidence}%)"
            return res

        # Attempt allotropy first
        asm = convert_with_allotropy(str(input_path), detected_vendor)
        used_fallback = False

        # Attempt declarative YAML mapping engine if allotropy returned None
        if asm is None:
            try:
                from yaml_mapping_engine import parse_with_yaml_mapping

                asm = parse_with_yaml_mapping(str(input_path))
                if asm is not None:
                    warnings.append("Parsed via declarative YAML mapping engine")
            except Exception:
                pass

        if asm is None:
            if not allow_fallback:
                res["error"] = "Allotropy parser failed and fallback disallowed"
                return res
            asm = flexible_parse(str(input_path), detected_vendor)
            used_fallback = True
            warnings.append("Used fallback parser")

        if asm is None:
            res["error"] = "Could not parse file structure"
            return res

        res["used_fallback"] = used_fallback
        asm = add_provenance_metadata(asm, str(input_path), detected_vendor, confidence, used_fallback, warnings)

        if output_path is None:
            final_out = input_path.with_suffix(".asm.json")
        else:
            final_out = output_path

        with open(final_out, "w", encoding="utf-8") as f:
            json.dump(asm, f, indent=2, default=str)

        res["output"] = str(final_out)
        res["success"] = True

        if flatten:
            try:
                from flatten_asm import flatten_asm_to_csv

                flat_path = input_path.with_suffix(".flat.csv")
                flatten_asm_to_csv(asm, str(flat_path))
            except Exception:
                pass

    except Exception as e:
        res["error"] = str(e)
    finally:
        res["duration_s"] = round(time.time() - start_time, 3)

    return res


def convert_batch_directory(
    batch_dir: Path, workers: int = 4, pattern: str = "*", flatten: bool = False, allow_fallback: bool = True
) -> List[Dict[str, Any]]:
    """Execute multi-process parallel conversion across a directory of instrument files."""
    valid_exts = {".csv", ".xlsx", ".xls", ".tsv", ".txt", ".pdf"}
    files_to_process = []

    for p in batch_dir.rglob(pattern):
        if (
            p.is_file()
            and p.suffix.lower() in valid_exts
            and not p.name.endswith(".asm.json")
            and not p.name.endswith(".flat.csv")
        ):
            files_to_process.append(p)

    total_files = len(files_to_process)
    print(f"\n[Parallel Batch Engine] Found {total_files} candidate files in {batch_dir}")
    print(f"Allocating {workers} worker processes...")

    if total_files == 0:
        return []

    results = []
    start_batch = time.time()

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(convert_single_file, fp, None, None, flatten, allow_fallback, True, True): fp
            for fp in files_to_process
        }

        for idx, fut in enumerate(as_completed(futures), 1):
            res = fut.result()
            results.append(res)
            status_tag = "[OK]" if res["success"] else "[FAILED]"
            print(
                f"  [{idx}/{total_files}] {status_tag} {Path(res['file']).name} -> {res['vendor']} ({res['duration_s']}s)"
            )

    total_time = round(time.time() - start_batch, 2)
    success_count = sum(1 for r in results if r["success"])

    # Write summary CSV
    summary_path = batch_dir / "batch_conversion_summary.csv"
    try:
        pd = get_pandas()
        if pd:
            df = pd.DataFrame(results)
            df.to_csv(summary_path, index=False)
            print(f"\nBatch summary report written to: {summary_path}")
    except Exception:
        pass

    print("\n" + "=" * 65)
    print(f" Batch Conversion Completed: {success_count}/{total_files} succeeded in {total_time}s")
    print(f" Throughput: {round(total_files / max(0.01, total_time), 1)} files/sec across {workers} cores")
    print("=" * 65)

    return results


def main():
    """Main CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert instrument data to ASM format (High-Performance Parallel Edition)"
    )
    parser.add_argument("input", nargs="?", help="Input file path or directory")
    parser.add_argument("--batch-dir", "-d", help="Directory of instrument files for parallel batch processing")
    parser.add_argument(
        "--workers", "-w", type=int, default=os.cpu_count() or 4, help="Number of parallel worker processes"
    )
    parser.add_argument("--vendor", help="Vendor enum name (auto-detected if omitted)")
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument("--flatten", action="store_true", help="Also generate flattened 2D CSV")
    parser.add_argument("--allow-fallback", action="store_true", default=True, help="Allow flexible parser fallback")
    parser.add_argument("--skip-validation", action="store_true", help="Skip schema validation")
    parser.add_argument("--force", action="store_true", help="Force conversion even on low confidence")

    args = parser.parse_args()

    # Detect batch mode from --batch-dir or if positional input is a directory
    target_dir = None
    if args.batch_dir:
        target_dir = Path(args.batch_dir)
    elif args.input and Path(args.input).is_dir():
        target_dir = Path(args.input)

    if target_dir:
        if not target_dir.exists():
            print(f"Error: Directory not found: {target_dir}", file=sys.stderr)
            sys.exit(1)
        convert_batch_directory(
            target_dir, workers=args.workers, flatten=args.flatten, allow_fallback=args.allow_fallback
        )
        return

    if not args.input:
        parser.print_help()
        sys.exit(1)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    print(f"Processing single file: {input_path}")
    res = convert_single_file(
        input_path,
        vendor=args.vendor,
        output_path=Path(args.output) if args.output else None,
        flatten=args.flatten,
        allow_fallback=args.allow_fallback,
        skip_validation=args.skip_validation,
        force=args.force,
    )

    if res["success"]:
        print(f"Successfully converted -> {res['output']} ({res['vendor']}, {res['duration_s']}s)")
    else:
        print(f"Conversion failed: {res['error']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
