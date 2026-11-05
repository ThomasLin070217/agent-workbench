#!/usr/bin/env python3
"""Local SharedNet workbench. Credentials and CLI execution stay on the server."""
import json
from contextlib import closing
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from session_links import list_sessions

PROJECT = Path(__file__).resolve().parent
MANIFEST = Path(os.environ.get('VIEWER_MANIFEST', PROJECT / '.state/managed/runtime.json'))
CLI_BIN = os.environ.get('SHAREDNET_BIN', str(PROJECT.parent / 'sharednet-client/packages/cli/bin/sharednet.js'))
PORT = int(os.environ.get('VIEWER_PORT', '3003'))
STATE = Path(os.environ.get('VIEWER_STATE', PROJECT / '.state/viewer'))
SESSION_ROOTS = os.environ.get('NATIVE_SESSION_STATE', str(PROJECT / '.state/native-sessions')).split(os.pathsep)
DSH_URL = os.environ.get('DSH_WEB_URL', '')
HANDOFF = PROJECT / '.state/native-handoff.json'
DSH_BRIDGE = (PROJECT / '.state/desktop-bridge-installed').exists()
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.Lock()


def runtime():
    data = json.loads(MANIFEST.read_text())
    gen = Path(data['cwd'])
    return data, gen, dict(os.environ, XDG_STATE_HOME=str(gen / 'xdg/state'),
        XDG_CONFIG_HOME=str(gen / 'xdg/config'), SHAREDNET_SEAT=data['seats']['brain'])


def cli(*args):
    data, gen, env = runtime()
    r = subprocess.run(['node', CLI_BIN, *args, '--as', data['seats']['brain']],
        cwd=gen, env=env, capture_output=True, text=True, timeout=30)
    if r.returncode:
        raise RuntimeError('SharedNet 暂时不可用，请检查 Room 服务后刷新')
    return json.loads(r.stdout)


def send_message(message, request_id):
    if not isinstance(message, str) or not message.strip() or len(message) > 16000 or '\0' in message:
        raise ValueError('消息需要 1–16000 个字符')
    if str(uuid.UUID(request_id)) != request_id:
        raise ValueError('无效的请求编号')
    room, _, _ = runtime()
    identity = room.get('rid', room['cwd']) + ':' + request_id
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with LOCK, closing(sqlite3.connect(STATE / 'delivery.sqlite3')) as db:
        db.execute('CREATE TABLE IF NOT EXISTS delivery (id TEXT PRIMARY KEY, body TEXT, status TEXT, result TEXT)')
        row = db.execute('SELECT body,status,result FROM delivery WHERE id=?', (identity,)).fetchone()
        if row:
            if row[0] != message:
                raise ValueError('请求编号已被另一条消息使用')
            if row[1] == 'sent':
                return json.loads(row[2])
            raise RuntimeError('上一条发送结果不确定，请先在 Room 确认，避免重复派单')
        db.execute('INSERT INTO delivery VALUES (?,?,?,?)', (identity, message, 'pending', None))
        db.commit()
        result = cli('say', message)
        db.execute('UPDATE delivery SET status=?, result=? WHERE id=?', ('sent', json.dumps(result), identity))
        db.commit()
        return result


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def trusted_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

    def send(self, data, code=200, mime='application/json; charset=utf-8'):
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.trusted_host():
            return self.send({'error': '不允许的主机'}, 403)
        parsed = urlparse(self.path)
        assets = {'/': ('viewer.html','text/html; charset=utf-8'), '/app.js': ('app.js','text/javascript; charset=utf-8'),
                  '/style.css': ('style.css','text/css; charset=utf-8')}
        if parsed.path in assets:
            name, mime = assets[parsed.path]
            return self.send((PROJECT / name).read_bytes(), mime=mime)
        try:
            if parsed.path == '/api/bootstrap':
                return self.send({'token': TOKEN})
            if parsed.path == '/api/native-open/status':
                try:
                    return self.send(json.loads(Path(str(HANDOFF)+'.ack').read_text()))
                except (OSError, ValueError):
                    return self.send({'status': 'pending'})
            if parsed.path == '/api/sessions':
                return self.send(list_sessions(SESSION_ROOTS, DSH_URL, DSH_BRIDGE))
            if parsed.path == '/api/status':
                data, _, _ = runtime()
                return self.send({'room': data.get('rid'), 'agents': list(data.get('seats', {}))})
            if parsed.path == '/api/messages':
                count = max(1, min(100, int(parse_qs(parsed.query).get('count',['100'])[0])))
                return self.send(cli('read', '--last', str(count)))
            self.send({'error':'找不到页面'}, 404)
        except ValueError:
            self.send({'error': '参数或配置无效'}, 400)
        except (OSError, KeyError):
            self.send({'error':'尚未连接 Room，请先启动 SharedNet 服务'}, 503)
        except (RuntimeError, subprocess.TimeoutExpired):
            self.send({'error':'Room 连接中断，正在尝试重新连接'}, 503)

    def do_POST(self):
        if not self.trusted_host() or self.headers.get('Origin') != 'http://' + self.headers.get('Host','') or not secrets.compare_digest(self.headers.get('X-Workbench-Token',''), TOKEN):
            return self.send({'error':'请求来源验证失败，请刷新页面'}, 403)
        if self.path not in ('/api/messages', '/api/native-open'):
            return self.send({'error':'找不到接口'}, 404)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 65536 or self.headers.get('Content-Type','').split(';')[0] != 'application/json':
                return self.send({'error':'消息格式或长度无效'}, 400)
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError()
            if self.path == '/api/native-open':
                import time
                sid = data.get('session_id')
                items = list_sessions(SESSION_ROOTS, dsh_bridge=DSH_BRIDGE)['items']
                target = next((x for x in items if x['session_id']==sid and x['agent']=='deepseek-harness'), None)
                if not target or not target['href']:
                    return self.send({'error':'会话不存在、执行中，或桌面插件未启用'}, 409)
                request_id = str(uuid.uuid4())
                payload = {'id':request_id,'session_id':sid,'expires_at':int(time.time()*1000)+120000}
                HANDOFF.parent.mkdir(parents=True,exist_ok=True)
                temporary = HANDOFF.with_suffix('.'+request_id+'.tmp')
                temporary.write_text(json.dumps(payload))
                temporary.replace(HANDOFF)
                return self.send({'request_id':request_id,'href':'dsh://open','status':'pending'})
            result = send_message(data.get('message'), data.get('request_id', ''))
            self.send({'result': result, 'status':'sent'})
        except (ValueError, TypeError, AttributeError):
            self.send({'error':'消息或请求编号无效'}, 400)
        except (OSError, KeyError):
            self.send({'error':'Room 尚未连接'}, 503)
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            self.send({'error': str(e) if isinstance(e, RuntimeError) else '发送超时，请在 Room 确认是否送达后再继续'}, 409)


if __name__ == '__main__':
    os.umask(0o077)
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    print(f'SharedNet workbench: http://127.0.0.1:{server.server_port}', flush=True)
    server.serve_forever()
