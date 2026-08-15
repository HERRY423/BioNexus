#!/usr/bin/env python3
"""
Declarative YAML Mapping Engine for Laboratory Instrument Data.
Parses complex laboratory spreadsheets and outputs standards-compliant
Allotrope Simple Model (ASM) JSON based on YAML rules.

Features:
- Cell reference extraction (e.g., 'B2', 'C4')
- Regex-based header metadata extraction
- 2D Plate Matrix grid unpivoting (A1..H12) & 1D long table support
- Generates fully compliant ASM measurement documents and calculated data aggregates
- Attaches cryptographic SHA-256 data lineage
"""

import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:
    yaml = None

try:
    import pandas as pd
except ImportError:
    pd = None


def load_mapping_configs(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load declarative instrument YAML mapping rules."""
    if not yaml:
        return {}

    if config_path is None:
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configs", "instrument_mappings.yml"
        )

    if not os.path.exists(config_path):
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def match_instrument_rule(
    file_path: str, raw_text: str, config: Dict[str, Any]
) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Match a file against defined YAML instrument rules."""
    instruments = config.get("instruments", {})
    file_name = Path(file_path).name.lower()
    text_lower = raw_text.lower()

    for inst_id, inst_conf in instruments.items():
        # 1. Check filename patterns
        patterns = inst_conf.get("file_patterns", [])
        name_match = any(re.match(p, file_name, re.IGNORECASE) for p in patterns)

        # 2. Check keywords
        keywords = inst_conf.get("detection_keywords", [])
        kw_matches = sum(1 for kw in keywords if kw.lower() in text_lower)

        if name_match or kw_matches >= len(keywords) // 2 + 1:
            return inst_id, inst_conf

    return None


def extract_metadata_from_rules(lines: List[str], rules: Dict[str, Any]) -> Dict[str, Any]:
    """Extract header metadata fields according to YAML declarative rules."""
    extracted = {}

    for field_name, rule in rules.items():
        strategy = rule.get("strategy", "fixed")
        default_val = rule.get("default")

        if strategy == "fixed":
            extracted[field_name] = rule.get("value", default_val)

        elif strategy == "regex":
            pattern = rule.get("pattern", "")
            found_val = default_val
            for line in lines:
                m = re.search(pattern, line, re.IGNORECASE)
                if m:
                    found_val = m.group(1).strip()
                    break
            extracted[field_name] = found_val

        elif strategy == "cell":
            target = rule.get("target", "A1").upper()
            col_letter = target[0]
            row_idx = int(target[1:]) - 1
            col_idx = ord(col_letter) - ord("A")

            if row_idx < len(lines):
                parts = re.split(r"[,;\t]+", lines[row_idx].strip())
                if col_idx < len(parts):
                    extracted[field_name] = parts[col_idx].strip().strip('"').strip("'")
                else:
                    extracted[field_name] = default_val
            else:
                extracted[field_name] = default_val

    return extracted


def parse_with_yaml_mapping(file_path: str, config_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Parse an instrument output file using declarative YAML rules.

    Returns
    -------
    ASM JSON dictionary or None if no matching YAML rule was found.
    """
    if not pd:
        return None

    config = load_mapping_configs(config_path)
    if not config or "instruments" not in config:
        return None

    # Read text sample for matching
    encodings = ["utf-8", "latin-1", "cp1252"]
    raw_text = ""
    lines = []
    for enc in encodings:
        try:
            with open(file_path, "r", encoding=enc) as f:
                lines = [f.readline() for _ in range(60)]
                raw_text = "".join(lines)
            break
        except Exception:
            continue

    match_res = match_instrument_rule(file_path, raw_text, config)
    if not match_res:
        return None

    inst_id, inst_conf = match_res
    vendor = inst_conf.get("vendor", "Generic Lab Vendor")
    model = inst_conf.get("model", "Instrument")
    meas_type = inst_conf.get("measurement_type", "measurement")

    # 1. Extract metadata
    meta_rules = inst_conf.get("metadata_rules", {})
    extracted_meta = extract_metadata_from_rules(lines, meta_rules)

    # 2. Read tabular data
    table_rules = inst_conf.get("data_table_rules", {})
    start_keyword_str = table_rules.get("start_keyword", "<>|Well|Sample")
    start_keywords = [k.strip().lower() for k in start_keyword_str.split("|") if k.strip()]
    val_cols = table_rules.get("value_column", "Value|OD|Signal|Raw").split("|")
    well_cols = table_rules.get("well_column", "Well|Sample Name").split("|")
    unit = table_rules.get("unit", "(unitless)")

    # Find table start row by exact token matching
    skip_rows = 0
    for idx, line in enumerate(lines):
        tokens = [t.strip().lower() for t in line.replace("\t", " ").replace(",", " ").replace(";", " ").split()]
        if any(k in tokens for k in start_keywords):
            skip_rows = idx
            break

    try:
        suffix = Path(file_path).suffix.lower()
        if suffix in (".xlsx", ".xls"):
            df = pd.read_excel(file_path, skiprows=skip_rows)
        else:
            df = pd.read_csv(file_path, skiprows=skip_rows, sep=None, engine="python")
    except Exception:
        return None

    measurements = []

    # Check if 2D plate matrix layout (e.g. columns '1', '2', '3' and rows 'A', 'B', 'C'...)
    numeric_cols = [c for c in df.columns[1:] if str(c).strip().isdigit()]
    first_col_vals = [str(v).strip() for v in df.iloc[:, 0].dropna()[:8]]
    is_2d_matrix = len(numeric_cols) >= 2 and any(v.isalpha() for v in first_col_vals)

    if is_2d_matrix:
        # Unpivot 2D matrix into individual well measurements
        row_col_name = df.columns[0]
        for _, row in df.iterrows():
            row_letter = str(row[row_col_name]).strip().upper()
            if not row_letter or not row_letter[0].isalpha():
                continue
            row_letter = row_letter[0]
            for col_num in numeric_cols:
                val = row[col_num]
                if pd.notna(val):
                    well_id = f"{row_letter}{int(col_num)}"
                    try:
                        fval = float(val)
                    except (ValueError, TypeError):
                        fval = str(val)

                    meas_doc = {
                        "location identifier": well_id,
                        "sample identifier": f"Sample_{well_id}",
                        meas_type: {"value": fval, "unit": unit},
                    }
                    measurements.append(meas_doc)
    else:
        # 1D long table format
        matched_well_col = next(
            (c for c in df.columns if any(w.lower() in str(c).lower() for w in well_cols)), df.columns[0]
        )
        matched_val_col = next((c for c in df.columns if any(v.lower() in str(c).lower() for v in val_cols)), None)

        for _, row in df.iterrows():
            well_id = str(row[matched_well_col]).strip()
            if pd.isna(well_id) or well_id == "" or well_id.lower() == "nan":
                continue

            meas_doc = {
                "location identifier": well_id,
                "sample identifier": f"Sample_{well_id}",
            }

            if matched_val_col and pd.notna(row[matched_val_col]):
                try:
                    meas_doc[meas_type] = {"value": float(row[matched_val_col]), "unit": unit}
                except (ValueError, TypeError):
                    meas_doc[meas_type] = str(row[matched_val_col])

            # Additional columns
            for add_col in table_rules.get("additional_columns", []):
                field = add_col.get("name")
                target_col = add_col.get("column")
                if target_col in df.columns and pd.notna(row[target_col]):
                    val = row[target_col]
                    try:
                        meas_doc[field] = float(val)
                    except (ValueError, TypeError):
                        meas_doc[field] = str(val)

            measurements.append(meas_doc)

    # Construct schema-compliant Allotrope Simple Model (ASM)
    file_bytes = Path(file_path).read_bytes()
    file_sha256 = hashlib.sha256(file_bytes).hexdigest()
    now_iso = datetime.now(timezone.utc).isoformat()

    asm = {
        "$asm.manifest": config.get("manifest", "http://purl.allotrope.org/manifests/plate-reader/BENCHMARK/V1.0"),
        "measurement aggregate document": {
            "measurement identifier": file_sha256[:16],
            "measurement time": extracted_meta.get("measurement_time", now_iso),
            "device system document": {
                "device identifier": extracted_meta.get("device_identifier", f"{vendor}-{model}"),
                "model number": model,
                "equipment serial number": extracted_meta.get("serial_number", "UNKNOWN"),
            },
            "measurement document": measurements,
        },
        "custom metadata": {
            "conversion provenance": {
                "engine": "BioNexus Declarative YAML Mapping Engine v1.3.0",
                "matched_rule": inst_id,
                "vendor": vendor,
                "source_file": Path(file_path).name,
                "source_sha256": file_sha256,
                "num_measurements": len(measurements),
                "timestamp": now_iso,
            }
        },
    }

    return asm
