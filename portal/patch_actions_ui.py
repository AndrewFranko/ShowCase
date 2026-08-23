"""Actions lens: work-item inbox with state machine + audit, evidence signing UI,
briefing export link. Asserted anchors throughout."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
p = ROOT / "app" / "static" / "index.html"
s = p.read_text(encoding="utf-8")
n0 = len(s)

def swap(old, new, what):
    global s
    assert old in s, f"anchor missing: {what}"
    s = s.replace(old, new, 1)

# 1 ── nav gains Actions ─────────────────────────────────────────────────
swap("""const LENSES=[['findings','Findings'],['ops','Operations'],['quality','Quality'],
              ['eng','Engineering'],['field','Field'],['evidence','Evidence'],
              ['platform','Platform']];""",
"""const LENSES=[['findings','Findings'],['ops','Operations'],['quality','Quality'],
              ['eng','Engineering'],['field','Field'],['evidence','Evidence'],
              ['actions','Actions'],['platform','Platform']];""",
"nav lenses")

# 2 ── Actions lens section, before Platform ─────────────────────────────
swap('<section class="lens" id="l-platform">',
'''<section class="lens" id="l-actions">
  <div class="note"><span class="eyebrow">The write path, and its boundary</span>
    <p>Findings become owned work here: a five-state lifecycle, a mandatory actor and
    note on every transition, and an append-only audit trail. Writes go to a
    <b>separate store</b> &mdash; the spine stays read-only, and no write route touches
    a case. Dispositioning a <i>case</i> remains forbidden; dispositioning a
    <i>finding</i> is QMS workflow.</p></div>

  <div class="panel"><div class="ph"><span class="eyebrow">Inbox</span>
    <h2>Findings requiring action</h2>
    <p>Synced from the current warehouse &mdash; idempotent, and never resurrects an
    item a person already moved.</p></div>
    <div class="pb">
      <div class="ctl">
        <label class="eyebrow" for="actorIn">Acting as</label>
        <input id="actorIn" type="text" value="andrii" style="width:140px;font:13px 'IBM Plex Sans',sans-serif;padding:6px 9px;background:var(--surface);color:var(--ink);border:1px solid var(--rule-2)">
        <button class="btn" id="syncBtn">Sync findings</button>
        <span class="mono" id="syncOut" style="font-size:12px;color:var(--ink-3)"></span>
        <a class="btn" href="/api/briefing?download=true" style="margin-left:auto;text-decoration:none">Export briefing</a>
      </div>
      <div id="actionList"></div>
    </div></div>
</section>

<section class="lens" id="l-platform">''',
"actions lens section")

# 3 ── signing UI inside the Evidence lens ───────────────────────────────
swap('''      <div class="trace" id="packTrace"></div>
    </div></div>
</section>

<section class="lens" id="l-actions">''',
'''      <div class="trace" id="packTrace"></div>
      <div style="border-top:1px solid var(--rule);margin-top:18px;padding-top:16px">
        <div class="eyebrow" style="margin-bottom:10px">Freeze &amp; sign this pack</div>
        <div class="ctl">
          <input id="signActor" placeholder="name" style="width:130px;font:13px 'IBM Plex Sans',sans-serif;padding:6px 9px;background:var(--surface);color:var(--ink);border:1px solid var(--rule-2)">
          <input id="signRole" placeholder="role" style="width:150px;font:13px 'IBM Plex Sans',sans-serif;padding:6px 9px;background:var(--surface);color:var(--ink);border:1px solid var(--rule-2)">
          <input id="signNote" placeholder="note (optional)" style="flex:1 1 160px;font:13px 'IBM Plex Sans',sans-serif;padding:6px 9px;background:var(--surface);color:var(--ink);border:1px solid var(--rule-2)">
          <button class="btn" id="signBtn">Verify &amp; sign</button>
        </div>
        <div id="signOut"></div>
        <div class="eyebrow" style="margin:16px 0 8px">Signed packs (re-verified on every read)</div>
        <div class="tw"><table id="signedTbl"><thead><tr>
          <th>Claim</th><th>Manifest</th><th>Signed by</th><th class="n">When</th><th>Verification</th>
        </tr></thead><tbody></tbody></table></div>
      </div>
    </div></div>
</section>

<section class="lens" id="l-actions">''',
"signing UI")

# 4 ── renderers + wiring ────────────────────────────────────────────────
swap("function drawPlatform(){",
'''const STATE_TAG={open:'crit',acknowledged:'warn',investigating:'info',
                 resolved:'ok',dismissed:'info'};
let TRANSITION_MAP={};

async function loadActions(){
  const d=await get('/api/actions');
  TRANSITION_MAP=d.transitions;
  const openCount=d.items.filter(i=>['open','acknowledged','investigating'].includes(i.state)).length;
  const navBtn=document.querySelector('#nav button[data-k="actions"]');
  navBtn.innerHTML='Actions'+(openCount?` <span class="tag crit" style="margin-left:4px">${openCount}</span>`:'');
  $('actionList').innerHTML=d.items.length?d.items.map(i=>`
    <div class="finding-card" data-aid="${i.action_id}" style="margin-bottom:14px">
      <div class="fc-head" style="padding:14px 18px 12px">
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
          <span class="tag ${STATE_TAG[i.state]||'info'}">${i.state}</span>
          <span class="tag info">${i.kind.replace(/_/g,' ')}</span>
          <span class="mono" style="font-size:10.5px;color:var(--ink-3)">grain ${i.grain_sha} &middot; ${i.events} event(s)</span>
        </div>
        <div style="font-weight:600;margin-top:8px">${i.title}</div>
      </div>
      <div class="fc-body" style="padding:12px 18px">
        <div class="ctl" style="margin:0">
          <select class="trSel">${(TRANSITION_MAP[i.state]||[]).map(t=>`<option>${t}</option>`).join('')}</select>
          <input class="trNote" placeholder="note (required for the audit trail)"
            style="flex:1 1 220px;font:13px 'IBM Plex Sans',sans-serif;padding:6px 9px;background:var(--surface);color:var(--ink);border:1px solid var(--rule-2)">
          <button class="btn trGo">Apply</button>
          <button class="btn trAudit">Audit trail</button>
        </div>
        <div class="trOut" style="font-size:12.5px;margin-top:8px"></div>
        <div class="trTrail trace" style="display:none;margin-top:10px"></div>
      </div>
    </div>`).join('')
    :'<div style="color:var(--ink-3)">No work items. Press "Sync findings" to derive them from the warehouse.</div>';
}

async function wireActions(){
  $('syncBtn').onclick=async()=>{
    const r=await fetch('/api/actions/sync',{method:'POST'}).then(x=>x.json());
    $('syncOut').textContent=`${r.created.length} new / ${r.total_items} total`;
    loadActions();
  };
  $('actionList').onclick=async e=>{
    const card=e.target.closest('[data-aid]');if(!card)return;
    const aid=card.dataset.aid;
    if(e.target.closest('.trGo')){
      const body={to_state:card.querySelector('.trSel').value,
                  actor:$('actorIn').value,note:card.querySelector('.trNote').value};
      const res=await fetch(`/api/actions/${aid}/transition`,
        {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const out=card.querySelector('.trOut');
      if(res.ok){loadActions();}
      else{const err=await res.json();
        out.innerHTML=`<span class="tag crit">refused</span> ${err.detail}`;}
    }
    if(e.target.closest('.trAudit')){
      const trail=(await fetch(`/api/actions/${aid}/audit`).then(x=>x.json())).events;
      const box=card.querySelector('.trTrail');
      box.style.display=box.style.display==='none'?'block':'none';
      box.innerHTML=trail.map(ev=>`<div class="hop">
        <div class="lbl">${ev.occurred_at.slice(0,16)}</div>
        <div><b>${ev.actor}</b>: ${ev.from_state?ev.from_state+' &rarr; ':''}${ev.to_state}
          <span style="color:var(--ink-3)">&mdash; ${ev.note}</span></div></div>`).join('');
    }
  };
}

async function loadSigned(){
  const rows=await get('/api/evidence/signed');
  $('signedTbl').tBodies[0].innerHTML=rows.length?rows.map(r=>`<tr>
    <td class="mono" style="font-size:11.5px">${r.claim_type}</td>
    <td class="mono" style="font-size:11.5px">${r.manifest_sha.slice(0,16)}...</td>
    <td>${r.actor} <span style="color:var(--ink-3)">(${r.role})</span></td>
    <td class="n" style="font-size:11.5px">${r.signed_at.slice(0,16)}</td>
    <td>${r.verification==='verified'?'<span class="tag ok">verified</span>'
        :`<span class="tag crit">${r.verification}</span>`}</td></tr>`).join('')
    :'<tr><td colspan="5" style="color:var(--ink-3)">nothing signed yet</td></tr>';
}

function wireSigning(){
  $('signBtn').onclick=async()=>{
    const res=await fetch(`/api/evidence/${$('claimSel').value}/sign`,
      {method:'POST',headers:{'Content-Type':'application/json'},
       body:JSON.stringify({actor:$('signActor').value,role:$('signRole').value,
                            note:$('signNote').value})});
    const out=$('signOut');
    if(res.ok){const r=await res.json();
      out.innerHTML=`<div class="finding" id="signVerdict" style="background:var(--ok-bg);border-color:var(--ok)">
        <b>Signed.</b> Pack frozen as <span class="mono" style="font-size:12px">${r.manifest_sha256.slice(0,16)}...</span></div>`;
      loadSigned();
    }else{const err=await res.json();
      out.innerHTML=`<div class="finding" id="signVerdict"><b>Refused.</b> ${err.detail}</div>`;}
  };
}

function drawPlatform(){''',
"action renderers")

# 5 ── boot ──────────────────────────────────────────────────────────────
swap('''    wireCrossLinks();
    if(location.hash)applyHash();else redraw();''',
'''    wireCrossLinks();wireActions();wireSigning();
    await loadActions();await loadSigned();
    if(location.hash)applyHash();else redraw();''',
"boot")

p.write_text(s, encoding="utf-8")
print(f"patched {n0} -> {len(s)} bytes; all anchors applied")

# ---- e2e lens-count updates -------------------------------------------------
for f, pairs in [
    (ROOT / "tests" / "e2e" / "test_deployed.py", [
        ('''    labels = ["Findings", "Operations", "Quality", "Engineering", "Field",
              "Evidence", "Platform"]''',
         '''    labels = ["Findings", "Operations", "Quality", "Engineering", "Field",
              "Evidence", "Actions", "Platform"]'''),
        ('''    for label in ["Findings", "Operations", "Quality", "Engineering", "Field",
                  "Evidence", "Platform"]:''',
         '''    for label in ["Findings", "Operations", "Quality", "Engineering", "Field",
                  "Evidence", "Actions", "Platform"]:'''),
    ]),
    (ROOT / "tests" / "e2e" / "test_lenses.py", [
        ('''LENSES = ["Findings", "Operations", "Quality", "Engineering", "Field",
          "Evidence", "Platform"]''',
         '''LENSES = ["Findings", "Operations", "Quality", "Engineering", "Field",
          "Evidence", "Actions", "Platform"]'''),
        ('''    keys = ["findings", "ops", "quality", "eng", "field", "evidence", "platform"]''',
         '''    keys = ["findings", "ops", "quality", "eng", "field", "evidence",
            "actions", "platform"]'''),
    ]),
]:
    t = f.read_text(encoding="utf-8")
    for old, new in pairs:
        assert old in t, f"{f.name}: anchor missing:\n{old[:60]}"
        t = t.replace(old, new, 1)
    f.write_text(t, encoding="utf-8")
    print(f"updated {f.name}")
