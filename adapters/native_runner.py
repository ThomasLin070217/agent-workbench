#!/usr/bin/env python3
"""Opt-in durable CLI sessions. Native harnesses own transcripts; we store IDs only."""
import fcntl
import hashlib
import json
import math
import os
import re
import shlex
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import time


class Busy(Exception):
    pass


def command(kind, session):
    if kind == 'codex':
        sandbox = os.environ.get('CODEX_TASK_SANDBOX', 'read-only')
        if sandbox not in ('read-only', 'workspace-write'):
            raise ValueError('Invalid task sandbox')
        common = ['--json', '--skip-git-repo-check', '-c', f'sandbox_mode="{sandbox}"', '-c', 'approval_policy="never"']
        return ['codex', 'exec'] + (['resume'] if session else []) + common + ([session] if session else []) + ['-']
    if kind == 'claude':
        return ['claude', '-p', '--verbose', '--output-format', 'stream-json'] + (['--resume', session] if session else [])
    if kind == 'deepseek-harness':
        return ['dsh', 'headless', '--json'] + (['--session-id', session] if session else []) + ['-']
    raise ValueError('Unsupported native harness')


def event_values(kind, event):
    if kind == 'codex':
        sid = event.get('thread_id') if event.get('type') == 'thread.started' else None
        item = event.get('item', {})
        reply = item.get('text') if event.get('type') == 'item.completed' and item.get('type') == 'agent_message' else None
        failed = event.get('type') == 'turn.failed'
    elif kind == 'claude':
        sid = event.get('session_id')
        reply = event.get('result') if event.get('type') == 'result' else None
        failed = event.get('type') == 'result' and event.get('is_error', False)
    else:
        sid = event.get('sessionId') if event.get('type') == 'session' else None
        reply = event.get('text') if event.get('type') == 'final' else None
        failed = event.get('type') == 'error'
    return sid, reply, failed


def run(kind, data):
    prompt = data.get('prompt')
    if not isinstance(prompt, str) or not prompt.strip() or '\0' in prompt:
        raise ValueError('A nonempty prompt is required')
    if not data.get('room_id') or not data.get('member_id'):
        raise ValueError('room_id and member_id are required for session isolation')
    timeout = float(os.environ.get('ADAPTER_TIMEOUT', '180'))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('Invalid timeout')
    workspace = str(Path(os.environ.get('AGENT_WORKDIR', Path(__file__).resolve().parents[1])).resolve())
    # Keep outside the disposable SharedNet generation directory.
    root = Path(os.environ.get('NATIVE_SESSION_STATE', Path(__file__).resolve().parents[1] / '.state/native-sessions'))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    home_key, home_default = {
        'codex': ('CODEX_HOME', '.codex'),
        'claude': ('CLAUDE_CONFIG_DIR', '.claude'),
        'deepseek-harness': ('DSH_HOME', '.dsh'),
    }[kind]
    harness_home = str(Path(os.environ.get(home_key, Path.home() / home_default)).resolve())
    identity = [kind, data['room_id'], data['member_id'], workspace, harness_home]
    task_id = data.get('task_id')
    if task_id:
        if not isinstance(task_id, str) or not re.fullmatch(r'TASK-[A-Za-z0-9-]+', task_id):
            raise ValueError('Invalid task_id')
        identity.append(task_id)
    key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    path = root / (key + '.json')
    with (root / (key + '.lock')).open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Busy('This native session is already running') from None
        record = json.loads(path.read_text()) if path.exists() else {
            'agent': kind, 'room_id': data['room_id'], 'member_id': data['member_id'],
            'workspace': workspace, 'harness_home': harness_home, 'native_session_id': None, 'tasks': [],
            'gui_verified': False,
        }
        delivery = data.get('through')
        if delivery is not None and (not isinstance(delivery, int) or isinstance(delivery, bool) or delivery < 0):
            raise ValueError('through must be a nonnegative integer')
        if delivery is not None and record.get('delivery') is not None and delivery < record['delivery']:
            raise RuntimeError('Stale delivery rejected; native session has already advanced')
        if delivery is not None and record.get('delivery') == delivery:
            if record.get('status') == 'completed':
                return record['reply']
            raise RuntimeError('Delivery outcome uncertain/failed; inspect the native session before resubmitting with a new sequence')
        tasks = [data['task_id']] if data.get('task_id') else []
        for message in data.get('messages', []):
            if isinstance(message, dict):
                tasks.extend(re.findall(r'\bTASK-[A-Za-z0-9-]+\b', str(message.get('content', ''))))
        for task in tasks:
            if task not in record['tasks']:
                record['tasks'].append(task)

        def save():
            record['updated_at'] = time.time()
            fd, tmp = tempfile.mkstemp(dir=root, prefix=key, suffix='.tmp')
            try:
                with os.fdopen(fd, 'w') as out:
                    json.dump(record, out, ensure_ascii=False, indent=2)
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(tmp, path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)

        record.update(status='starting', delivery=delivery)
        if task_id:
            record.update(task_id=task_id, project_id=data.get('project_id'), task_title=data.get('task_title'))
        save()
        child = None
        reply = None
        failed = False
        completed = False
        try:
            # File stdin avoids pipe deadlock for large wake prompts. Diagnostics stay private.
            with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as errors:
                source.write(prompt.encode())
                source.seek(0)
                env = dict(os.environ)
                if kind == 'deepseek-harness' and not env.get('DEEPSEEK_API_KEY'):
                    credentials = Path(env.get('DSH_CREDENTIALS_FILE', str(Path.home() / '.dsh/.credentials.yaml')))
                    if credentials.is_file():
                        match = re.search(r'^\s*DEEPSEEK_API_KEY:\s*(.+)$', credentials.read_text(), re.M)
                        if match:
                            values = shlex.split(match[1], comments=True)
                            if len(values) == 1 and values[0] not in ('null', '~', '|', '>'):
                                env['DEEPSEEK_API_KEY'] = values[0]
                child = subprocess.Popen(command(kind, record['native_session_id']), stdin=source,
                    stdout=subprocess.PIPE, stderr=errors, cwd=workspace, env=env, start_new_session=True)
                start = time.monotonic()
                buffer = b''
                total = 0
                with selectors.DefaultSelector() as selector:
                    selector.register(child.stdout, selectors.EVENT_READ)
                    while selector.get_map():
                        if time.monotonic() - start > timeout:
                            raise RuntimeError('Native harness timed out; session ID retained for recovery')
                        for ready, _ in selector.select(.2):
                            chunk = os.read(ready.fileobj.fileno(), 65536)
                            if not chunk:
                                selector.unregister(ready.fileobj)
                                continue
                            total += len(chunk)
                            if total > 16 * 1024 * 1024:
                                raise RuntimeError('Native event stream exceeded 16 MiB')
                            buffer += chunk
                            while b'\n' in buffer:
                                line, buffer = buffer.split(b'\n', 1)
                                try:
                                    event = json.loads(line)
                                except ValueError:
                                    continue
                                if not isinstance(event, dict):
                                    continue
                                sid, text, error = event_values(kind, event)
                                completed = completed or event.get('type') == {
                                    'codex': 'turn.completed', 'claude': 'result', 'deepseek-harness': 'final'
                                }[kind]
                                if sid:
                                    if record['native_session_id'] and sid != record['native_session_id']:
                                        raise RuntimeError('Harness changed session ID unexpectedly')
                                    record.update(native_session_id=sid, status='running')
                                    save()
                                if text:
                                    reply = text
                                failed = failed or error
                child.wait(timeout=max(.1, timeout - (time.monotonic() - start)))
                if child.returncode or failed or not completed or not reply or not record['native_session_id']:
                    raise RuntimeError(f'Native harness did not complete successfully (exit {child.returncode}); verify login/network/provider')
            record.update(status='completed', reply=reply)
            save()
            return reply
        except BaseException:
            if child is not None and child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            record['status'] = 'failed'
            save()
            raise
        finally:
            if child is not None and child.stdout is not None:
                child.stdout.close()


if __name__ == '__main__':
    os.umask(0o077)
    def interrupted(signum, frame):
        raise RuntimeError('Native adapter interrupted; inspect saved session before retrying')
    signal.signal(signal.SIGTERM, interrupted)
    try:
        print(run(sys.argv[1], json.load(sys.stdin)))
    except Busy as error:
        print(str(error), file=sys.stderr)
        sys.exit(75)
    except Exception as error:
        print(f'Native adapter failed: {error}', file=sys.stderr)
        sys.exit(1)
