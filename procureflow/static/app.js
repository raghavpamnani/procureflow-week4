const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = n => '₹' + Number(n).toLocaleString('en-IN');
let storageKey = 'procureflow-request';
let current = null, branch = null, busy = false, approvalArmed = false;
async function api(path, options = {}) {
  const r = await fetch('/api' + path, {headers:{'Content-Type':'application/json'}, ...options});
  let data;
  try { data = await r.json(); } catch { throw new Error('The server could not complete this request. See the terminal and retry.'); }
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data));
  return data;
}
function toast(text, error = false) { $('toast').textContent = text; $('toast').className = 'toast' + (error ? ' error' : ''); clearTimeout(window.toastTimer); window.toastTimer = setTimeout(() => $('toast').classList.add('hidden'), 9000); }
async function action(fn) {
  if (busy) return;
  busy = true; document.querySelectorAll('button').forEach(b => b.disabled = true);
  try { await fn(); } catch (e) { toast(e.message, true); }
  finally { busy = false; document.querySelectorAll('button').forEach(b => b.disabled = false); if (current) syncControls(); }
}
function brief() {
  return {title:$('title').value, quantity:Number($('quantity').value), budget_inr:Number($('budget-inr').value), min_ram_gb:Number($('ram').value), min_storage_gb:Number($('storage').value), delivery_days:Number($('days').value), priority:$('priority').value, notes:$('notes').value, simulate_timeout:$('timeout').checked};
}
function fill(r) { $('title').value=r.title; $('quantity').value=r.quantity; $('budget-inr').value=r.budget_inr; $('ram').value=r.min_ram_gb; $('storage').value=r.min_storage_gb; $('days').value=r.delivery_days; $('priority').value=r.priority; $('notes').value=r.notes; $('timeout').checked=r.simulate_timeout; }
function showDesk() { $('desk-view').classList.remove('hidden'); $('orders-view').classList.add('hidden'); $('nav-desk').classList.add('active'); $('nav-orders').classList.remove('active'); }
async function refresh() {
  const [meta, requests, orders] = await Promise.all([api('/meta'), api('/requests'), api('/orders')]);
  storageKey='procureflow-request:'+meta.workspace_id;
  $('mode').textContent = meta.mode === 'demo' ? 'DEMO MODE · NO LLM' : 'LOCAL MODEL · ' + meta.model;
  $('budget').textContent = money(meta.budget.available_inr);
  $('count-active').textContent = requests.filter(r=>r.status==='awaiting_approval').length;
  $('count-orders').textContent = orders.length; $('count-tools').textContent=Object.keys(meta.tools).length;
  $('request-list').innerHTML = requests.length ? requests.map(r=>`<button class="request-link ${current?.request_id===r.id?'selected':''}" data-request="${esc(r.id)}">${esc(r.title)}<small>${esc(r.status.replaceAll('_',' '))} · ${esc(r.id.slice(0,6))}</small></button>`).join('') : '<p class="subtle">Your requests will appear here.</p>';
  $('orders').innerHTML = orders.length ? orders.map(o=>`<article class="panel"><div class="eyebrow">LOCAL SIMULATION</div><h2>${esc(o.id)}</h2><p>${esc(o.supplier)} · ${esc(o.model)}</p><strong class="price">${money(o.total_inr)}</strong><div class="facts"><span class="fact">${o.quantity} laptops</span><span class="fact">Human approved</span></div><small class="subtle">${esc(new Date(o.created).toLocaleString())}</small></article>`).join('') : '<section class="panel"><h2>No orders yet.</h2><p>Approve a recommendation to create your first simulated purchase order.</p></section>';
}
function syncControls() {
  const pending = Boolean(current?.pending?.length);
  $('approval-controls').classList.toggle('hidden', !pending);
  $('approve').disabled = busy || !pending || !current?.proposal?.selected_id;
  $('revise').disabled = busy || !pending || current.revision >= 4;
  $('retry').classList.toggle('hidden', pending || !current.next?.length);
}
async function render(s) {
  current=s; branch=null; approvalArmed=false; $('approve').textContent='Approve & create order'; revisionArmed=false; $('revise').textContent='Revise brief'; $('review-note').value=''; showDesk(); fill(s.request); localStorage.setItem(storageKey,s.request_id);
  $('download-report').href='/api/requests/'+s.request_id+'/report'; $('result').classList.remove('hidden'); $('empty-state').classList.add('hidden'); $('activity').classList.remove('hidden');
  $('workflow-status').textContent=s.status.replaceAll('_',' '); $('result-status').textContent=s.status.replaceAll('_',' ').toUpperCase();
  $('submit').innerHTML='Start a new request <span>→</span>';
  $('activity').innerHTML=(s.audit||[]).map(e=>`<div class="activity-event"><strong>${esc(e.actor)}</strong><p>${esc(e.detail)}</p>${e.note?`<p>Review: ${esc(e.note)}</p>`:''}${(e.tools||[]).map(t=>`<div class="tool-event ${t.ok?'':'failed'}">${esc(t.tool)} · attempt ${t.attempt} · ${esc(t.detail)}</div>`).join('')}</div>`).join('');
  const p=s.proposal, rec=s.recommendation;
  $('recommendation').innerHTML = p?.selected_id ? `<div class="eyebrow">RECOMMENDED OPTION</div><h3>${esc(p.supplier)} · ${esc(p.model)}</h3><strong class="price">${money(p.total_inr)}<small>GST included</small></strong><div class="facts"><span class="fact">${p.quantity} laptops</span><span class="fact">${p.delivery_days}-day delivery</span><span class="fact">${p.warranty_years}-year warranty</span></div><p>${esc(rec.rationale)}</p>${rec.tradeoffs.map(t=>`<p class="subtle">• ${esc(t)}</p>`).join('')}` : `<h3>${s.errors?.length?'Workflow needs attention':'No eligible option yet.'}</h3><p>${esc(rec?.rationale || 'A step could not finish. Check the error and retry.')}</p><p>${esc(s.errors?.join('; ') || '')}</p>`;
  $('order-receipt').innerHTML=s.order?`<div class="receipt"><small>PURCHASE ORDER CREATED</small><strong>${esc(s.order.id)}</strong><p>${money(s.order.total_inr)} · ${s.order.quantity} units</p><small>Stored once. Repeated approval cannot create a duplicate.</small></div>`:'';
  const selectedCheck=s.policy?.checks.find(c=>c.id===p?.selected_id);
  $('evidence').innerHTML = [ ['Supplier, specs & warranty', selectedCheck?.eligible ? 'All checks passed' : 'See comparison below'], ['Request budget', money(s.request.budget_inr)], ['Department available at check', money(s.policy?.budget?.available_inr || 0)], ['Human approval', s.order?'Recorded & executed':s.status==='rejected'?'Rejected':'Required before execution'], ['Active context',`${s.context_bytes||0} bytes`], ['Revision',`${s.revision||0} / 4`] ].map(([k,v])=>`<div class="evidence-row"><span>${esc(k)}</span><span>${esc(v)}</span></div>`).join('') + `<p class="evidence-note">${esc(s.policy?.policy||'')}<br>Proposal fingerprint: ${esc((s.proposal_hash||'').slice(0,16))}…${s.memory_summary?'<br>Older exchanges have been summarized; hard constraints remain in structured state.':''}</p>`;
  $('quotes').innerHTML=(s.quotes||[]).map(q=>{const c=s.policy?.checks.find(c=>c.id===q.id);return `<tr class="${q.id===p?.selected_id?'selected-quote':''}"><td>${esc(q.supplier)}<small>${esc(q.model)}${q.id===p?.selected_id?' · Recommended':''}</small></td><td>${q.ram_gb} GB / ${q.storage_gb} GB<small>${q.warranty_years}-year warranty · ${q.stock} in stock</small></td><td>${money(q.unit_inr*s.request.quantity)}</td><td>${q.delivery_days} days</td><td class="${c?.eligible?'policy-pass':'policy-fail'}">${c?.eligible?'✓ Eligible':esc(c?.reasons.join(' · ')||'Not checked')}</td></tr>`}).join('');
  $('parent-info').classList.toggle('hidden',!s.parent); $('parent-info').textContent=s.parent?'Alternative branch from request '+s.parent.request_id.slice(0,8)+'. Original request and orders are unchanged.':'';
  const h=await api('/requests/'+s.request_id+'/history');
  $('checkpoints').innerHTML=h.filter(x=>x.has_request).map(x=>`<option value="${esc(x.checkpoint_id)}">${esc(new Date(x.at).toLocaleTimeString())} · ${esc(x.next.join(', ')||x.status)} · revision ${x.revision}</option>`).join('');
  syncControls(); await refresh();
}
async function watchJob(id) {
  for (let i=0;i<600;i++) {
    const job=await api('/jobs/'+id);
    $('empty-state').classList.add('hidden'); $('activity').classList.remove('hidden');
    $('activity').innerHTML=(job.state.audit||[]).map(e=>`<div class="activity-event"><strong>${esc(e.actor)}</strong><p>${esc(e.detail)}</p></div>`).join('');
    if (!job.running) {
      if (job.error) { if(job.state.request)await render(job.state); throw new Error(job.error); }
      return job.state;
    }
    await new Promise(resolve=>setTimeout(resolve,800));
  }
  throw new Error('Still running. Your request is saved; open it from Recent requests.');
}
$('request-form').addEventListener('submit',e=>{e.preventDefault(); action(async()=>{
  $('workflow-status').textContent='Working…'; $('submit').textContent='Specialists are working…';
  toast('Comparing suppliers and checking policy. Local-model mode may take a few minutes.');
  const req=brief();
  let out;
  if (branch) {
    out=await api(`/requests/${branch.id}/fork`,{method:'POST',body:JSON.stringify({checkpoint_id:branch.checkpoint,request:req})});
  } else {
    const job=await api('/jobs',{method:'POST',body:JSON.stringify(req)});
    localStorage.setItem(storageKey,job.request_id);
    out=await watchJob(job.request_id);
  }
  await render(out); $('result').scrollIntoView({behavior:'smooth',block:'start'});
}).finally(()=>{if(!current)$('submit').innerHTML='Find the right fit <span>→</span>';});});
async function decide(kind) {
  if(kind==='approve'&&!approvalArmed){approvalArmed=true;$('approve').textContent='Confirm '+money(current.proposal.total_inr)+' order';toast('Review the supplier and total above, then click Confirm to create the simulated order.');return;}
  approvalArmed=false;
  if(kind==='revise'&&!$('request-form').reportValidity())return;
  await action(async()=>{
    const d={action:kind,proposal_hash:current.proposal_hash,note:$('review-note').value};
    if(kind==='revise')d.revision=brief();
    await render(await api(`/requests/${current.request_id}/decision`,{method:'POST',body:JSON.stringify(d)}));
    toast(kind==='approve'?'Purchase order created.':kind==='revise'?'Revised recommendation ready.':'Request rejected.');
  });
}
$('approve').onclick=()=>decide('approve'); $('reject').onclick=()=>decide('reject');
let revisionArmed=false;
$('revise').onclick=()=>{if(!revisionArmed){revisionArmed=true;$('revise').textContent='Submit revised brief';$('request-form').scrollIntoView({behavior:'smooth',block:'center'});toast('Edit the brief above, then click “Submit revised brief” below.');}else{revisionArmed=false;$('revise').textContent='Revise brief';decide('revise');}};
$('fork').onclick=()=>action(async()=>{const checkpoint=$('checkpoints').value;const snapshot=await api(`/requests/${current.request_id}/checkpoints/${encodeURIComponent(checkpoint)}`);branch={id:current.request_id,checkpoint};fill(snapshot.request);$('submit').innerHTML='Create alternative branch <span>↗</span>';$('request-form').scrollIntoView({behavior:'smooth',block:'center'});toast('Restored the brief from revision '+snapshot.revision+'. Edit it, then create an alternative branch.');});
$('retry').onclick=()=>action(async()=>render(await api(`/requests/${current.request_id}/retry`,{method:'POST'})));
$('request-list').onclick=e=>{const b=e.target.closest('[data-request]');if(b)action(async()=>render(await api('/requests/'+b.dataset.request)));};
$('nav-desk').onclick=showDesk;
$('nav-orders').onclick=()=>action(async()=>{await refresh();$('desk-view').classList.add('hidden');$('orders-view').classList.remove('hidden');$('nav-desk').classList.remove('active');$('nav-orders').classList.add('active');});
(async()=>{try{await refresh();const id=localStorage.getItem(storageKey);if(id){const job=await api('/jobs/'+id);if(job.running)await render(await watchJob(id));else if(job.state.request)await render(job.state);else toast('This request was interrupted before its first checkpoint. Start a new request.');}}catch(e){toast(e.message,true)}})();
