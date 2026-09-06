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
