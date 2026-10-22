"""Governance contract at raw MCP boundaries; no external scientific services."""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bionexus.evidence_contract import interpret_positive_output
from bionexus.mcp.server import create_mcp_server, handle_rpc_request_async
from bionexus.mcp.transport import call_tool


def run(coro):
    return asyncio.run(coro)


def body(result):
    assert result['content'][0]['text'] == result['structuredContent']['result']
    value = json.loads(result['content'][0]['text'])
    c = value['evidence_contract']
    assert c['scientific_authorization'] == 'NONE'
    assert c['scientific_facts_verified'] is False
    return value


@pytest.mark.parametrize('arguments', [{}, {'query': 3}, {'query': 'hello', 'extra': True},
    {'query': 'hello', 'data_metadata': []}, {'query': 'hello', 'research_purpose': 'future'},
    {'query': 'hello', 'lab_policy': 'future'}, {'query': 'hello', 'intent_keywords': [1]},
    {'query': 'hello', 'data_metadata': {'num_donors': True}},
    {'query': 'hello', 'data_metadata': {'num_donors': -1}},
    {'query': 'hello', 'data_metadata': {'num_donors': 3.5}},
    {'query': 'hello', 'data_metadata': {'num_donors': '6'}},
    {'query': 'hello', 'data_metadata': {'perturbation': 'true'}},
    {'query': 'hello', 'data_metadata': {'independent_validation': 1}},
    {'query': 'hello', 'data_metadata': {'claim_class': {'invalid': True}}},
    {'query': 'hello', 'data_metadata': {'claim_class': 'future_class'}},
    {'query': 'hello', 'data_metadata': {'claim_class': ''}},
    {'query': 'hello', 'data_metadata': {'claim_class': 'causal', 'requested_claim_class': 'descriptive'}},
    {'query': 'hello', 'data_metadata': {'other': float('nan')}}])
def test_invalid_inputs_never_receive_a_positive_contract(arguments):
    result = run(call_tool('bionexus_warrant_check', arguments))
    assert result['isError'] is True
    assert body(result)['status'] == 'FAILED'


@pytest.mark.parametrize('name', ['future_tool', 'search_cosmic', 'search_pubmed'])
def test_unknown_and_unadvertised_tools_are_not_dispatched(name, monkeypatch):
    monkeypatch.delenv('BIONEXUS_LOCAL_HOSTED_FALLBACKS', raising=False)
    result = run(call_tool(name, {'query': 'synthetic'}))
    assert result['isError'] is True
    assert body(result)['error']['code'] == 'UNKNOWN_TOOL'


@pytest.mark.parametrize('minimum,expected', [(3, 'PERMITTED'), (1, 'ABSTAIN')])
def test_narrow_positive_and_refusal_remain_distinct(minimum, expected, canonical_backends_available):
    result = run(call_tool('bionexus_warrant_check', {'query': 'Compare drug treated vs control in scRNA',
        'data_metadata': {'min_replicates_per_condition': minimum, 'is_integer_like': True}}))
    assert result['isError'] is False
    value = body(result)
    assert value['status'] == expected
    assert interpret_positive_output(value, surface='mcp:bionexus_warrant_check')['positive'] is (minimum == 3)


def test_unknown_is_completed_call_without_scientific_conclusion():
    result = run(call_tool('bionexus_warrant_check', {'query': 'hello', 'data_metadata': None}))
    assert result['isError'] is False
    assert body(result)['status'] == 'NEEDS_DATA'


@pytest.mark.parametrize('failure', ['raise', 'reported', 'nonfinite'])
def test_execution_and_serialization_failures_are_errors(failure, monkeypatch):
    from bionexus.mcp.schemas import TOOL_ADAPTER_MAP
    async def broken(args):
        if failure == 'raise':
            raise RuntimeError('private-input-do-not-echo')
        return {'error': 'private-input-do-not-echo'} if failure == 'reported' else {'x': float('inf')}
    monkeypatch.setitem(TOOL_ADAPTER_MAP, 'bionexus_warrant_check', broken)
    result = run(call_tool('bionexus_warrant_check', {'query': 'hello'}))
    assert result['isError'] is True
    assert body(result)['status'] == 'FAILED'
    assert 'private-input-do-not-echo' not in str(result)


def test_claim_evaluation_failure_revokes_route_permit(monkeypatch, canonical_backends_available):
    from bionexus.claim_semantics import DeterministicWarrantEngine
    def broken(*args):
        raise RuntimeError('synthetic failure')
    monkeypatch.setattr(DeterministicWarrantEngine, 'evaluate', broken)
    result = run(call_tool('bionexus_warrant_check', {'query': 'Compare drug treated vs control in scRNA',
        'data_metadata': {'min_replicates_per_condition': 3, 'is_integer_like': True}}))
    assert result['isError'] is True
    value = body(result)
    assert value['status'] == 'FAILED'
    assert value['preflight_status_before_error'] == 'PERMITTED'
    assert value['evidence_contract']['assessment_kind'] == 'UNACCEPTED'


@pytest.mark.parametrize('corruption', ['error', 'governing', 'missing', 'contract'])
def test_consumer_rejects_conflicting_nested_state(corruption, canonical_backends_available):
    value = body(run(call_tool('bionexus_warrant_check', {'query': 'Compare drug treated vs control in scRNA',
        'data_metadata': {'min_replicates_per_condition': 3, 'is_integer_like': True}})))
    if corruption == 'error':
        value['claim_evaluation_error'] = 'ValueError'
    elif corruption == 'governing':
        value['claim_warrant_evaluation']['governing_status'] = 'NEEDS_DATA'
    elif corruption == 'missing':
        del value['claim_warrant_evaluation']
    else:
        value['claim_warrant_evaluation']['evidence_contract']['schema'] = 'future'
    with pytest.raises(ValueError):
        interpret_positive_output(value, surface='mcp:bionexus_warrant_check')


@pytest.mark.parametrize('approved', ['true', 1])
def test_sdk_raw_handler_never_coerces_host_approval(approved, monkeypatch, tmp_path):
    pytest.importorskip('mcp')
    from mcp import types
    audit = tmp_path / 'audit.jsonl'
    monkeypatch.setenv('BIONEXUS_MCP_AUDIT_LOG', str(audit))
    server = create_mcp_server()
    request = types.CallToolRequest(method='tools/call', params=types.CallToolRequestParams(
        name='bionexus_host_probe', arguments={'host_name': 'synthetic', 'host_version': '1',
            'session_id': 'synthetic-only', 'challenge': 'synthetic-challenge-2026',
            'model': 'none', 'human_approved': approved}))
    result = run(server._mcp_server.request_handlers[types.CallToolRequest](request)).root.model_dump()
    assert result['isError'] is True
    assert body(result)['status'] == 'FAILED'
    assert not audit.exists()


def test_host_receipt_preserves_declared_negative_approval(monkeypatch, tmp_path):
    audit = tmp_path / 'audit.jsonl'
    monkeypatch.setenv('BIONEXUS_MCP_AUDIT_LOG', str(audit))
    result = run(call_tool('bionexus_host_probe', {'host_name': 'synthetic', 'host_version': '1',
        'session_id': 'synthetic-only', 'challenge': 'synthetic-challenge-2026',
        'model': 'none', 'human_approved': False}))
    value = body(result)
    assert result['isError'] is False
    assert value['human_approved'] is False
    assert value['approval_source'] == 'DECLARED'
    assert value['acceptance_verdict'] == 'pending_run_validation'
    assert json.loads(audit.read_text())['human_approved'] is False


@pytest.mark.parametrize('rpc_request', [None, [], 1, {}, {'method': 'ping'},
    {'jsonrpc': '2.0', 'id': True, 'method': 'ping'},
    {'jsonrpc': '2.0', 'id': 1, 'method': 'ping', 'params': []}])
def test_invalid_legacy_requests_return_protocol_error(rpc_request):
    result = run(handle_rpc_request_async(rpc_request))
    assert result['error']['code'] == -32600


def test_legacy_notification_cannot_execute_tool(monkeypatch):
    from bionexus.mcp.schemas import TOOL_ADAPTER_MAP
    async def forbidden(args):
        pytest.fail('notification executed tool')
    monkeypatch.setitem(TOOL_ADAPTER_MAP, 'bionexus_warrant_check', forbidden)
    assert run(handle_rpc_request_async({'jsonrpc': '2.0', 'method': 'tools/call',
        'params': {'name': 'bionexus_warrant_check', 'arguments': {'query': 'hello'}}})) is None


@pytest.mark.parametrize('mode', ['sdk', 'legacy'])
def test_real_stdio_subprocess_matrix(mode, tmp_path):
    if mode == 'sdk':
        pytest.importorskip('mcp')
    from mcp_acceptance import run as acceptance
    report = acceptance(tmp_path / mode, Path(__file__).resolve().parents[2] / 'src', mode)
    assert report['status'] == 'PASS'


def test_sdk_crash_exits_nonzero_without_transport_switch(monkeypatch):
    import bionexus.mcp.server as server
    monkeypatch.delenv('BIONEXUS_MCP_LEGACY_MODE', raising=False)
    monkeypatch.setattr('sys.argv', ['server'])
    monkeypatch.setattr(server, 'FastMCP', object())
    def crash():
        raise RuntimeError('startup fault')
    monkeypatch.setattr(server, 'create_mcp_server', crash)
    with pytest.raises(SystemExit) as stopped:
        server.main()
    assert stopped.value.code == 1


def test_legacy_eof_drains_accepted_requests_and_recovers_parse_error(tmp_path):
    request = {'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call',
               'params': {'name': 'bionexus_warrant_check', 'arguments': {'query': 'hello'}}}
    package = Path(__file__).resolve().parents[2] / 'src'
    result = subprocess.run([sys.executable, '-B', '-m', 'bionexus.mcp_server', '--legacy'],
        input='not json\n' + json.dumps(request) + '\n', capture_output=True, text=True, timeout=30,
        cwd=tmp_path, env=dict(os.environ, PYTHONPATH=str(package), PYTHONIOENCODING='utf-8'))
    assert result.returncode == 0, result.stderr
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert any(r.get('error', {}).get('code') == -32700 for r in responses)
    completed = next(r for r in responses if r.get('id') == 7)
    assert body(completed['result'])['status'] == 'NEEDS_DATA'
