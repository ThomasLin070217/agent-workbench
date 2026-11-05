"""Validated links to existing native sessions; never creates or forks a session."""
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse, quote

UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'

def deepseek_base(value):
    p = urlparse(value)
    if p.scheme != 'http' or p.hostname not in ('127.0.0.1', 'localhost', '::1') or p.username or p.password or p.query or p.fragment or p.path not in ('', '/'):
        raise ValueError('DSH_WEB_URL must be a local HTTP origin without tokens or a path')
    return value.rstrip('/') + '/'

def artifact_url(value):
    if not isinstance(value, str):
        return None
    try:
        p = urlparse(value)
        if p.scheme == 'http' and p.hostname == '127.0.0.1' and p.port and 0 < p.port < 65536 and not p.username and not p.password and p.path in ('', '/') and not p.query and not p.fragment:
            return value
    except ValueError:
        pass
    return None

def list_sessions(roots, dsh_url='', dsh_bridge=False):
    items, warnings, seen = [], [], set()
    base = ''  # Desktop handoff; no browser Web UI target.
    for root in roots:
        for path in sorted(Path(root).glob('*.json')):
            try:
                record = json.loads(path.read_text())
                agent, sid = record.get('agent'), record.get('native_session_id', '')
                if agent not in ('codex', 'deepseek-harness'):
                    continue
                pattern = UUID if agent == 'codex' else 'session-' + UUID
                if not isinstance(sid, str) or not re.fullmatch(pattern, sid):
                    warnings.append('有会话尚未取得有效的原生 ID')
                    continue
                identity = (agent, sid)
                if identity in seen:
                    continue
                seen.add(identity)
                busy = record.get('status') in ('starting', 'running')
                href = 'codex://threads/' + sid if agent == 'codex' else ('dsh://open' if dsh_bridge else None)
                reason = 'Agent 正在执行，结束后再打开继续聊' if busy else (None if href else 'DeepSeek 桌面客户端需要先启用会话接续插件')
                items.append({
                    'key': agent + ':' + sid, 'agent': agent, 'session_id': sid,
                    'tasks': [str(t) for t in record.get('tasks', [])] if isinstance(record.get('tasks', []), list) else [], 'workspace': record.get('workspace', ''),
                    'room_id': record.get('room_id'), 'status': record.get('status', 'unknown'),
                    'project_id': record.get('project_id'), 'task_title': record.get('task_title'),
                    'artifact_url': artifact_url(record.get('artifact_url')), 'workflow_status': record.get('workflow_status'),
                    'updated_at': float(record.get('updated_at', 0)), 'href': None if busy else href,
                    'open_reason': reason, 'link_basis': 'official' if agent == 'codex' else 'project-plugin',
                })
            except (ValueError, OSError, TypeError, AttributeError):
                warnings.append('一个会话索引无法读取；其他会话不受影响')
    return {'items': sorted(items, key=lambda x: x['updated_at'], reverse=True), 'warnings': sorted(set(warnings))}
