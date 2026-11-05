#!/usr/bin/env python3
"""Explicit local task dispatch for the approved pilot; not a general scheduler."""
import argparse
import importlib.util
import json
import os
import re
from pathlib import Path
import time
import uuid

import viewer

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--agent', choices=['codex', 'deepseek-harness'], required=True)
    parser.add_argument('--task', required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--prompt', type=Path, required=True)
    parser.add_argument('--turn', type=int, required=True)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    if not args.workspace.is_dir() or not re.fullmatch(r'TASK-[A-Za-z0-9-]+', args.task) or args.turn < 1:
        parser.error('Existing workspace, TASK- identifier and positive turn required')
    if args.write and args.agent != 'codex':
        parser.error('Only the developer Codex task can opt into workspace writes')
    manifest = json.loads(viewer.MANIFEST.read_text())
    seat = 'codex' if args.agent == 'codex' else 'deepseek'
    run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{manifest['rid']}:{args.task}:{args.agent}:{args.turn}"))
    store = ROOT / '.state' / 'pilot' / run_id
    store.mkdir(parents=True, exist_ok=True, mode=0o700)
    def publish(stage, content):
        payload = {'task': args.task, 'agent': args.agent, 'turn': args.turn,
                   'workspace': str(args.workspace.resolve()), 'stage': stage,
                   'time': time.time(), 'content': content}
        (store / (stage + '.json')).write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        try:
            # Quoted reports must not accidentally wake a fixed Room seat.
            forwarded = content.replace('@', '@\u200b')
            viewer.send_message(f'[{args.task}][{stage}] {args.agent}\n{forwarded}'[:15500],
                                str(uuid.uuid5(uuid.UUID(run_id), stage)))
        except Exception as error:
            (store / (stage + '-delivery-error.txt')).write_text(str(error))
            print(f'Room delivery pending ({stage}); local record retained', flush=True)
    spec = importlib.util.spec_from_file_location('pilot_native_runner', ROOT / 'adapters/native_runner.py')
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    os.environ['AGENT_WORKDIR'] = str(args.workspace.resolve())
    os.environ['ADAPTER_TIMEOUT'] = '900'
    os.environ['CODEX_TASK_SANDBOX'] = 'workspace-write' if args.write else 'read-only'
    os.environ['NATIVE_SESSION_STATE'] = str(ROOT / '.state/native-sessions')
    publish('started', f'已批准的股票复核试点。工作副本：{args.workspace.name}。本回合结束不代表任务通过验收。')
    try:
        reply = native.run(args.agent, {
            'room_id': manifest['rid'], 'member_id': manifest['seats'][seat],
            'task_id': args.task, 'project_id': 'stock-double-check',
            'task_title': '股票买卖前复核', 'through': args.turn,
            'prompt': args.prompt.read_text(),
        })
        publish('turn_returned', reply)
        print(json.dumps({'task': args.task, 'status': 'turn_returned', 'record': str(store)}, ensure_ascii=False), flush=True)
    except Exception as error:
        publish('failed', str(error))
        raise


if __name__ == '__main__':
    main()
