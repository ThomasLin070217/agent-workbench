#!/usr/bin/env python3
"""Wake contract: only a complete, nonempty answer on stdout; failures on stderr."""
import json
import math
import os
from pathlib import Path
import signal
import re
import shlex
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request


def execute(argv, timeout, prompt=None):
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        child = subprocess.Popen(argv, stdin=subprocess.PIPE if prompt is not None else subprocess.DEVNULL,
                                 stdout=out, stderr=err, start_new_session=True, text=True)
        try:
            child.communicate(input=prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            raise RuntimeError(f'{argv[0]} timed out after {timeout:g}s')
        if child.returncode:
            # Avoid relaying credential-bearing diagnostics from harnesses.
            raise RuntimeError(f'{argv[0]} failed (exit {child.returncode}); check CLI login, permissions and sandbox restrictions')
        if out.tell() > 2 * 1024 * 1024:
            raise RuntimeError('Model output exceeds 2 MiB')
        out.seek(0)
        return out.read().decode('utf-8')


def main():
    data = json.load(sys.stdin)
    prompt = data.get('prompt') if isinstance(data, dict) else None
    if not isinstance(prompt, str) or not prompt.strip() or '\0' in prompt:
        raise ValueError('wake.prompt must be a nonempty string without NUL')
    timeout = float(os.environ.get('ADAPTER_TIMEOUT', '180'))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('ADAPTER_TIMEOUT must be positive and finite')
    os.chdir(os.environ.get('AGENT_WORKDIR', str(Path(__file__).resolve().parents[1])))
    kind = sys.argv[1]
    if kind == 'codex':
        with tempfile.TemporaryDirectory(prefix='my-agents-codex-') as tmp:
            answer = Path(tmp) / 'answer.txt'
            execute(['codex', 'exec', '-s', 'read-only', '--skip-git-repo-check', '--output-last-message', str(answer), '-'], timeout, prompt)
            if answer.exists() and answer.stat().st_size > 2 * 1024 * 1024:
                raise RuntimeError('Model answer exceeds 2 MiB')
            reply = answer.read_text() if answer.exists() else ''
    elif kind == 'claude':
        reply = execute(['claude', '-p', '--output-format', 'text'], timeout, prompt)
    elif kind == 'deepseek-harness':
        # Some headless versions do not load the user's credential file.
        # Preserve explicit keys; accept a simple YAML scalar as a fallback.
        if not os.environ.get('DEEPSEEK_API_KEY'):
            credentials = Path(os.environ.get('DSH_CREDENTIALS_FILE', str(Path.home() / '.dsh/.credentials.yaml')))
            if credentials.is_file():
                match = re.search(r'^\s*DEEPSEEK_API_KEY:\s*(.+)$', credentials.read_text(), re.M)
                if match:
                    values = shlex.split(match[1], comments=True)
                    if len(values) == 1 and values[0] not in ('null', '~', '|', '>'):
                        os.environ['DEEPSEEK_API_KEY'] = values[0]
        # Prefix whitespace so a leading dash in user content cannot become a flag.
        reply = execute(['dsh', 'headless', ' ' + prompt], timeout)
    else:
        provider = 'OPENAI' if kind == 'chatgpt' else 'DEEPSEEK'
        key = os.environ.get(provider + '_API_KEY')
        if not key:
            raise ValueError(provider + '_API_KEY is missing')
        url = 'https://api.openai.com/v1/chat/completions' if kind == 'chatgpt' else 'https://api.deepseek.com/chat/completions'
        messages = [{'role': 'user', 'content': prompt}]
        if kind == 'chatgpt':
            messages.insert(0, {'role': 'system', 'content': '你是团队的大脑。把任务拆成步骤，用 @名字 指派给对应 worker，回复简洁、可执行。'})
        payload = {'model': os.environ.get(provider + '_MODEL', 'gpt-4o' if kind == 'chatgpt' else 'deepseek-chat'), 'messages': messages}
        request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read(2 * 1024 * 1024 + 1)
                if len(body) > 2 * 1024 * 1024:
                    raise RuntimeError('API response exceeds 2 MiB')
                reply = json.loads(body)['choices'][0]['message']['content']
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'{provider} API HTTP {error.code}') from None
    if not isinstance(reply, str) or not reply.strip():
        raise RuntimeError('Model returned an empty response')
    print(reply.strip())


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Adapter failed: {error}', file=sys.stderr)
        sys.exit(1)
