#!/usr/bin/env python3
"""Own one isolated SharedNet generation. Never adopt/kill untracked processes."""
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import uuid

PROJECT = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('MY_AGENTS_STATE', PROJECT / '.state/managed')).resolve()
ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
os.umask(0o077)
MANIFEST = ROOT / 'runtime.json'
ENV = dict(os.environ)
# Never let a parent Codex/Claude session auto-bind workers or auto-start serve.
for key in list(ENV):
    if key.startswith(('CODEX_', 'CLAUDE_')) and key not in ('CODEX_HOME', 'CLAUDE_CONFIG_DIR'):
        ENV.pop(key)
BIN = ENV.get('SHAREDNET_BIN', str(PROJECT.parent / 'sharednet-client/packages/cli/bin/sharednet.js'))
if not Path(BIN).is_file() and not ENV.get('SHAREDNET_BIN') and shutil.which('sharednet'):
    BIN = str(Path(shutil.which('sharednet')).resolve())
CLI = ['node', BIN]
ENV['SHAREDNET_BIN'] = BIN


def identity(pid):
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'lstart=', '-o', 'command='], capture_output=True, text=True, env={**os.environ, 'LC_ALL': 'C', 'TZ': 'UTC'})
    return result.stdout.strip() if result.returncode == 0 else ''


def alive(record):
    return bool(record and record.get('identity') and identity(record['pid']) == record['identity'])


def save(data):
    tmp = MANIFEST.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(MANIFEST)


def stop_one(data, name):
    record = data['processes'].get(name)
    if alive(record):
        # All managed services are session leaders. PID plus start time/command
        # protects against a stale PID accidentally targeting another program.
        os.killpg(record['pid'], signal.SIGTERM)
        until = time.monotonic() + 5
        while alive(record) and time.monotonic() < until:
            time.sleep(.1)
        if alive(record):
            os.killpg(record['pid'], signal.SIGKILL)
    data['processes'].pop(name, None)
    save(data)


def stop_all(data):
    for name in ('ngrok', 'mcp', 'serve', 'local'):
        stop_one(data, name)


def free_port(port):
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(('127.0.0.1', port))
        except OSError as error:
            raise RuntimeError(f'Port {port} is occupied or unavailable; refusing to adopt or stop its owner: {error}') from error


def run(data, *args):
    p = subprocess.run(CLI + list(args), cwd=data['cwd'], env=ENV, capture_output=True, text=True, timeout=30)
    if p.returncode:
        # CLI errors may contain invite tokens: do not echo argv or raw stderr.
        raise RuntimeError(f'SharedNet {args[0]} failed (exit {p.returncode}); no new Room will be created on retry')
    return json.loads(p.stdout) if p.stdout.strip() else {}


def start_process(data, name, argv):
    if alive(data['processes'].get(name)):
        return
    with (ROOT / f'{name}.log').open('ab') as log:
        p = subprocess.Popen(argv, cwd=data['cwd'], env=ENV, stdin=subprocess.DEVNULL,
                             stdout=log, stderr=log, start_new_session=True)
    try:
        record = {'pid': p.pid, 'identity': identity(p.pid)}
        if not record['identity']:
            raise RuntimeError(f'Cannot verify newly started {name} process')
    except (OSError, RuntimeError):
        p.terminate()
        p.wait(timeout=5)
        raise
    data['processes'][name] = record
    save(data)
    time.sleep(.15)
    if p.poll() is not None or not alive(record):
        raise RuntimeError(f'{name} failed to start; inspect {ROOT / (name + ".log")}')


def wait_for(check, label):
    until = time.monotonic() + 20
    while time.monotonic() < until:
        try:
            result = check()
            if result:
                return result
        except (OSError, ValueError, RuntimeError):
            pass
        time.sleep(.2)
    raise RuntimeError(f'{label} did not become ready within 20 seconds; logs: {ROOT}')


def json_get(url):
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=2) as response:
        return json.load(response)


def configure_env(data):
    gen = Path(data['cwd'])
    ENV['XDG_STATE_HOME'] = str(gen / 'xdg/state')
    ENV['XDG_CONFIG_HOME'] = str(gen / 'xdg/config')
    ENV['SHAREDNET_CWD'] = str(gen)
    ENV['MY_AGENTS_INSTANCE'] = data['instance']
    ENV['MCP_PORT'] = str(data['config']['mcp_port'])
    for key in ('SHAREDNET_API_KEY', 'SHAREDNET_BASE_URL', 'SHAREDNET_SEAT'):
        ENV.pop(key, None)


def load_local_env(data):
    path = Path(ENV['XDG_STATE_HOME']) / f'sharednet/local/{data["port"]}.env'
    if not path.exists() or not alive(data['processes'].get('local')):
        return False
    content = path.read_text()
    if f'(pid {data["processes"]["local"]["pid"]})' not in content:
        return False
    values = dict(re.findall(r'^export (SHAREDNET_[A-Z_]+)=([^\s]+)$', content, re.M))
    if values.get('SHAREDNET_BASE_URL') != f'http://127.0.0.1:{data["port"]}' or not values.get('SHAREDNET_API_KEY'):
        return False
    ENV.update(values)
    # Authenticated protocol check, not merely "something answered HTTP".
    request = urllib.request.Request(values['SHAREDNET_BASE_URL'] + '/api/v1/agents', headers={'Authorization': 'Bearer ' + values['SHAREDNET_API_KEY']})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=2) as response:
            payload = json.load(response)
            if not isinstance(payload, dict) or 'items' not in payload:
                raise RuntimeError('Unexpected SharedNet API response')
    except OSError as error:
        raise RuntimeError('SharedNet authenticated health check failed') from error
    return True


def start(data, mode):
    if not Path(BIN).is_file():
        raise RuntimeError('Set SHAREDNET_BIN to sharednet.js, or install sharednet on PATH')
    port = int(ENV.get('PORT', '3001'))
    mcp_port = int(ENV.get('MCP_PORT', '3002'))
    if not all(0 < p < 65536 for p in (port, mcp_port)) or port == mcp_port:
        raise RuntimeError('Invalid or overlapping PORT/MCP_PORT')
    workers = ENV.get('WORKERS', 'codex,claude').split(',')
    if not workers or len(workers) != len(set(workers)) or any(not re.fullmatch(r'[a-z][a-z0-9-]*', w) or w == 'brain' for w in workers):
        raise RuntimeError('WORKERS must contain unique adapter names, excluding brain')
    bindings = {w: ENV.get('DEEPSEEK_ADAPTER', 'deepseek-harness') if w == 'deepseek' else w for w in workers}
    if ENV.get('NATIVE_SESSIONS') == '1':
        native_agents = set(ENV.get('NATIVE_SESSION_AGENTS', 'codex,deepseek').split(','))
        bindings = {name: adapter + '-native' if name in native_agents and adapter in ('codex', 'claude', 'deepseek-harness') else adapter
                    for name, adapter in bindings.items()}
    if mode == 'local':
        bindings['brain'] = ENV.get('BRAIN', 'chatgpt')
    for adapter in bindings.values():
        if not re.fullmatch(r'[a-z][a-z0-9-]*', adapter) or not os.access(PROJECT / f'adapters/{adapter}.sh', os.X_OK):
            raise RuntimeError(f'Missing executable adapter: {adapter}')
    config = {'mode': mode, 'port': port, 'mcp_port': mcp_port, 'bindings': bindings,
              'ngrok': mode == 'web' and ENV.get('START_NGROK', '1') != '0', 'bin': BIN}
    if data and data['config'] != config and any(alive(r) for r in data['processes'].values()):
        raise RuntimeError('Configuration changed. Run ./stop.sh before changing a managed instance.')
    if data and not alive(data['processes'].get('local')):
        stop_all(data)
        # Only this manager's generation; legacy .state/xdg is never touched.
        old = Path(data['cwd'])
        if old.parent == ROOT and old.name.startswith('generation-'):
            shutil.rmtree(old, ignore_errors=True)
        data = None
    if not data:
        free_port(port)
        if mode == 'web':
            free_port(mcp_port)
        if config['ngrok']:
            free_port(4040)
        gen = ROOT / f'generation-{uuid.uuid4().hex}'
        gen.mkdir(mode=0o700)
        data = {'config': config, 'port': port, 'instance': uuid.uuid4().hex, 'cwd': str(gen), 'processes': {}, 'seats': {}}
        save(data)
    configure_env(data)
    if not alive(data['processes'].get('local')):
        free_port(port)
        start_process(data, 'local', CLI + ['local', '--port', str(port), '--json'])
    wait_for(lambda: load_local_env(data), 'SharedNet authenticated API')
    if 'sid' not in data:
        data['sid'] = run(data, 'session', 'start', '--new', '--json')['session_id']
        save(data)
    if 'rid' not in data:
        # Recover a room created just before an interrupted manifest write.
        rooms = run(data, 'room', 'list', '--session', data['sid'], '--json')
        existing = [r for r in rooms.get('items', rooms.get('rooms', [])) if r.get('name') == 'my-agents-managed']
        data['rid'] = existing[0]['id'] if existing else run(data, 'room', 'create', '--name', 'my-agents-managed', '--session', data['sid'], '--json')['room']['id']
        save(data)
    invite = run(data, 'room', 'invite', data['rid'], '--session', data['sid'], '--json')['for_agents']
    # Recover already-written seats after interrupted setup before adding any.
    seats_dir = Path(ENV['XDG_CONFIG_HOME']) / 'sharednet/rooms' / data['rid']
    for path in seats_dir.glob('*.json'):
        seat = json.loads(path.read_text())
        data['seats'].setdefault(seat['name'], seat['member_id'])
    for name in ['brain', *workers]:
        if name not in data['seats']:
            data['seats'][name] = run(data, 'join', invite, '--name', name, '--no-wake', '--json')['member_id']
            save(data)
        if name in bindings:
            run(data, 'wake', 'set', 'command', '--command', str(PROJECT / f'adapters/{bindings[name]}.sh'), '--as', data['seats'][name], '--json')
        elif name == 'brain':
            run(data, 'wake', 'off', '--as', data['seats'][name], '--json')
    save(data)
    ENV['SHAREDNET_SEAT'] = data['seats']['brain']
    run(data, 'read', '--last', '1', '--as', ENV['SHAREDNET_SEAT'], '--json')
    start_process(data, 'serve', CLI + ['serve'])
    wait_for(lambda: run(data, 'serve', '--status', '--json').get('running'), 'serve')
    if mode == 'web':
        if not alive(data['processes'].get('mcp')):
            free_port(mcp_port)
        start_process(data, 'mcp', ['node', str(PROJECT / 'mcp-server/server.mjs')])
        wait_for(lambda: json_get(f'http://127.0.0.1:{mcp_port}/health').get('instance') == data['instance'], 'MCP')
        if config['ngrok']:
            if not alive(data['processes'].get('ngrok')):
                free_port(4040)
            start_process(data, 'ngrok', [ENV.get('NGROK_BIN', shutil.which('ngrok') or 'ngrok'), 'http', str(mcp_port)])
            def tunnel():
                if not alive(data['processes'].get('ngrok')):
                    return None
                for t in json_get('http://127.0.0.1:4040/api/tunnels').get('tunnels', []):
                    if t.get('config', {}).get('addr') in (f'http://localhost:{mcp_port}', f'http://127.0.0.1:{mcp_port}', f'localhost:{mcp_port}', str(mcp_port)) and t.get('public_url', '').startswith('https://'):
                        return t['public_url']
            url = wait_for(tunnel, 'ngrok tunnel') + '/mcp'
        else:
            url = f'http://127.0.0.1:{mcp_port}/mcp'
        print(f'MCP URL: {url}')
    print(f'Ready. Room: {data["rid"]}; brain: {data["seats"]["brain"]}; state: {ROOT}')
    return data


def main():
    with (ROOT / 'runtime.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another start/stop is in progress')
        if not identity(os.getpid()):
            raise RuntimeError('Process identity inspection is unavailable; no service was started')
        data = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else None
        if sys.argv[1] == 'stop':
            if data:
                stop_all(data)
            print('Stopped managed processes only; legacy/untracked processes were not touched.')
        else:
            start(data, sys.argv[2])


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, KeyError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
