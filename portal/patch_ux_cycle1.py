"""Cycle-1 UX fixes: F1 tolerance dial (+F5 assumptions), F3 board triage,
F4 state-aware drawer (+F7 ARIA, F8 role field, F9 deep link, F2 record view)."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
p = ROOT / "app" / "static" / "index.html"
s = p.read_text(encoding="utf-8")
n0 = len(s)

def swap(old, new, what):
    global s
    assert old in s, f"anchor missing: {what}"
    s = s.replace(old, new, 1)

# ── F1: tolerance dial beside the guard dial ─────────────────────────────
swap('''      <div class="ctl">
        <label class="eyebrow" for="shGuard">Guard band &plusmn;</label>
        <input type="range" id="shGuard" min="0" max="0.08" step="0.005" value="0.03" style="flex:0 1 220px">
        <span class="mono" id="shGuardOut"></span>
        <button class="btn" id="shSign">Freeze policy as evidence pack</button>
        <span id="shSignOut" class="mono" style="font-size:12px"></span>
      </div>''',
'''      <div class="ctl">
        <label class="eyebrow" for="shTol">Strata tolerance</label>
        <input type="range" id="shTol" min="0.02" max="0.16" step="0.005" value="0.08"
               aria-label="strata residual-risk tolerance" style="flex:0 1 180px">
        <span class="mono" id="shTolOut"></span>
        <label class="eyebrow" for="shGuard">Guard band &plusmn;</label>
        <input type="range" id="shGuard" min="0" max="0.08" step="0.005" value="0.03"
               aria-label="guard band around the 0.80 threshold" style="flex:0 1 180px">
        <span class="mono" id="shGuardOut"></span>
        <input id="shRole" value="program lead" aria-label="signing role"
               style="width:120px;font:12px 'IBM Plex Sans',sans-serif;padding:5px 8px;background:var(--surface);color:var(--ink);border:1px solid var(--rule-2)">
        <button class="btn" id="shSign">Freeze policy as evidence pack</button>
        <span id="shSignOut" class="mono" style="font-size:12px"></span>
      </div>''',
"F1 tolerance dial + F8 role")

swap('''async function loadShadow(){
  const g=+$('shGuard').value;
  $('shGuardOut').textContent='±'+g.toFixed(3);
  const [r,tr]=await Promise.all([
    get(`/api/shadow?tolerance=0.08&guard=${g}`),
    get('/api/shadow/tradeoff?tolerance=0.08')]);''',
'''async function loadShadow(){
  const g=+$('shGuard').value, tol=+$('shTol').value;
  $('shGuardOut').textContent='±'+g.toFixed(3);
  $('shTolOut').textContent=(tol*100).toFixed(1)+'%';
  const [r,tr]=await Promise.all([
    get(`/api/shadow?tolerance=${tol}&guard=${g}`),
    get(`/api/shadow/tradeoff?tolerance=${tol}`)]);''',
"F1 loadShadow both dials")

# F5: assumptions line under the stats
swap('''  ].map(([v,k])=>`<div><span class="v" style="font-size:18px">${v}</span><span class="k">${k}</span></div>`).join('');
  $('shCurve').tBodies[0].innerHTML=''',
'''  ].map(([v,k])=>`<div><span class="v" style="font-size:18px">${v}</span><span class="k">${k}</span></div>`).join('')
  +`<div style="grid-column:1/-1;padding:8px 15px;font-size:11.5px;color:var(--ink-3)">
     FTE arithmetic: ${r.capacity.assumptions}. Auto cases skip the human step; queueing approximated by subtracting analyst minutes.</div>`;
  $('shCurve').tBodies[0].innerHTML=''',
"F5 assumptions")

swap("""function wireShadow(){
  $('shGuard').oninput=loadShadow;""",
"""function wireShadow(){
  $('shGuard').oninput=loadShadow;
  $('shTol').oninput=loadShadow;""",
"F1 wire tolerance")

swap("""      body:JSON.stringify({actor:$('actorIn')?$('actorIn').value:'andrii',
        role:'program lead',note:'shadow policy freeze',tolerance:0.08,guard:g})});""",
"""      body:JSON.stringify({actor:$('actorIn')?$('actorIn').value:'andrii',
        role:$('shRole').value||'program lead',note:'shadow policy freeze',
        tolerance:+$('shTol').value,guard:g})});""",
"F1 sign carries both dials")

# ── F3: board triage - urgency sort + quick filters ──────────────────────
swap('''      <div class="tw" style="max-height:300px;overflow-y:auto"><table id="invBoard"><thead><tr>''',
'''      <div class="ctl" id="invFilters" style="margin:10px 0 6px" role="group" aria-label="board filters"></div>
      <div class="tw" style="max-height:300px;overflow-y:auto"><table id="invBoard"><thead><tr>''',
"F3 filter slot")

swap('''const INV_TAG={received:'info',under_investigation:'warn',decided:'ok',closed:'ok'};
async function loadInvestigations(){
  const b=await get('/api/investigations');''',
'''const INV_TAG={received:'info',under_investigation:'warn',decided:'ok',closed:'ok'};
let INV_FILTER='overdue', INV_CACHE=null;

function invFiltered(items){
  const f={
    all:()=>true,
    overdue:i=>i.overdue,
    actionable:i=>['received','under_investigation','decided'].includes(i.state),
    closed:i=>i.state==='closed',
  }[INV_FILTER]||(()=>true);
  // Urgency order: overdue first (most negative clock first), then open states,
  // then by clock ascending - the triage order a Product Investigator needs,
  // replacing an 81-row manual scan (cycle-0 finding F3).
  const rank={received:0,under_investigation:1,decided:2,closed:3};
  return items.filter(f).sort((a,b)=>
    (b.overdue-a.overdue) || (a.overdue ? a.days_remaining-b.days_remaining
      : (rank[a.state]-rank[b.state] || a.days_remaining-b.days_remaining)));
}

async function loadInvestigations(){
  const b=await get('/api/investigations');
  INV_CACHE=b;''',
"F3 filter+sort machinery")

swap('''  $('invBoard').tBodies[0].innerHTML=b.items.map(i=>`''',
'''  const counts={all:b.items.length,
    overdue:b.items.filter(i=>i.overdue).length,
    actionable:b.items.filter(i=>['received','under_investigation','decided'].includes(i.state)).length,
    closed:b.items.filter(i=>i.state==='closed').length};
  $('invFilters').innerHTML=[['overdue','Overdue'],['actionable','Actionable'],
    ['closed','Closed'],['all','All']].map(([k,lab])=>
    `<button class="chipBtn btn" data-f="${k}" aria-pressed="${INV_FILTER===k}"
       style="${INV_FILTER===k?'background:var(--accent-2);color:#fff;border-color:var(--accent-2)':''}">${lab} (${counts[k]})</button>`).join('');
  $('invFilters').onclick=e=>{const btn=e.target.closest('[data-f]');
    if(btn){INV_FILTER=btn.dataset.f;loadInvestigations();}};
  $('invBoard').tBodies[0].innerHTML=invFiltered(b.items).map(i=>`''',
"F3 render filtered")

# ── F4: state-aware drawer + F2 record view + F9 deep link ───────────────
swap('''async function showInvestigation(cid){
  const f=await get(`/api/investigations/${cid}/file`);
  const d=$('invDrawer');d.style.display='block';''',
'''async function showInvestigation(cid){
  history.replaceState(null,'','#investigation='+cid);
  const state=(INV_CACHE?INV_CACHE.items.find(i=>i.complaint_id===cid):null)?.state||'received';
  if(state==='closed'){return showSealedRecord(cid);}
  const f=await get(`/api/investigations/${cid}/file`);
  const d=$('invDrawer');d.style.display='block';''',
"F4 route closed to record view")

swap('''    <div class="ctl" style="margin-top:14px" id="invDecideRow" data-cid="${cid}">
      <select id="invDecision">''',
'''    ${state!=='under_investigation'?'':''}
    <div class="ctl" style="margin-top:14px" id="invDecideRow" data-cid="${cid}">
      <select id="invDecision" aria-label="reportability decision">''',
"F7 decision aria")

swap('''      <input id="invRationale" placeholder="documented rationale (required, substantive)"''',
'''      <input id="invRationale" aria-label="decision rationale"
        placeholder="documented rationale (required, substantive)"''',
"F7 rationale aria")

# state-aware controls: decided -> only close; sealed handled above
swap('''  $('invDecide').onclick=async()=>{''',
'''  if(state==='decided'){
    $('invDecision').disabled=true;$('invRationale').disabled=true;
    $('invDecide').style.display='none';
    $('invOut').innerHTML='<span class="tag ok">decided</span> awaiting seal';
  }
  $('invDecide').onclick=async()=>{''',
"F4 decided state hides decide")

# after successful decide/seal, re-render state-aware
swap('''    $('invOut').innerHTML=res.ok
      ?`<span class="tag ok">decided</span>${j.late?' <span class="tag crit">LATE</span>':''}`
      :`<span class="tag crit">refused</span> ${j.detail}`;
    loadInvestigations();
  };
  $('invClose').onclick=async()=>{''',
'''    $('invOut').innerHTML=res.ok
      ?`<span class="tag ok">decided</span>${j.late?' <span class="tag crit">LATE</span>':''}`
      :`<span class="tag crit">refused</span> ${j.detail}`;
    if(res.ok){$('invDecision').disabled=true;$('invRationale').disabled=true;
      $('invDecide').style.display='none';}
    loadInvestigations();
  };
  $('invClose').onclick=async()=>{''',
"F4 post-decide lock")

swap('''    $('invOut').innerHTML=res.ok
      ?`<span class="tag ok">sealed</span> <span class="mono" style="font-size:11px">${j.manifest_sha256.slice(0,16)}…</span>`
      :`<span class="tag crit">refused</span> ${j.detail}`;
    loadInvestigations();
  };
}''',
'''    if(res.ok){await loadInvestigations();return showSealedRecord(cid);}
    $('invOut').innerHTML=`<span class="tag crit">refused</span> ${j.detail}`;
    loadInvestigations();
  };
}

async function showSealedRecord(cid){
  // F2: the sealed record stays reachable - hash, verification, audit trail.
  const r=await get(`/api/investigations/${cid}/record`);
  const d=$('invDrawer');d.style.display='block';
  d.innerHTML=`
    <div style="font-weight:600;margin-bottom:10px">Sealed investigation record —
      C-${String(cid).padStart(3,'0')}</div>
    <div class="statrow">
      <div><span class="v" style="font-size:14px" class="mono">${r.manifest_sha256}</span>
        <span class="k">manifest sha-256</span></div>
      <div><span class="v" style="font-size:16px">${r.verification==='verified'
          ?'<span class="tag ok">verified</span>':'<span class="tag crit">'+r.verification+'</span>'}</span>
        <span class="k">re-verified on read</span></div>
      <div><span class="v" style="font-size:16px">${r.decision.outcome.replace('_',' ')}
          ${r.decision.late?'<span class="tag crit">LATE</span>':''}</span>
        <span class="k">decision · ${r.decision.decided_by}</span></div>
    </div>
    <div class="eyebrow" style="margin:14px 0 6px">Audit trail (as sealed)</div>
    ${r.audit_trail.map(e=>`<div style="font-size:12.5px;padding:2px 0">
      <span class="mono" style="color:var(--ink-3)">${e.occurred_at.slice(0,16)}</span>
      <b>${e.actor}</b> ${e.from_state?e.from_state+' → ':''}${e.to_state}
      <span style="color:var(--ink-3)">— ${e.note}</span></div>`).join('')}
    <div class="mono" style="font-size:11px;color:var(--ink-3);margin-top:10px">${r.record_path}</div>`;
  d.scrollIntoView({behavior:'smooth',block:'nearest'});
}''',
"F2 sealed record view")

# board: closed rows get a Record button; deep link support
swap('''      <td>${i.state==='received'?`<button class="btn invOpen" style="padding:3px 9px;font-size:11px">Open</button>`
          :i.state!=='closed'?`<button class="btn invView" style="padding:3px 9px;font-size:11px">Work</button>`:''}</td>''',
'''      <td>${i.state==='received'?`<button class="btn invOpen" style="padding:3px 9px;font-size:11px">Open</button>`
          :i.state!=='closed'?`<button class="btn invView" style="padding:3px 9px;font-size:11px">Work</button>`
          :`<button class="btn invView" style="padding:3px 9px;font-size:11px">Record</button>`}</td>''',
"F2 record button")

swap('''  if(h.get('complaint')!=null){openLens('quality',false);trace(h.get('complaint'));return;}''',
'''  if(h.get('investigation')!=null){openLens('quality',false);
    (async()=>{if(!INV_CACHE)await loadInvestigations();
      showInvestigation(+h.get('investigation'));})();return;}
  if(h.get('complaint')!=null){openLens('quality',false);trace(h.get('complaint'));return;}''',
"F9 deep link")

p.write_text(s, encoding="utf-8")
print(f"patched {n0} -> {len(s)} bytes; all anchors applied")
