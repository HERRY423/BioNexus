---
name: instrument-data-to-allotrope
description: Convert laboratory instrument output files (PDF, CSV, Excel, TXT) to Allotrope Simple Model (ASM) JSON format or flattened 2D CSV using native allotropy or declarative YAML mapping rules. Use this skill when scientists need to standardize instrument data for LIMS systems, data lakes, or downstream analysis.
---

# Instrument Data to Allotrope Converter

Convert laboratory instrument files into standardized Allotrope Simple Model (ASM) JSON and 2D flattened CSV format for LIMS upload, data lakes, or automated ingestion pipelines.

## Key Features

1. **Auto-Detection**: Recognizes 20+ laboratory instrument types (Tecan, BioTek, Molecular Devices, Beckman, NanoDrop, Bio-Rad, Roche, MSD, etc.)
2. **Declarative YAML Mapping Engine** (`configs/instrument_mappings.yml`): Customize parsing rules for proprietary lab devices using YAML without writing code.
3. **High-Throughput Parallel Batch Processing**: Multi-core process pool executor converts hundreds of plates in seconds with summary metrics.
4. **Calculated Data Traceability**: Standards-compliant `calculated-data-aggregate-document` and cryptographic SHA-256 data lineage.

---

## Quick Start CLI

```bash
# Single file conversion
python scripts/convert_to_asm.py plate_reader_output.xlsx --flatten

# High-throughput batch conversion across all available CPU cores
python scripts/convert_to_asm.py --batch-dir ./raw_plates/ --workers 8 --flatten
```

---

## Custom Instrument Configuration (`configs/instrument_mappings.yml`)

Add custom laboratory instrument mappings declaratively:

```yaml
instruments:
  my_custom_fluorometer:
    vendor: "Custom Vendor"
    model: "FluoroMax-4"
    measurement_type: "fluorescence emission"
    file_patterns:
      - ".*fluoromax.*\\.csv$"
    detection_keywords:
      - "FluoroMax"
      - "Intensity"
    metadata_rules:
      device_identifier:
        strategy: "cell"
        target: "B1"
      excitation_wavelength:
        strategy: "regex"
        pattern: "Ex:\\s*(\\d+)"
        default: 480
    data_table_rules:
      header_row_detection: "auto"
      start_keyword: "Well|Sample"
      well_column: "Well"
      value_column: "Intensity|Counts"
      unit: "RFU"
```
