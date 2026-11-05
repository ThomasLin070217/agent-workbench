'use strict';
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function inline(text) {
  return esc(text).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,'<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
}
function markdown(text) {
  const lines = String(text ?? '').split('\n'); let out='', code=null, lang='', list=null;
  const closeList=()=>{if(list){out+=`</${list}>`;list=null;}};
  for (const line of lines) {
    if (/^\s*```/.test(line)) {
      closeList();
      if(code!==null){out+=`<div class="codebox"><div class="codehead"><span>${esc(lang || '代码')}</span><button class="copy-code" type="button">复制代码</button></div><pre><code>${esc(code.join('\n'))}</code></pre></div>`;code=null;}
      else {code=[];lang=line.trim().slice(3).trim();} continue;
    }
    if(code!==null){code.push(line);continue;}
    const heading=line.match(/^(#{1,3})\s+(.+)$/), bullet=line.match(/^\s*[-*]\s+(.+)$/), ordered=line.match(/^\s*\d+\.\s+(.+)$/);
    if(bullet || ordered){const tag=bullet?'ul':'ol';if(list!==tag){closeList();list=tag;out+=`<${tag}>`;}out+=`<li>${inline((bullet||ordered)[1])}</li>`;continue;}
    closeList();
    if(heading){const tag='h'+(heading[1].length+1);out+=`<${tag}>${inline(heading[2])}</${tag}>`;}
    else if(line.startsWith('> '))out+=`<blockquote>${inline(line.slice(2))}</blockquote>`;
    else if(line.trim())out+=`<p>${inline(line)}</p>`;
  }
  closeList(); if(code!==null)out+=`<div class="codebox"><div class="codehead"><span>${esc(lang||'代码')}</span><button class="copy-code" type="button">复制代码</button></div><pre><code>${esc(code.join('\n'))}</code></pre></div>`;
  return out;
}
if(typeof module!=='undefined')module.exports={esc,markdown};
if(typeof document!=='undefined'){
const $=id=>document.getElementById(id);
let sessions=[], selected=null, messages=new Map(), room=null, token=null, delay=3000, timer=null, polling=false, revision='', sending=false, delivery=null, visibleLimit=12;
const statusNames={completed:'已返回',running:'执行中',starting:'启动中',failed:'上次执行失败',unknown:'状态未知'};
const agentName=a=>a==='deepseek-harness'?'DeepSeek Harness':'Codex';
function notice(text){$('notice').textContent=text;}
async function api(path,options){const response=await fetch(path,{...options,signal:AbortSignal.timeout(35000)});const data=await response.json();if(!response.ok)throw new Error(data.error||'连接失败');return data;}
function renderSessions(){
  const query=$('search').value.trim().toLowerCase();
  $('session-count').textContent=sessions.length;
  const visible=sessions.filter(s=>[s.agent,s.session_id,s.workspace,...s.tasks].join(' ').toLowerCase().includes(query));
  $('sessions').innerHTML=visible.length?visible.map(s=>`<button class="session ${selected===s.key?'selected':''}" data-session="${esc(s.key)}"><strong>${esc(s.tasks[0] || '原生会话')}</strong><div class="row"><span>${agentName(s.agent)}</span><span>${statusNames[s.status]||'状态未知'}</span></div><small>${esc(s.session_id)}</small></button>`).join(''):`<p class="hint">${query?'没有匹配的会话':'还没有可接续的会话。Agent 完成首次原生调用后会显示在这里。'}</p>`;
  const s=sessions.find(s=>s.key===selected);
  $('room-nav').classList.toggle('selected',!s);
  $('session-detail').hidden=!s;
  if(!s){$('title').textContent='协作 Room';$('subtitle').textContent='在这里协作，在原生应用中继续';return;}
  $('title').textContent=agentName(s.agent);$('subtitle').textContent=s.tasks.join(' · ')||'原生会话';
  const allowed=s.href && (s.agent==='codex'?/^codex:\/\/threads\/[0-9a-f-]+$/.test(s.href):s.href==='dsh://open');
  $('session-detail').innerHTML=`<div class="detail-top"><div><h2>继续这段对话</h2><p>打开已有会话，保留上下文。下方仍是 Room 协作消息。</p></div>${allowed?`<a class="open-native" href="${esc(s.href)}" ${s.agent==='codex'?'':`data-desktop-session="${esc(s.session_id)}"`}>在 ${s.agent==='codex'?'Codex':'DeepSeek 桌面端'}中打开</a>`:''}</div><div class="detail-meta"><code>${esc(s.session_id)}</code><button class="copy-id" data-copy="${esc(s.session_id)}">复制 ID</button></div>${s.open_reason?`<p class="detail-warning">${esc(s.open_reason)}</p>`:''}`;
}
function renderMessages(){
  const all=[...messages.values()].sort((a,b)=>(a.sequence||0)-(b.sequence||0));
  const items=all.slice(-visibleLimit);
  const next=JSON.stringify(items);if(revision===next)return;const first=!revision;revision=next;
  const log=$('log'), bottom=first||log.scrollHeight-log.scrollTop-log.clientHeight<100, old=log.scrollTop;
  if(!items.length)return;
  log.innerHTML=(all.length>visibleLimit?'<button class="older-messages" type="button">查看更早的 Room 消息</button>':'')+items.map(m=>{const name=m.sender?.name||'?';const date=new Date(m.created_at);return `<article class="msg ${name==='brain'?'user':''}"><div class="meta"><strong>${esc(name==='brain'?'Room 发起人':name)}</strong><time>${Number.isNaN(date.getTime())?'':esc(date.toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'}))}</time><span>#${esc(m.sequence)}</span></div><div>${String(m.content||'').length>600?`<p>${esc(String(m.content).slice(0,160))}…</p><details><summary>展开完整长消息</summary>${markdown(m.content)}</details>`:markdown(m.content)}</div></article>`;}).join('');
  if(bottom){log.scrollTop=log.scrollHeight;requestAnimationFrame(()=>{log.scrollTop=log.scrollHeight;});$('new-messages').hidden=true;}else{log.scrollTop=old;$('new-messages').hidden=false;}
}
async function poll(){
  if(polling)return;polling=true;clearTimeout(timer);
  try{
    const results=await Promise.allSettled([api('/api/status'),api('/api/messages'),api('/api/sessions')]);
    if(results[2].status==='fulfilled'){sessions=results[2].value.items;renderSessions();}
    if(results[0].status==='rejected')throw results[0].reason;
    const status=results[0].value;
    if(room!==status.room){room=status.room;messages.clear();revision='';$('log').innerHTML='<div class="empty"><h2>Room 已连接</h2><p>还没有消息，发出第一条任务吧。</p></div>';}
    $('room-label').textContent=room||'Room 未启动';
    if(results[1].status==='rejected')throw results[1].reason;
    const items=results[1].value.items||[];
    for(const m of items)if(m.id)messages.set(m.id,m);
    renderMessages();delay=3000;$('connection').textContent='Room 已连接';$('connection').classList.remove('error');
  }catch(error){$('connection').textContent='连接中断 · 自动重连';$('connection').classList.add('error');delay=Math.min(delay*2,30000);}
  finally{polling=false;timer=setTimeout(poll,delay);}
}

document.addEventListener('click', async e=>{
 const link=e.target.closest('[data-desktop-session]');if(!link)return;e.preventDefault();
 try{
  if(!token)token=(await api('/api/bootstrap')).token;
  const request=await api('/api/native-open',{method:'POST',headers:{'Content-Type':'application/json','X-Workbench-Token':token},body:JSON.stringify({session_id:link.dataset.desktopSession})});
  notice('正在唤起 DeepSeek 本地客户端，并定位原会话…');
  window.location.href=request.href;
  let attempts=0;
  const check=async()=>{try{const ack=await api('/api/native-open/status');if(ack.id===request.request_id){notice(ack.status==='selected'?'DeepSeek 桌面端已选中原会话，可在客户端继续聊天。':'桌面会话定位失败，请在客户端检查会话是否可用。');return;}}catch{}
   if(++attempts<30)setTimeout(check,2000);else notice('尚未收到桌面客户端确认。请打开 DeepSeek Harness；首次安装插件可能需要重新启动客户端。');};
  setTimeout(check,1000);
 }catch(error){notice(error.message);}
});

$('sessions').addEventListener('click',e=>{const el=e.target.closest('[data-session]');if(el){selected=el.dataset.session;renderSessions();document.body.classList.remove('nav-open');}});
$('room-nav').onclick=()=>{selected=null;renderSessions();document.body.classList.remove('nav-open');};
$('search').oninput=renderSessions;$('refresh').onclick=poll;
$('menu').onclick=()=>document.body.classList.add('nav-open');$('close-nav').onclick=()=>document.body.classList.remove('nav-open');
document.addEventListener('keydown',e=>{if(e.key==='Escape')document.body.classList.remove('nav-open');});
document.addEventListener('click',async e=>{const copy=e.target.closest('.copy-code,.copy-id');if(!copy)return;const text=copy.dataset.copy||copy.closest('.codebox').querySelector('code').textContent;try{await navigator.clipboard.writeText(text);copy.textContent='已复制';}catch{notice('无法自动复制，请选中文字后复制。');}});
$('log').addEventListener('click',e=>{if(e.target.closest('.older-messages')){visibleLimit+=20;revision='';renderMessages();$('log').scrollTop=0;}});
$('log').addEventListener('scroll',()=>{if($('log').scrollHeight-$('log').scrollTop-$('log').clientHeight<100)$('new-messages').hidden=true;});
$('new-messages').onclick=()=>{$('log').scrollTop=$('log').scrollHeight;$('new-messages').hidden=true;};
$('message').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();$('composer').requestSubmit();}});
$('composer').onsubmit=async e=>{
  e.preventDefault();if(sending)return;const draft=$('message').value.trim();if(!draft)return;
  const agent=$('agent').value;const body=agent&&!draft.includes('@'+agent)?'@'+agent+' '+draft:draft;
  if(!delivery||delivery.message!==body)delivery={request_id:crypto.randomUUID(),message:body};
  sending=true;$('send').disabled=true;notice('正在发送到 Room…');
  try{if(!token)token=(await api('/api/bootstrap')).token;
    await api('/api/messages',{method:'POST',headers:{'Content-Type':'application/json','X-Workbench-Token':token},body:JSON.stringify(delivery)});
    if($('message').value.trim()===draft)$('message').value='';delivery=null;notice('已送达 Room，等待 Agent 回复。');await poll();
  }catch(error){notice(error.message+'。输入内容已保留。');}
  finally{sending=false;$('send').disabled=false;}
};
poll();
}
