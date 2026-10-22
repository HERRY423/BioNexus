"""Bounded local MCP transport/real Codex app-server acceptance. No model turn.

Uses real child processes and newline JSON-RPC, never in-process tool mocks.
Run in a host environment that permits Windows asyncio loopback socketpairs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path


class JsonProcess:
    def __init__(self, command, out: Path, env=None, cwd=None):
        self.out = out
        out.mkdir(parents=True, exist_ok=False)
        self.trace = (out / 'wire.jsonl').open('x', encoding='utf-8')
        self.stderr = (out / 'stderr.log').open('x', encoding='utf-8')
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.stderr, text=True, encoding='utf-8', env=env, cwd=cwd,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.messages = queue.Queue()
        self.counter = 0
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        for line in self.process.stdout:
            try:
                self.messages.put(json.loads(line))
            except ValueError:
                self.messages.put({'invalid_stdout': line})
        self.messages.put({'eof': True})

    def send(self, value):
        self.trace.write(json.dumps({'direction': 'send', 'message': value}, ensure_ascii=False) + '\n')
        self.trace.flush()
        self.process.stdin.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')
        self.process.stdin.flush()

    def request(self, method, params=None, timeout=45):
        self.counter += 1
        ident = self.counter
        self.send({'jsonrpc': '2.0', 'id': ident, 'method': method, 'params': params or {}})
        end = time.monotonic() + timeout
        while True:
            response = self.messages.get(timeout=max(.01, end - time.monotonic()))
            self.trace.write(json.dumps({'direction': 'receive', 'message': response}, ensure_ascii=False) + '\n')
            self.trace.flush()
            if 'eof' in response or 'invalid_stdout' in response:
                raise RuntimeError(response)
            if response.get('id') == ident:
                return response
            if time.monotonic() >= end:
                raise TimeoutError(method)

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=10)
        self.thread.join(timeout=2)
        self.trace.close()
        self.stderr.close()


def cases():
    query = 'Compare drug treated vs control in scRNA'
    return [
        ('positive', {'query': query, 'data_metadata': {'min_replicates_per_condition': 3, 'is_integer_like': True}}, 'PERMITTED', False),
        ('refused', {'query': query, 'data_metadata': {'min_replicates_per_condition': 1, 'is_integer_like': True}}, 'ABSTAIN', False),
        ('unknown', {'query': 'hello what can you do'}, 'NEEDS_DATA', False),
        ('failed', {'query': query, 'data_metadata': {'num_donors': 'not-a-number'}}, 'FAILED', True),
        ('bool_string', {'query': query, 'data_metadata': {'perturbation': 'true'}}, 'FAILED', True),
        ('bool_count', {'query': query, 'data_metadata': {'num_donors': True}}, 'FAILED', True),
        ('missing_query', {}, 'FAILED', True),
        ('extra_arg', {'query': query, 'unknown': True}, 'FAILED', True),
        ('nullable', {'query': 'hello', 'data_metadata': None, 'lab_policy': None}, 'NEEDS_DATA', False),
        ('invalid_claim_class', {'query': query, 'data_metadata': {'min_replicates_per_condition': 3,
            'is_integer_like': True, 'claim_class': {'invalid': True}}}, 'FAILED', True),
    ]


def check_result(result, status, error):
    assert result.get('isError', False) is error, result
    texts = [x['text'] for x in result['content'] if x['type'] == 'text']
    assert len(texts) == 1
    assert result['structuredContent']['result'] == texts[0]
    payload = json.loads(texts[0])
    assert payload['status'] == status, payload
    contract = payload['evidence_contract']
    assert contract['scientific_facts_verified'] is False
    assert contract['scientific_authorization'] == 'NONE'
    assert contract['independence'] == 'UNKNOWN'
    assert (contract['outcome'] == 'POSITIVE') is (status == 'PERMITTED')
    if status == 'PERMITTED':
        assert contract['positive_basis'] == 'DECLARED_PREMISES'
        assert contract['input_integrity'] == 'UNKNOWN'
    return payload


def run(out, package_root, mode, codex=None):
    out.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, PYTHONPATH=str(package_root), PYTHONIOENCODING='utf-8',
               PYTHONDONTWRITEBYTECODE='1')
    env.pop('BIONEXUS_MCP_LEGACY_MODE', None)
    env.pop('BIONEXUS_MCP_AUDIT_LOG', None)
    env.pop('BIONEXUS_LOCAL_HOSTED_FALLBACKS', None)
    env['BIONEXUS_MCP_AUDIT_LOG'] = str(out / 'host-audit.jsonl')
    if mode == 'codex':
        home = out / 'isolated-home'
        home.mkdir()
        # Test-only process environment; never alter the user's CODEX_HOME/config.
        env['CODEX_HOME'] = str(home)
        cfg = '\n'.join([
            'model_provider = "acceptance_local"', 'model = "no-model-call"',
            '[model_providers.acceptance_local]', 'name = "Acceptance local only"',
            'base_url = "http://127.0.0.1:9/v1"', 'wire_api = "responses"',
            '[features]', 'plugins = false', 'remote_plugin = false', 'apps = false',
            '[analytics]', 'enabled = false',
            '[mcp_servers.candidate]', f'command = {json.dumps(sys.executable)}',
            'args = ["-B", "-m", "bionexus.mcp_server"]', 'startup_timeout_sec = 40',
            '[mcp_servers.candidate.env]', f'PYTHONPATH = {json.dumps(str(package_root))}',
            'PYTHONIOENCODING = "utf-8"', 'PYTHONDONTWRITEBYTECODE = "1"',
            f'BIONEXUS_MCP_AUDIT_LOG = {json.dumps(str(out / "host-audit.jsonl"))}',
        ])
        (home / 'config.toml').write_text(cfg, encoding='utf-8')
        command = [codex or shutil.which('codex'), 'app-server', '--stdio']
    else:
        command = [sys.executable, '-B', '-m', 'bionexus.mcp_server']
        if mode == 'legacy':
            command.append('--legacy')
    client = JsonProcess(command, out / 'process', env, out)
    records = []
    try:
        if mode == 'codex':
            init = client.request('initialize', {'clientInfo': {'name': 'bionexus-acceptance', 'version': '1.0'},
                'capabilities': {'experimentalApi': True}})
            assert 'result' in init, init
            client.send({'jsonrpc': '2.0', 'method': 'initialized'})
            started = client.request('thread/start', {'cwd': str(out), 'ephemeral': True,
                'approvalPolicy': 'never', 'sandbox': 'read-only', 'baseInstructions': 'Local MCP test only. No model turn.'})
            assert 'result' in started, started
            thread = started['result']['thread']['id']
            inventory = client.request('mcpServerStatus/list', {'threadId': thread, 'serverName': 'candidate'})
            (out / 'host-start.json').write_text(json.dumps({'initialize': init, 'thread': started, 'inventory': inventory}, indent=2), encoding='utf-8')
        else:
            init = client.request('initialize', {'protocolVersion': '2024-11-05',
                'capabilities': {}, 'clientInfo': {'name': 'bionexus-acceptance', 'version': '1.0'}})
            assert 'result' in init, init
            client.send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
            inventory = client.request('tools/list')
            assert 'result' in inventory, inventory
        for name, args, status, error in [*cases(), ('recovery', *cases()[0][1:])]:
            if mode == 'codex':
                response = client.request('mcpServer/tool/call', {'threadId': thread, 'server': 'candidate',
                    'tool': 'bionexus_warrant_check', 'arguments': args})
            else:
                response = client.request('tools/call', {'name': 'bionexus_warrant_check', 'arguments': args})
            assert 'result' in response, response
            payload = check_result(response['result'], status, error)
            records.append({'case': name, 'status': 'PASS', 'payload': payload})
        identities = {r['payload']['runtime_identity']['package_tree_sha256'] for r in records}
        assert len(identities) == 1
        probe_args = {'host_name': 'codex' if mode == 'codex' else 'transport-harness',
            'host_version': init['result'].get('userAgent', 'protocol-harness'), 'model': 'NO_MODEL_TURN',
            'session_id': 'acceptance-' + out.name, 'challenge': 'local-acceptance-' + out.name,
            'human_approved': False}
        params = {'threadId': thread, 'server': 'candidate', 'tool': 'bionexus_host_probe', 'arguments': probe_args} if mode == 'codex' else {'name': 'bionexus_host_probe', 'arguments': probe_args}
        bad_params = dict(params, arguments=dict(probe_args, challenge='short'))
        bad_probe = client.request('mcpServer/tool/call' if mode == 'codex' else 'tools/call', bad_params)
        failure = check_result(bad_probe['result'], 'FAILED', True)
        assert failure['error']['code'] == 'TOOL_EXECUTION_FAILED'
        assert not (out / 'host-audit.jsonl').exists()
        probe = client.request('mcpServer/tool/call' if mode == 'codex' else 'tools/call', params)
        result = probe['result']
        assert not result.get('isError', False), probe
        assert result['content'][0]['text'] == result['structuredContent']['result']
        receipt = json.loads(result['content'][0]['text'])
        assert receipt['status'] == 'RECORDED'
        assert receipt['human_approved'] is False
        assert receipt['host_identity_source'] == receipt['approval_source'] == 'DECLARED'
        assert receipt['acceptance_verdict'] == 'pending_run_validation'
        assert receipt['runtime_identity']['package_tree_sha256'] in identities
        # Independently verify the append-only receipt's hash and challenge binding.
        event = json.loads((out / 'host-audit.jsonl').read_text(encoding='utf-8'))
        event_hash = event.pop('event_hash')
        def digest(value):
            raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
            return 'sha256:' + hashlib.sha256(raw).hexdigest()
        assert event_hash == receipt['receipt_event_hash'] == digest(event)
        assert event['human_approved'] is False and event['challenge_sha256'] == digest({'challenge': probe_args['challenge']})
        assert event['runtime_identity'] == receipt['runtime_identity']
        (out / 'host-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        # Bind responses to the exact on-disk candidate package, independently of server code.
        root = package_root / 'bionexus'
        files = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(root.rglob('*')) if p.is_file() and p.suffix in {'.py', '.json'}}
        expected = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        assert identities == {expected}
        report = {'status': 'PASS', 'mode': mode, 'cases': records, 'runtime_package_sha256': expected,
                  'host_probe': 'PASS_DECLARED_IDENTITY_AND_NEGATIVE_APPROVAL_PRESERVED',
                  'actual_tool_exception_and_recovery': 'PASS',
                  'model_turns': 0, 'laboratory_trials': 0, 'package_root': str(package_root),
                  'host_scope': 'isolated real Codex app-server' if mode == 'codex' else 'subprocess stdio transport'}
        (out / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        print(json.dumps({'status': 'PASS', 'mode': mode, 'cases': len(records), 'runtime_package_sha256': expected}))
        return report
    finally:
        client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--package-root', required=True, type=Path)
    parser.add_argument('--mode', choices=['sdk', 'legacy', 'codex'], required=True)
    parser.add_argument('--codex')
    args = parser.parse_args()
    run(args.out.resolve(), args.package_root.resolve(), args.mode, args.codex)
