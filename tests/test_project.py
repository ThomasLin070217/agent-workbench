import importlib.util
import io
import fcntl
import sys
import urllib.error
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import unittest
import urllib.request
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]


def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Adapters(unittest.TestCase):
    def test_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('claude', 'codex', 'dsh'):
                path = Path(tmp) / name
                path.write_text('''#!/usr/bin/env python3
import os, sys, time
from pathlib import Path
mode=os.environ.get('FAKE_MODE','ok')
if mode=='fail': sys.exit(23)
if mode=='timeout': time.sleep(5)
if mode=='empty': sys.exit(0)
reply='first line\\nlast line'
if '--output-last-message' in sys.argv:
    Path(sys.argv[sys.argv.index('--output-last-message')+1]).write_text(reply)
else: print(reply)
''')
                path.chmod(0o700)
            env = dict(os.environ, PATH=tmp + ':' + os.environ['PATH'])
            for name in ('claude', 'codex', 'deepseek-harness'):
                for mode in ('ok', 'fail', 'empty', 'timeout'):
                    with self.subTest(adapter=name, mode=mode):
                        p = subprocess.run([str(PROJECT / f'adapters/{name}.sh')], input=json.dumps({'prompt': '--not-a-flag\nhello'}), text=True, capture_output=True, env=dict(env, FAKE_MODE=mode, ADAPTER_TIMEOUT='.2' if mode == 'timeout' else '3'), timeout=4)
                        if mode == 'ok':
                            self.assertEqual(p.returncode, 0, p.stderr)
                            self.assertEqual(p.stdout.strip(), 'first line\nlast line')
                        else:
                            self.assertNotEqual(p.returncode, 0)
                            self.assertEqual(p.stdout, '')
            for name in ('claude', 'codex', 'deepseek-harness', 'chatgpt', 'deepseek'):
                for payload in ('not json', '{}', '{"prompt": 3}', '{"prompt":"  "}'):
                    p = subprocess.run([str(PROJECT / f'adapters/{name}.sh')], input=payload, text=True, capture_output=True, env=env)
                    self.assertNotEqual(p.returncode, 0)
                    self.assertEqual(p.stdout, '')
            for name, key in [('chatgpt', 'OPENAI_API_KEY'), ('deepseek', 'DEEPSEEK_API_KEY')]:
                p = subprocess.run([str(PROJECT / f'adapters/{name}.sh')], input='{"prompt":"hello"}', text=True, capture_output=True, env=dict(env, **{key: ''}))
                self.assertNotEqual(p.returncode, 0)
                self.assertEqual(p.stdout, '')


    def test_api_responses(self):
        spec = importlib.util.spec_from_file_location('adapter_runner', PROJECT / 'adapters/runner.py')
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        for provider, key in [('chatgpt', 'OPENAI_API_KEY'), ('deepseek', 'DEEPSEEK_API_KEY')]:
            for reply in ('line one\nline two', '', None):
                with self.subTest(provider=provider, reply=reply), patch.dict(os.environ, {key: 'test-only-key'}), patch.object(sys, 'argv', ['runner', provider]), patch.object(sys, 'stdin', io.StringIO('{"prompt":"hello"}')), patch.object(sys, 'stdout', io.StringIO()) as output, patch.object(runner.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps({'choices': [{'message': {'content': reply}}]}).encode())):
                    if reply:
                        runner.main()
                        self.assertEqual(output.getvalue().strip(), reply)
                    else:
                        with self.assertRaises(RuntimeError): runner.main()
            with patch.dict(os.environ, {key: 'test-only-key'}), patch.object(sys, 'argv', ['runner', provider]), patch.object(sys, 'stdin', io.StringIO('{"prompt":"hello"}')), patch.object(runner.urllib.request, 'urlopen', side_effect=urllib.error.HTTPError('https://example.invalid', 401, 'unauthorized', {}, None)):
                with self.assertRaisesRegex(RuntimeError, 'HTTP 401'): runner.main()


class Integration(unittest.TestCase):
    def test_real_sharednet_mcp_lifecycle(self):
        with tempfile.TemporaryDirectory(prefix='my-agents-integration-') as tmp:
            sp, mp = port(), port()
            with patch.dict(os.environ, MY_AGENTS_STATE=tmp, PORT=str(sp), MCP_PORT=str(mp), START_NGROK='0', WORKERS='codex,claude'):
                spec = importlib.util.spec_from_file_location('runtime_test', PROJECT / 'runtime.py')
                runtime = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(runtime)
            # The sandbox denies ps. Replace ONLY process identity probing with
            # Popen ownership tracking for children created in this test.
            children = {}
            real_popen = subprocess.Popen
            def popen(*args, **kwargs):
                p = real_popen(*args, **kwargs)
                children[p.pid] = p
                return p
            def identity(pid):
                p = children.get(pid)
                return f'test-owned-{pid}' if p and p.poll() is None else ''
            def rpc(method, params=None, extra=None):
                body = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}
                headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream', **(extra or {})}
                req = urllib.request.Request(f'http://127.0.0.1:{mp}/mcp', data=json.dumps(body).encode(), headers=headers)
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=10) as response:
                    self.assertNotIn('mcp-session-id', response.headers)
                    return json.load(response)
            with patch.object(runtime, 'identity', identity), patch.object(runtime.subprocess, 'Popen', popen):
                try:
                    # Lock contention must fail before any process starts.
                    with (runtime.ROOT / 'runtime.lock').open('a') as lock:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        with patch.object(sys, 'argv', ['runtime', 'start', 'web']):
                            with self.assertRaisesRegex(RuntimeError, 'in progress'): runtime.main()
                    data = runtime.start(None, 'web')
                    first = json.loads(runtime.MANIFEST.read_text())
                    again = runtime.start(data, 'web')
                    self.assertEqual(first['rid'], again['rid'])
                    self.assertEqual(first['processes'], again['processes'])
                    # Simulate interruption after remote creation/local seat write
                    # but before the corresponding manifest checkpoint.
                    recovered = json.loads(json.dumps(again))
                    recovered.pop('rid')
                    recovered['seats'] = {}
                    data = runtime.start(recovered, 'web')
                    self.assertEqual(data['rid'], first['rid'])
                    self.assertEqual(data['seats'], first['seats'])
                    self.assertEqual(len(list(Path(runtime.ENV['XDG_CONFIG_HOME']).glob('sharednet/rooms/*'))), 1)
                    self.assertEqual(len(set(again['seats'].values())), 3)
                    init = rpc('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'smoke', 'version': '1'}})
                    self.assertIn('result', init)
                    self.assertEqual(len(rpc('tools/list')['result']['tools']), 2)
                    say = rpc('tools/call', {'name': 'room_say', 'arguments': {'message': 'smoke: no worker mention'}})
                    self.assertNotIn('isError', say['result'])
                    read = rpc('tools/call', {'name': 'room_read', 'arguments': {}})
                    messages = json.loads(read['result']['content'][0]['text'])['items']
                    self.assertEqual(messages[-1]['sender']['name'], 'brain')
                    invalid = rpc('tools/call', {'name': 'room_read', 'arguments': {'count': 0}})
                    self.assertTrue(invalid['result']['isError'])
                    spoof = rpc('tools/call', {'name': 'room_say', 'arguments': {'message': 'spoof', 'seat': data['seats']['codex']}})
                    self.assertTrue(spoof['result']['isError'])
                    # MCP-only restart retains Room and works without reinitialization,
                    # even if a client sends a stale session header.
                    runtime.stop_one(data, 'mcp')
                    data = runtime.start(data, 'web')
                    self.assertEqual(data['rid'], first['rid'])
                    self.assertNotIn('isError', rpc('tools/call', {'name': 'room_read', 'arguments': {}}, {'Mcp-Session-Id': 'old-session'})['result'])
                    # An invalid credential must fail without making another Room.
                    env_file = Path(runtime.ENV['XDG_STATE_HOME']) / f'sharednet/local/{sp}.env'
                    original = env_file.read_text()
                    env_file.write_text(original.replace('SHAREDNET_API_KEY=', 'SHAREDNET_API_KEY=wrong'))
                    with self.assertRaises(RuntimeError): runtime.load_local_env(data)
                    env_file.write_text(original)
                    # Local memory lost -> stop ONLY tracked dependents, fresh generation.
                    old_cwd = data['cwd']
                    runtime.stop_one(data, 'local')
                    data = runtime.start(data, 'web')
                    self.assertNotEqual(data['rid'], first['rid'])
                    self.assertFalse(Path(old_cwd).exists())
                    runtime.stop_all(data)
                    # Port occupied by another listener is never adopted.
                    with socket.socket() as occupied:
                        occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        occupied.bind(('127.0.0.1', sp)); occupied.listen()
                        with self.assertRaisesRegex(RuntimeError, 'occupied'):
                            runtime.start(data, 'web')
                finally:
                    for p in reversed(list(children.values())):
                        if p.poll() is None:
                            p.terminate()
                            try: p.wait(timeout=3)
                            except subprocess.TimeoutExpired:
                                p.kill(); p.wait(timeout=3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
