"""Unit tests for BioNexus Laboratory Instrument Ingestion Gateway (BNS-INST-001)."""

from pathlib import Path
from bionexus.instrument_gateway import (
    InstrumentType,
    LaboratoryInstrumentGateway,
)


def test_detect_instrument_type(tmp_path):
    gw = LaboratoryInstrumentGateway()
    
    f_ngs = tmp_path / "RunInfo.xml"
    f_ngs.write_text("<Run><Flowcell>ABC</Flowcell></Run>", encoding="utf-8")
    itype, vendor = gw.detect_instrument_type(f_ngs)
    assert itype == InstrumentType.NGS_SEQUENCER
    assert "Illumina" in vendor

    f_sc = tmp_path / "metrics_summary.csv"
    f_sc.write_text("Estimated Number of Cells,Mean Reads per Cell\n3000,50000\n", encoding="utf-8")
    itype, vendor = gw.detect_instrument_type(f_sc)
    assert itype == InstrumentType.SINGLE_CELL_CONTROLLER

    f_plt = tmp_path / "biotek_plate_01.csv"
    f_plt.write_text("BioTek Gen5 Output\nWell,Value\nA1,100\nA2,200\n", encoding="utf-8")
    itype, vendor = gw.detect_instrument_type(f_plt)
    assert itype == InstrumentType.PLATE_READER


def test_ingest_plate_reader(tmp_path):
    gw = LaboratoryInstrumentGateway()
    csv_file = tmp_path / "plate_reader.csv"
    csv_file.write_text("Well,RFU\nA1,1200\nA2,1350\nA3,1100\n", encoding="utf-8")

    out_json = tmp_path / "asm_output.json"
    res = gw.ingest_plate_reader(csv_file, output_json_path=out_json)

    assert res.success is True
    assert res.records_ingested == 3
    assert res.summary_metrics["well_count"] == 3
    assert res.summary_metrics["mean_intensity"] > 1000
    assert out_json.is_file()
    assert res.receipt["execution_status"] == "SUCCESS"
    assert res.receipt["tool_name"] == "instrument.ingest_plate_reader"


def test_ingest_single_cell_metrics(tmp_path):
    gw = LaboratoryInstrumentGateway()
    csv_file = tmp_path / "metrics_summary.csv"
    csv_file.write_text("Estimated Number of Cells,Mean Reads per Cell\n3500,45000\n", encoding="utf-8")

    res = gw.ingest_single_cell_metrics(csv_file)
    assert res.success is True
    assert res.instrument_type == InstrumentType.SINGLE_CELL_CONTROLLER.value
    assert res.summary_metrics["Estimated Number of Cells"] == 3500
    assert res.receipt["execution_status"] == "SUCCESS"
