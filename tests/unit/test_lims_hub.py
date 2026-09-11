"""Unit tests for BioNexus LIMS Connectivity Hub (BNS-LIMS-001)."""

import pytest

from bionexus.lims_hub import (
    FIRST_ROUND_PILOT_INCLUDED,
    PILOT_EXCLUSION_REASON,
    BenchlingConnector,
    C04PairingCustodianHub,
    GenericRestLIMSConnector,
    LIMSConnectionConfig,
    LIMSConnectorType,
)


def test_benchling_export_assay():
    config = LIMSConnectionConfig(
        connector_type=LIMSConnectorType.BENCHLING,
        base_url="https://api.benchling.com/v2",
        auth_token="test_token_123",
        project_id="prj_oncology_01",
    )
    assert config.get_sanitized_config()["auth_token"] == "REDACTED"

    connector = BenchlingConnector(config)
    measurements = [
        {"well": "A1", "value": 1520.5, "unit": "RFU", "sample_id": "SMP-A1"},
        {"well": "A2", "value": 1490.2, "unit": "RFU", "sample_id": "SMP-A2"},
    ]
    res = connector.export_assay_results(
        schema_id="sch_plate_fluorescence",
        plate_id="PLT-20260829-001",
        measurements=measurements,
        mock_response=True,
    )
    assert res.success is True
    assert res.records_synced == 2
    assert res.target_entity_id == "PLT-20260829-001"
    assert res.receipt["tool_name"] == "lims.benchling_export_assay"
    assert res.receipt["execution_status"] == "SUCCESS"
    assert "receipt_hash" in res.receipt
    assert res.metadata["first_round_pilot_included"] is False
    assert FIRST_ROUND_PILOT_INCLUDED is False


def test_benchling_post_evidence_card():
    config = LIMSConnectionConfig(connector_type=LIMSConnectorType.BENCHLING)
    connector = BenchlingConnector(config)
    card = {"claim_id": "CLM-001", "warrant_tier": "SUPPORTED", "p_val": 0.001}
    res = connector.post_evidence_card_to_notebook(
        entry_id="ent_2026_08_001",
        title="TP53 Validation Card",
        evidence_card=card,
        mock_response=True,
    )
    assert res.success is True
    assert res.records_synced == 1
    assert res.receipt["execution_status"] == "SUCCESS"


def test_generic_lims_sync():
    config = LIMSConnectionConfig(
        connector_type=LIMSConnectorType.LABWARE,
        base_url="https://labware.internal/api/v1",
    )
    connector = GenericRestLIMSConnector(config)
    samples = [{"sample_id": "S1"}, {"sample_id": "S2"}, {"sample_id": "S3"}]
    res = connector.sync_samples(samples, mock_response=True)
    assert res.success is True
    assert res.records_synced == 3
    assert res.receipt["execution_status"] == "SUCCESS"


def test_c04_pairing_hub(tmp_path):
    hub = C04PairingCustodianHub()
    res = hub.audit_manifest(tmp_path / "non_existent.csv")
    assert res["status"] == "ABSTAIN"
    assert res["passed"] is False
    assert "Missing manifest" in res["issues"][0]


def test_benchling_live_missing_token_fails_closed():
    config = LIMSConnectionConfig(
        connector_type=LIMSConnectorType.BENCHLING,
        base_url="https://api.benchling.com/v2",
        auth_token=None,
    )
    connector = BenchlingConnector(config)
    res = connector.export_assay_results(
        schema_id="sch_1",
        plate_id="PLT-001",
        measurements=[{"well": "A1", "value": 10.0, "unit": "RFU", "sample_id": "SMP-A1"}],
        mock_response=False,
    )
    assert res.success is False
    assert res.records_synced == 0
    assert PILOT_EXCLUSION_REASON in res.errors[0]
    assert res.receipt["execution_status"] == "ERROR"


def test_benchling_live_http_dispatch(monkeypatch):
    config = LIMSConnectionConfig(
        connector_type=LIMSConnectorType.BENCHLING,
        base_url="https://api.benchling.com/v2",
        auth_token="valid_secret_key",
    )
    connector = BenchlingConnector(config)

    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json_data = json_data
            self.text = str(json_data)

        def json(self):
            return self._json_data

    called = {"n": 0}

    def _post(*args, **kwargs):
        called["n"] += 1
        return MockResponse(201, {"status": "CREATED", "id": "asyr_123"})

    monkeypatch.setattr("requests.post", _post)
    res = connector.export_assay_results(
        schema_id="sch_1",
        plate_id="PLT-001",
        measurements=[{"well": "A1", "value": 10.0, "unit": "RFU", "sample_id": "SMP-A1"}],
        mock_response=False,
    )
    assert res.success is False
    assert called["n"] == 0
    assert PILOT_EXCLUSION_REASON in res.errors[0]
    assert res.metadata["first_round_pilot_included"] is False


def test_generic_lims_live_dispatch(monkeypatch):
    config = LIMSConnectionConfig(
        connector_type=LIMSConnectorType.LABWARE,
        base_url="https://labware.internal/api/v1",
        auth_token="token_xyz",
    )
    connector = GenericRestLIMSConnector(config)

    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json_data = json_data
            self.text = str(json_data)

        def json(self):
            return self._json_data

    monkeypatch.setattr(
        "requests.post",
        lambda url, json, headers, timeout, verify: MockResponse(200, {"processed": 2}),
    )
    called = {"n": 0}

    def _post(*args, **kwargs):
        called["n"] += 1
        return MockResponse(200, {"processed": 2})

    monkeypatch.setattr("requests.post", _post)
    res = connector.sync_samples([{"sample_id": "S1"}, {"sample_id": "S2"}], mock_response=False)
    assert res.success is False
    assert called["n"] == 0
    assert PILOT_EXCLUSION_REASON in res.errors[0]


def test_empty_measurement_is_not_auto_filled():
    config = LIMSConnectionConfig(
        connector_type=LIMSConnectorType.BENCHLING,
        project_id="prj_oncology_01",
    )
    connector = BenchlingConnector(config)
    with pytest.raises(ValueError, match="missing required fields"):
        connector.format_assay_payload("schema-test", "plate-test", [{}])

    res = connector.export_assay_results(
        schema_id="schema-test",
        plate_id="plate-test",
        measurements=[{}],
        mock_response=True,
    )
    assert res.success is False
    assert res.records_synced == 0
    assert "auto-filled" in res.errors[0] or "missing required fields" in res.errors[0]


def test_missing_project_id_is_not_defaulted():
    config = LIMSConnectionConfig(connector_type=LIMSConnectorType.BENCHLING)
    connector = BenchlingConnector(config)
    with pytest.raises(ValueError, match="project_id is required"):
        connector.format_assay_payload(
            "schema-test",
            "plate-test",
            [{"well": "A1", "value": 1.0, "unit": "RFU", "sample_id": "SMP-A1"}],
        )


def test_allotrope_asm_lims_bridge_transform():
    from bionexus.lims_hub import AllotropeASMLIMSBridge

    asm_doc = {
        "$asm.manifest": "http://purl.allotrope.org/manifests/plate-reader/REC/2024/06/plate-reader.manifest",
        "measurement_aggregate_document": {
            "measurement_document": [
                {
                    "location_identifier": "A1",
                    "measurement_time": "2026-09-11T12:00:00Z",
                    "fluorescence": 1250.5,
                    "unit": "RFU",
                    "sample_identifier": "SMP-TEST-01",
                },
                {
                    "location_identifier": "A2",
                    "measurement_time": "2026-09-11T12:00:00Z",
                    "fluorescence": 980.2,
                    "unit": "RFU",
                    "sample_identifier": "SMP-TEST-02",
                },
            ],
            "plate_well_count": 2,
        },
    }

    bridge = AllotropeASMLIMSBridge()
    measurements = bridge.parse_asm_to_measurements(asm_doc)
    assert len(measurements) == 2
    assert measurements[0]["well"] == "A1"
    assert measurements[0]["value"] == 1250.5
    assert measurements[0]["unit"] == "RFU"
    assert measurements[0]["sample_id"] == "SMP-TEST-01"

    benchling_payload = bridge.transform_for_lims(
        asm_document=asm_doc,
        target_system=LIMSConnectorType.BENCHLING,
        schema_id="sch_plate_fluorescence",
        plate_id="PLT-2026-001",
        project_id="prj_screen",
    )
    assert benchling_payload["schemaId"] == "sch_plate_fluorescence"
    assert benchling_payload["plateId"] == "PLT-2026-001"
    assert len(benchling_payload["results"]) == 2

    labware_payload = bridge.transform_for_lims(
        asm_document=asm_doc,
        target_system=LIMSConnectorType.LABWARE,
        schema_id="sch_labware_01",
        plate_id="PLT-2026-001",
    )
    assert labware_payload["target_system"] == "LABWARE"
    assert labware_payload["records_count"] == 2


def test_allotrope_asm_fails_closed_on_missing_measurements():
    from bionexus.lims_hub import AllotropeASMLIMSBridge

    bridge = AllotropeASMLIMSBridge()

    # Empty document
    with pytest.raises(ValueError, match="No measurement documents found"):
        bridge.parse_asm_to_measurements({})

    # Measurement missing numerical value
    bad_doc = {
        "measurement_aggregate_document": {
            "measurement_document": [{"location_identifier": "A1", "unit": "RFU"}]
        }
    }
    with pytest.raises(ValueError, match="missing numerical measurement value"):
        bridge.parse_asm_to_measurements(bad_doc)

    # Measurement missing location/well
    bad_doc_no_well = {
        "measurement_aggregate_document": {
            "measurement_document": [{"fluorescence": 100.0, "unit": "RFU"}]
        }
    }
    with pytest.raises(ValueError, match="missing location_identifier"):
        bridge.parse_asm_to_measurements(bad_doc_no_well)


def test_egress_controlled_lims_client_ssrf_guards():
    from bionexus.lims_hub import EgressControlledLIMSClient

    client = EgressControlledLIMSClient()

    # AWS/GCP/Azure link-local metadata addresses MUST be blocked
    res_metadata = client.dispatch(
        url="http://169.254.169.254/latest/meta-data",
        payload={"leak": "token"},
    )
    assert res_metadata["success"] is False
    assert res_metadata["status"] == "EGRESS_BLOCKED"
    assert "SSRF Guard" in res_metadata["error"]
    assert res_metadata["receipt"]["tool_name"] == "lims.egress_dispatch"
    assert res_metadata["receipt"]["execution_status"] == "ERROR"

    # Cloud internal metadata domain MUST be blocked
    res_gcp = client.dispatch(
        url="http://metadata.google.internal/computeMetadata/v1/",
        payload={},
    )
    assert res_gcp["success"] is False
    assert "SSRF Guard" in res_gcp["error"]

    # Non-whitelisted external domain MUST be blocked
    res_evil = client.dispatch(
        url="https://evil-unauthorized-target.org/api",
        payload={},
    )
    assert res_evil["success"] is False
    assert "not in the configured LIMS egress allowlist" in res_evil["error"]

    # Whitelisted domain mock dispatch succeeds with receipt
    res_benchling = client.dispatch(
        url="https://api.benchling.com/v2/assay-results",
        payload={"schemaId": "sch_1"},
        mock_response=True,
    )
    assert res_benchling["success"] is True
    assert res_benchling["status"] == "MOCK_SUCCESS"
    assert res_benchling["receipt"]["execution_status"] == "SUCCESS"


def test_allotrope_asm_export_to_lims_mock():
    from bionexus.lims_hub import AllotropeASMLIMSBridge

    asm_doc = {
        "measurement_aggregate_document": {
            "measurement_document": [
                {"location_identifier": "B1", "absorbance": 0.452, "unit": "OD600", "sample_identifier": "SMP-B1"}
            ]
        }
    }

    bridge = AllotropeASMLIMSBridge()
    res = bridge.export_asm_to_lims(
        asm_document=asm_doc,
        endpoint_url="https://api.benchling.com/v2/assay-results",
        target_system=LIMSConnectorType.BENCHLING,
        schema_id="sch_od600",
        plate_id="PLT-ABS-01",
        project_id="prj_growth",
        mock_response=True,
    )

    assert res.success is True
    assert res.records_synced == 1
    assert res.target_entity_id == "PLT-ABS-01"
    assert res.receipt["tool_name"] == "lims.allotrope_bridge_export"
    assert res.receipt["execution_status"] == "SUCCESS"


def test_lims_cli_export_asm(tmp_path, capsys):
    import json

    from bionexus.cli import main as cli_main

    asm_file = tmp_path / "tecan_plate.json"
    asm_doc = {
        "measurement_aggregate_document": {
            "measurement_document": [
                {"location_identifier": "C1", "fluorescence": 3400.0, "unit": "RFU", "sample_identifier": "SMP-C1"}
            ]
        }
    }
    asm_file.write_text(json.dumps(asm_doc), encoding="utf-8")

    ret = cli_main([
        "lims",
        "export-asm",
        "--asm",
        str(asm_file),
        "--endpoint",
        "https://api.benchling.com/v2/assay-results",
        "--target",
        "BENCHLING",
        "--plate-id",
        "PLT-CLI-01",
        "--project-id",
        "prj_cli",
        "--mock",
        "--json",
    ])
    assert ret == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["success"] is True
    assert data["records_synced"] == 1
    assert data["target_entity_id"] == "PLT-CLI-01"

