import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
import session_links
import viewer

CID='00000000-0000-4000-8000-000000000001'
DID='session-00000000-0000-4000-8000-000000000002'

class Links(unittest.TestCase):
    def test_exact_native_ids_and_busy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'one.json').write_text(json.dumps({'agent':'codex','native_session_id':CID,'status':'completed','tasks':['TASK-UI01']}))
            (root/'two.json').write_text(json.dumps({'agent':'deepseek-harness','native_session_id':DID,'status':'completed'}))
            items=session_links.list_sessions([root], 'http://127.0.0.1:3080',True)['items']
            self.assertEqual(items[0]['href'],'codex://threads/'+CID)
            self.assertEqual(items[1]['href'],'dsh://open')
            (root/'one.json').write_text(json.dumps({'agent':'codex','native_session_id':CID,'status':'running'}))
            self.assertIsNone(session_links.list_sessions([root])['items'][0]['href'])
            self.assertIsNone(session_links.list_sessions([root])['items'][1]['href'])

    def test_artifact_is_local_and_token_free(self):
        self.assertEqual(session_links.artifact_url('http://127.0.0.1:3010'), 'http://127.0.0.1:3010')
        for value in ['javascript:alert(1)', 'https://example.com', 'http://user:pass@127.0.0.1:3010', 'http://127.0.0.1:3010/?token=secret', 'http://127.0.0.1:99999', None]:
            self.assertIsNone(session_links.artifact_url(value))

    def test_invalid_ids_and_url_no_tokens(self):
        for url in ['https://example.com','http://127.0.0.1:3080/?token=secret','http://user:pass@localhost','file:///tmp','javascript:alert(1)']:
            with self.assertRaises(ValueError):session_links.deepseek_base(url)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'bad.json').write_text('{bad')
            (root/'evil.json').write_text(json.dumps({'agent':'codex','native_session_id':'../new?prompt=evil'}))
            self.assertEqual(session_links.list_sessions([root])['items'],[])
            self.assertTrue(session_links.list_sessions([root])['warnings'])

class Delivery(unittest.TestCase):
    def test_exactly_one_model_dispatch_for_retries(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(viewer,'STATE',Path(tmp)), patch.object(viewer,'runtime',return_value=({'rid':'room','cwd':'/'},None,{})), patch.object(viewer,'cli',return_value={'message':{'id':'sent'}}) as cli:
            rid=str(uuid.uuid4())
            viewer.send_message('@codex do work',rid)
            viewer.send_message('@codex do work',rid)
            self.assertEqual(cli.call_count,1)
            with self.assertRaises(ValueError):viewer.send_message('another message',rid)

    def test_uncertain_delivery_never_replayed(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(viewer,'STATE',Path(tmp)), patch.object(viewer,'runtime',return_value=({'rid':'room','cwd':'/'},None,{})), patch.object(viewer,'cli',side_effect=RuntimeError('network')) as cli:
            rid=str(uuid.uuid4())
            with self.assertRaises(RuntimeError):viewer.send_message('hello',rid)
            with self.assertRaisesRegex(RuntimeError,'不确定'):viewer.send_message('hello',rid)
            self.assertEqual(cli.call_count,1)

    def test_request_validation(self):
        for message,rid in [('',str(uuid.uuid4())),('hi','not-uuid'),('x'*16001,str(uuid.uuid4()))]:
            with self.assertRaises(ValueError):viewer.send_message(message,rid)

if __name__=='__main__':unittest.main()
