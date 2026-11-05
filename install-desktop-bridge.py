#!/usr/bin/env python3
"""Register a local plugin in DSH's supported profile patch; preserves other settings."""
from pathlib import Path
import json, os, shutil
project=Path(__file__).resolve().parent
home=Path(os.environ.get('DSH_HOME', str(Path.home()/'.dsh')))
patch=home/'profiles/desktop/cordis.patch.yml'
if not patch.exists():
    raise SystemExit('请先正常启动一次 DeepSeek Harness 桌面客户端，再安装插件。')
backup=project/'.state/verification/desktop-cordis-before-UI01.yml'
backup.parent.mkdir(parents=True,exist_ok=True)
if not backup.exists():shutil.copy2(patch,backup)
text=patch.read_text()
if 'id: sharednet-desktop-session-link' not in text:
    text+='\n- insert:\n    - id: sharednet-desktop-session-link\n      name: '+json.dumps(str(project/'dsh-session-link/index.js'))+'\n      config:\n        mailboxFile: '+json.dumps(str(project/'.state/native-handoff.json'))+'\n'
    temp=patch.with_suffix('.ui01.tmp');temp.write_text(text);temp.replace(patch)
(project/'.state/desktop-bridge-installed').write_text('Desktop local plugin configured\n')
print('DeepSeek 桌面插件配置已安装。客户端通常会热加载；若没有连接状态，再正常重启客户端。')
