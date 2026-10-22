"""Check the actual outbound request, even when safe metadata is also supplied."""

import asyncio
import io
import json
import urllib.request

import pytest

from bionexus.egress_guard import (
    DataGovernanceGuard,
    EgressBlockedError,
    guarded_requests_get,
    guarded_urlopen,
)
from bionexus.mcp.client import async_http_request

PUBLIC_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
SENSITIVE_MARKER = "SYNTHETIC_PRIVATE_VALUE_927"


@pytest.fixture
def guard(tmp_path):
    return DataGovernanceGuard(mode="ALLOWLIST", audit_log_path=tmp_path / "egress.jsonl")


@pytest.mark.parametrize("query", [
    "term=patient_id%3DSYNTHETIC_PRIVATE_VALUE_927&term=TP53",
    "term=TP53&term=patient_id%3DSYNTHETIC_PRIVATE_VALUE_927",
])
def test_duplicate_url_query_never_discards_a_sensitive_value(guard, monkeypatch, query):
    def transport(*args, **kwargs):
        pytest.fail("blocked query reached transport")

    monkeypatch.setattr(urllib.request, "urlopen", transport)
    with pytest.raises(EgressBlockedError):
        guarded_urlopen(PUBLIC_URL + "?" + query, guard=guard, payload={"query": "TP53"})
    record = guard.get_audit_trail()[-1]
    assert record.outcome == "BLOCKED"
    assert SENSITIVE_MARKER not in guard.audit_log_path.read_text(encoding="utf-8")
    assert "?" not in record.endpoint


@pytest.mark.parametrize("body", [
    b'{"patient_id":"SYNTHETIC_PRIVATE_VALUE_927"}',
    b'{"term":"patient_id=SYNTHETIC_PRIVATE_VALUE_927","term":"TP53"}',
    b'{"\\u0070atient_id":"SYNTHETIC_PRIVATE_VALUE_927"}',
    b"term=%70atient_id%3DSYNTHETIC_PRIVATE_VALUE_927&term=TP53",
])
def test_safe_description_cannot_replace_real_body(guard, monkeypatch, body):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("blocked body reached transport"))
    req = urllib.request.Request(PUBLIC_URL, data=body)
    with pytest.raises(EgressBlockedError):
        guarded_urlopen(req, guard=guard, payload={"safe": "TP53"})
    assert SENSITIVE_MARKER not in guard.audit_log_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("extra", [
    {"params": [("term", "patient_id=SYNTHETIC_PRIVATE_VALUE_927"), ("term", "TP53")]},
    {"params": "term=%70atient_id%3DSYNTHETIC_PRIVATE_VALUE_927"},
    {"data": b"patient_id=SYNTHETIC_PRIVATE_VALUE_927"},
    {"json": {"patient_id": SENSITIVE_MARKER}},
])
def test_requests_parameters_and_body_are_also_inspected(guard, extra):
    def transport(*args, **kwargs):
        pytest.fail("blocked request reached transport")

    with pytest.raises(EgressBlockedError):
        guarded_requests_get(PUBLIC_URL, request_get=transport, guard=guard,
                             payload={"safe": "TP53"}, **extra)
    assert SENSITIVE_MARKER not in guard.audit_log_path.read_text(encoding="utf-8")


def test_direct_guard_also_inspects_url_with_explicit_payload(guard):
    permitted, record = guard.evaluate_request(
        PUBLIC_URL + "?term=patient_id%3DSYNTHETIC_PRIVATE_VALUE_927",
        purpose="synthetic test", payload={"safe": "TP53"},
    )
    assert not permitted and record.outcome == "BLOCKED"


def test_public_query_body_and_description_reach_transport(guard, monkeypatch):
    calls = []

    def transport(request, **kwargs):
        calls.append(request)
        return io.BytesIO(b'{"gene":"TP53"}')

    monkeypatch.setattr(urllib.request, "urlopen", transport)
    req = urllib.request.Request(PUBLIC_URL + "?term=TP53&term=BRCA1", data=b'{"gene":"EGFR"}')
    with guarded_urlopen(req, guard=guard, payload={"public_dataset": "GSE96583"}) as response:
        assert json.loads(response.read())["gene"] == "TP53"
    assert calls == [req]
    assert guard.get_audit_trail()[-1].outcome == "PERMITTED"


def test_sensitive_explicit_payload_is_not_lost_with_safe_wire_bytes(guard, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("blocked metadata reached transport"))
    with pytest.raises(EgressBlockedError):
        guarded_urlopen(PUBLIC_URL + "?term=TP53", guard=guard, payload={"patient_id": SENSITIVE_MARKER})


def test_mcp_http_path_cannot_hide_sensitive_query_with_json_body(guard, monkeypatch, caplog):
    monkeypatch.setattr("bionexus.egress_guard._GLOBAL_GUARD", guard)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("blocked MCP query reached transport"))
    with pytest.raises(EgressBlockedError):
        asyncio.run(async_http_request(
            PUBLIC_URL + "?term=patient_id%3DSYNTHETIC_PRIVATE_VALUE_927",
            json_data={"safe": "TP53"}, max_retries=1,
        ))
    assert SENSITIVE_MARKER not in guard.audit_log_path.read_text(encoding="utf-8")
    assert SENSITIVE_MARKER not in caplog.text
