/* Shared browser/UXP client. Model text is rendered only through textContent. */
const $ = id => document.getElementById(id);
const labels = {Exposure:'曝光', Contrast:'对比度', Highlights:'高光', Shadows:'阴影', Whites:'白色', Blacks:'黑色', Temperature:'色温', Tint:'色调', Vibrance:'自然饱和度', Saturation:'饱和度'};
const uxp = typeof require === 'function' ? require('uxp') : null;
let endpoint = uxp ? 'http://127.0.0.1:8765' : window.location.origin;
let token = uxp ? '' : window.location.hash.slice(1);
let review = null, applied = false, busy = false, selectedEntry = null;
if (!uxp && token) window.history.replaceState(null, '', window.location.pathname);
function clear(node) { while(node.firstChild) node.removeChild(node.firstChild); }
function el(tag, text, cls) { const n=document.createElement(tag); n.textContent=text; if(cls) n.className=cls; return n; }
function message(text, error=false) { $('message').textContent=text; $('message').className=error ? 'error' : ''; }
function controls() {
  for (const id of ['read','preview','connect','pick','mode','text','nef','style','consent','refresh','closed']) $(id).disabled=busy;
  $('apply').disabled=busy || !review || !review.can_apply || applied || !$('closed').checked;
  $('save-style').disabled=busy || !review || !review.can_apply;
  $('reopen').disabled=busy || !selectedEntry;
}
function invalidate() { review=null; applied=false; $('closed').checked=false; clear($('changes')); $('changes').className='empty'; $('changes').textContent='请生成新的参数预览。'; $('explanation').textContent=''; clear($('warnings')); controls(); }
async function api(path, data={}) {
  if(!token) throw new Error('请先载入本机服务生成的 connection.json。');
  const response=await fetch(endpoint+'/api/'+path, {method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+token},body:JSON.stringify(data)});
  const payload=await response.json(); if(!response.ok) throw new Error(payload.error || '本机服务请求失败。'); return payload.result;
}
async function task(action) { if(busy) return; busy=true; controls(); try { await action(); } catch(e) { message(e.message || '操作失败，请检查本机服务。',true); } finally { busy=false; controls(); } }
async function styles() { const values=await api('styles'); clear($('style')); if(!values.length) { const opt=el('option','还没有保存的风格'); opt.value=''; $('style').appendChild(opt); } for(const s of values) { const opt=el('option',s.name); opt.value=s.name; $('style').appendChild(opt); } }
async function refreshHistory() {
  const rows=await api('history',{nef:$('nef').value.trim() || null}); clear($('history'));
  const names={planned:'已预览',applying:'待核对（应用中或中断）',applied:'已应用',needs_review:'待核对'};
  if(!rows.length) $('history').textContent='暂无记录。';
  for(const row of rows) { const n=el('div','', 'record'); n.appendChild(el('div',new Date(row.created).toLocaleString()+' · '+names[row.state],'record-title')); n.appendChild(el('div',row.review.request || row.review.mode)); n.appendChild(el('div',row.review.changes.map(c=>(labels[c.parameter] || c.parameter)+' '+c.before+' → '+c.after).join(' / '))); if(row.result && row.result.backup_path) n.appendChild(el('div','备份：'+row.result.backup_path,'backup')); if(row.result && row.result.error) n.appendChild(el('div',row.result.error,'error')); $('history').appendChild(n); }
}
async function connected() { const status=await api('status'); $('connection-state').textContent='已连接本机'; $('model').textContent=status.provider ? status.provider+' / '+status.model : '仅本地模式 · 未配置模型'; $('consent').checked=false; invalidate(); await styles(); await refreshHistory(); message('已连接。选择照片并读取参数。'); }
function connection(data) { if(!data || data.url!=='http://127.0.0.1:8765' || typeof data.token!=='string' || !/^[A-Za-z0-9_-]{40,64}$/.test(data.token)) throw new Error('连接文件无效；只支持本机 8765 端口。'); endpoint=data.url; token=data.token; }
$('connect').addEventListener('click',()=> { if(uxp) task(async()=> { const f=await uxp.storage.localFileSystem.getFileForOpening({types:['json']}); if(!f) return; connection(JSON.parse(await f.read())); await connected(); }); else $('connection-file').click(); });
$('connection-file').addEventListener('change',()=>task(async()=> { const f=$('connection-file').files[0]; if(!f) return; if(f.size>4096) throw new Error('连接文件过大。'); connection(JSON.parse(await f.text())); await connected(); $('connection-file').value=''; }));
function renderCurrent(data) { clear($('current')); for(const [name,value] of Object.entries(data.parameters)) { const row=el('div','','parameter'); row.appendChild(el('span',labels[name] || name)); row.appendChild(el('span',value===null?'未记录':String(value),'parameter-value')); $('current').appendChild(row); } }
async function read() { invalidate(); renderCurrent(await api('read',{nef:$('nef').value.trim()})); await refreshHistory(); message('参数已读取。输入需求后生成预览。'); }
$('read').addEventListener('click',()=>task(read));
$('pick').hidden=!uxp; $('reopen').hidden=!uxp;
$('pick').addEventListener('click',()=>task(async()=> { const f=await uxp.storage.localFileSystem.getFileForOpening({types:['nef']}); if(!f) return; selectedEntry=f; $('nef').value=f.nativePath; await read(); }));
$('reopen').addEventListener('click',()=>task(async()=> { if(!selectedEntry || selectedEntry.nativePath!==$('nef').value) throw new Error('请通过“选择照片”重新选择该 NEF。'); const ps=require('photoshop'); await ps.core.executeAsModal(()=>ps.app.open(selectedEntry),{commandName:'在 Camera Raw 中打开照片'}); message('已请求 Photoshop 打开所选文件，请核对 Camera Raw 参数。'); }));
for(const id of ['nef','text','mode','style','consent']) $(id).addEventListener(id==='nef'||id==='text'?'input':'change',()=> { if(id==='nef') { selectedEntry=null; clear($('current')); } invalidate(); $('consent-row').hidden=$('mode').value!=='ai'; $('style-controls').hidden=$('mode').value!=='style'; $('text').hidden=$('mode').value==='style'; $('text-label').hidden=$('mode').value==='style'; });
$('closed').addEventListener('change',controls);
$('preview').addEventListener('click',()=>task(async()=> {
  invalidate(); message('正在生成方案，请稍候…');
  review=await api('preview',{nef:$('nef').value.trim(),text:$('text').value,mode:$('mode').value,consent:$('consent').checked,style:$('style').value});
  clear($('changes')); $('changes').className='';
  for(const c of review.changes) { const row=el('div','','change'); row.appendChild(el('span',labels[c.parameter] || c.parameter)); row.appendChild(el('span',String(c.before),'before')); row.appendChild(el('strong',String(c.after))); $('changes').appendChild(row); }
  $('explanation').textContent=review.explanation || ''; clear($('warnings')); for(const warning of [...review.blocked_reasons,...review.warnings]) $('warnings').appendChild(el('div',warning)); await refreshHistory(); message(review.can_apply?'方案已就绪，请审核变化；尚未写入。':'方案不能应用，请查看原因。');
}));
$('apply').addEventListener('click',()=>task(async()=> {
  const active=review; applied=true; // Never offer a blind retry after a disconnected response.
  const result=await api('apply',{identity:active.id,digest:active.plan_sha256,closed:$('closed').checked});
  $('closed').checked=false; message(result.status==='unchanged'?'参数已经一致，未创建新备份。':'已应用并保存备份。请重开这张 NEF 检查效果；下一次调整需重新预览。'); renderCurrent(await api('read',{nef:active.nef_path})); await refreshHistory();
}));
$('save-style').addEventListener('click',()=>task(async()=> { await api('save-style',{identity:review.id,name:$('style-name').value}); await styles(); message('个人风格已保存。下次使用会根据当前参数重新预览。'); }));
$('refresh').addEventListener('click',()=>task(refreshHistory));
if(token) task(connected);
controls();
