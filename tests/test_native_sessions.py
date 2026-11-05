import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('native_runner', PROJECT / 'adapters/native_runner.py')
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


class NativeSessions(unittest.TestCase):
    def test_persistence_resume_dedup_and_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub = root / 'codex'
            stub.write_text('''#!/usr/bin/env python3
import json,sys,os
from pathlib import Path
p=Path(os.environ['CALLS'])
with p.open('a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')
print(json.dumps({'type':'thread.started','thread_id':'native-123'}),flush=True)
prompt=sys.stdin.read()
if prompt == 'fail': sys.exit(2)
print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'remembered'}}))
print(json.dumps({'type':'turn.completed'}))
''')
            stub.chmod(0o700)
            env = dict(PATH=tmp + ':' + os.environ['PATH'], CALLS=str(root/'calls'),
                       NATIVE_SESSION_STATE=str(root/'state'), AGENT_WORKDIR=tmp)
            data = dict(room_id='room', member_id='seat', through=1, prompt='remember',
                        messages=[{'content':'[TASK-20261105-UI01] remember'}])
            with patch.dict(os.environ, env):
                self.assertEqual(native.run('codex', data), 'remembered')
                self.assertEqual(native.run('codex', data), 'remembered')
                self.assertEqual(len((root/'calls').read_text().splitlines()), 1)
                self.assertEqual(native.run('codex', dict(data, through=2)), 'remembered')
                calls = [json.loads(x) for x in (root/'calls').read_text().splitlines()]
                self.assertNotIn('resume', calls[0])
                self.assertIn('resume', calls[1])
                self.assertIn('native-123', calls[1])
                with self.assertRaisesRegex(RuntimeError, 'Stale'):
                    native.run('codex', data)
                with self.assertRaises(RuntimeError):
                    native.run('codex', dict(data, through=3, prompt='fail'))
                record = json.loads(next((root/'state').glob('*.json')).read_text())
                self.assertEqual(record['native_session_id'], 'native-123')
                self.assertEqual(record['status'], 'failed')
                self.assertEqual(record['tasks'], ['TASK-20261105-UI01'])
                with self.assertRaisesRegex(RuntimeError, 'uncertain'):
                    native.run('codex', dict(data, through=3, prompt='fail'))
                self.assertEqual(len((root/'calls').read_text().splitlines()), 3)
                native.run('codex', dict(data, member_id='another'))
                self.assertEqual(len(list((root/'state').glob('*.json'))), 2)
                # Explicit task identity must separate same-seat tasks.
                native.run('codex', dict(data, task_id='TASK-A'))
                native.run('codex', dict(data, task_id='TASK-B'))
                self.assertEqual(len(list((root/'state').glob('*.json'))), 4)
                task_records = [json.loads(p.read_text()) for p in (root/'state').glob('*.json')]
                self.assertEqual({r.get('task_id') for r in task_records if r.get('task_id')}, {'TASK-A', 'TASK-B'})
                calls = [json.loads(x) for x in (root/'calls').read_text().splitlines()]
                self.assertNotIn('resume', calls[-1])
                self.assertNotIn('resume', calls[-2])


    def test_task_sandbox_is_explicit_and_bounded(self):
        with patch.dict(os.environ, {'CODEX_TASK_SANDBOX': 'read-only'}):
            self.assertIn('sandbox_mode="read-only"', native.command('codex', None))
        with patch.dict(os.environ, {'CODEX_TASK_SANDBOX': 'workspace-write'}):
            self.assertIn('sandbox_mode="workspace-write"', native.command('codex', None))
        with patch.dict(os.environ, {'CODEX_TASK_SANDBOX': 'danger-full-access'}):
            with self.assertRaises(ValueError): native.command('codex', None)

    def test_provider_resume_commands(self):
        self.assertEqual(native.command('deepseek-harness', 'session-42'),
                         ['dsh', 'headless', '--json', '--session-id', 'session-42', '-'])
        self.assertIn('--resume', native.command('claude', 'uuid'))
        self.assertEqual(native.event_values('claude', {'type':'result','session_id':'uuid','result':'ok'}),
                         ('uuid', 'ok', False))
        self.assertEqual(native.event_values('deepseek-harness', {'type':'session','sessionId':'session-42'}),
                         ('session-42', None, False))


if __name__ == '__main__':
    unittest.main()
