"""Two business-process UIs: the investigation board (Quality) and the policy
simulator (Operations). Asserted anchors."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
p = ROOT / "app" / "static" / "index.html"
s = p.read_text(encoding="utf-8")
n0 = len(s)

def swap(old, new, what):
    global s
    assert old in s, f"anchor missing: {what}"
    s = s.replace(old, new, 1)

# 1 ── investigation process board at the top of Quality ─────────────────
swap('''<section class="lens" id="l-quality">''',
'''<section class="lens" id="l-quality">
  <div class="panel"><div class="ph"><span class="eyebrow">Business process &middot; 21 CFR 820.198 / 803</span>
    <h2>Complaint investigations</h2>
    <p>received &rarr; under investigation &rarr; reportability decided (30-day clock)
    &rarr; closed with a sealed record. The software enforces the gates: no decision
    without a substantive rationale, no closing without a decision, and a decision
    after the deadline is recorded as LATE forever.</p></div>
    <div class="pb">
      <div class="statrow" id="invStats"></div>
      <div class="ctl" style="margin-top:14px">
        <label class="eyebrow" for="invActor">Investigator</label>
        <input id="invActor" type="text" value="andrii" style="width:130px;font:13px 'IBM Plex Sans',sans-serif;padding:6px 9px;background:var(--surface);color:var(--ink);border:1px solid var(--rule-2)">
        <span class="mono" id="invToday" style="font-size:12px;color:var(--ink-3)"></span>
      </div>
      <div class="tw" style="max-height:300px;overflow-y:auto"><table id="invBoard"><thead><tr>
        <th>Complaint</th><th>Type</th><th>Process state</th><th class="n">Clock</th><th></th>
      </tr></thead><tbody></tbody></table></div>
      <div id="invDrawer" style="display:none;border-top:2px solid var(--accent);margin-top:16px;padding-top:14px"></div>
    </div></div>
''',
"investigation board")

# 2 ── policy simulator panel in Operations, after the frontier panel ────
swap('''  <div class="panel"><div class="ph"><span class="eyebrow">Telemetry</span>
    <h2>Correction by coronary segment</h2>''',
'''  <div class="panel"><div class="ph"><span class="eyebrow">Business process &middot; policy decision</span>
    <h2>Shadow simulation: replay history under a policy</h2>
    <p>The program lead's actual question: adopt policy P and <b>name the patients
    whose answer changes</b>. Two dials: the strata tolerance, and a guard band
    routing anything within &plusmn;g of the 0.80 threshold to a human regardless
    of stratum.</p></div>
    <div class="pb">
      <div class="ctl">
        <label class="eyebrow" for="shGuard">Guard band &plusmn;</label>
        <input type="range" id="shGuard" min="0" max="0.08" step="0.005" value="0.03" style="flex:0 1 220px">
        <span class="mono" id="shGuardOut"></span>
        <button class="btn" id="shSign">Freeze policy as evidence pack</button>
        <span id="shSignOut" class="mono" style="font-size:12px"></span>
      </div>
      <div class="statrow" id="shStats"></div>
      <div class="g2" style="margin-top:16px">
        <div>
          <div class="eyebrow" style="margin-bottom:8px">Guard-band tradeoff (computed, not asserted)</div>
          <div class="tw"><table id="shCurve"><thead><tr>
            <th class="n">&plusmn;g</th><th class="n">Auto</th><th class="n">Hours back</th>
            <th class="n">Changed answers</th><th class="n">Would-be FN</th>
          </tr></thead><tbody></tbody></table></div>
        </div>
        <div>
          <div class="eyebrow" style="margin-bottom:8px">Harm ledger at this policy &mdash; the named cases</div>
          <div class="tw" style="max-height:240px;overflow-y:auto"><table id="shLedger"><thead><tr>
            <th>Case</th><th>Direction</th><th class="n">pre &rarr; post</th><th class="n">dist</th>
          </tr></thead><tbody></tbody></table></div>
        </div>
      </div>
      <div class="finding" id="shFraming" style="background:var(--info-bg);border-color:var(--accent-2)"></div>
    </div></div>

  <div class="panel"><div class="ph"><span class="eyebrow">Telemetry</span>
    <h2>Correction by coronary segment</h2>''',
"shadow panel")

# 3 ── renderers + wiring ────────────────────────────────────────────────
swap("function drawPlatform(){",
'''async function loadShadow(){
  const g=+$('shGuard').value;
  $('shGuardOut').textContent='±'+g.toFixed(3);
  const [r,tr]=await Promise.all([
    get(`/api/shadow?tolerance=0.08&guard=${g}`),
    get('/api/shadow/tradeoff?tolerance=0.08')]);
  $('shStats').innerHTML=[
    [num(r.volume.auto_released),'cases auto-released'],
    [pct(r.volume.auto_share,0),'of accepted volume'],
    [num(r.capacity.analyst_hours_returned)+' h','analyst time returned'],
    [r.capacity.fte_equivalent,'FTE equivalent'],
    [r.harm.changed_answers,'changed answers'],
    [r.harm.would_be_false_negatives,'would-be false negatives'],
    [r.sla.median_turnaround_before_min+' → '+r.sla.median_turnaround_after_min,'median TAT (min)'],
  ].map(([v,k])=>`<div><span class="v" style="font-size:18px">${v}</span><span class="k">${k}</span></div>`).join('');
  $('shCurve').tBodies[0].innerHTML=tr.curve.map(c=>{
    const cur=Math.abs(c.guard_band-g)<1e-9;
    return `<tr style="${cur?'background:var(--info-bg)':''}">
      <td class="n mono">${c.guard_band.toFixed(3)}</td>
      <td class="n">${num(c.auto_released)}</td>
      <td class="n">${num(c.hours_returned)}</td>
      <td class="n">${c.changed_answers}</td>
      <td class="n" style="color:var(--crit)">${c.would_be_false_negatives}</td></tr>`;}).join('');
  $('shLedger').tBodies[0].innerHTML=r.harm.ledger.length?r.harm.ledger.map(x=>`<tr>
    <td class="mono">${x.case_id}${x.has_complaint?' <span class="tag crit">complaint</span>':''}</td>
    <td><span class="tag ${x.direction==='would_be_false_negative'?'crit':'warn'}">${x.direction.replace('would_be_','').replace('_',' ')}</span></td>
    <td class="n mono" style="font-size:11.5px">${x.ffr_pre.toFixed(3)} → ${x.ffr_post.toFixed(3)}</td>
    <td class="n mono" style="font-size:11.5px">${x.distance_from_threshold.toFixed(3)}</td></tr>`).join('')
    :'<tr><td colspan="4" style="color:var(--ok)">no changed answers under this policy</td></tr>';
  $('shFraming').textContent=r.framing;
}

function wireShadow(){
  $('shGuard').oninput=loadShadow;
  $('shSign').onclick=async()=>{
    const g=+$('shGuard').value;
    const res=await fetch('/api/evidence/policy/sign',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({actor:$('actorIn')?$('actorIn').value:'andrii',
        role:'program lead',note:'shadow policy freeze',tolerance:0.08,guard:g})});
    $('shSignOut').textContent=res.ok
      ?'signed '+(await res.json()).manifest_sha256.slice(0,12)+'…'
      :'refused: '+(await res.json()).detail;
  };
}

const INV_TAG={received:'info',under_investigation:'warn',decided:'ok',closed:'ok'};
async function loadInvestigations(){
  const b=await get('/api/investigations');
  $('invToday').textContent=`today = day ${b.today} · deadline ${b.deadline_days} days`;
  $('invStats').innerHTML=[
    [b.summary.received,'received'],[b.summary.under_investigation,'investigating'],
    [b.summary.decided,'decided'],[b.summary.closed,'closed'],
    [b.summary.overdue,'OVERDUE'],
  ].map(([v,k])=>`<div><span class="v" style="font-size:20px;${k==='OVERDUE'&&v?'color:var(--crit)':''}">${v}</span><span class="k">${k}</span></div>`).join('');
  $('invBoard').tBodies[0].innerHTML=b.items.map(i=>`
    <tr data-inv="${i.complaint_id}">
      <td class="mono">C-${String(i.complaint_id).padStart(3,'0')}</td>
      <td>${i.complaint_type.replace(/_/g,' ')}</td>
      <td><span class="tag ${INV_TAG[i.state]}">${i.state.replace(/_/g,' ')}</span>
          ${i.decision?`<span class="tag ${i.decision==='mdr_reportable'?'crit':'info'}">${i.decision.replace('_',' ')}${i.decision_late?' · LATE':''}</span>`:''}</td>
      <td class="n mono" style="font-size:11.5px;${i.overdue?'color:var(--crit);font-weight:600':''}">${i.overdue?'OVERDUE ':''}${i.days_remaining}d</td>
      <td>${i.state==='received'?`<button class="btn invOpen" style="padding:3px 9px;font-size:11px">Open</button>`
          :i.state!=='closed'?`<button class="btn invView" style="padding:3px 9px;font-size:11px">Work</button>`:''}</td>
    </tr>`).join('');
}

async function showInvestigation(cid){
  const f=await get(`/api/investigations/${cid}/file`);
  const d=$('invDrawer');d.style.display='block';
  const sib=f.siblings.map(x=>`<tr><td>${x.scope}</td><td class="n">${x.cases}</td>
    <td class="n">${x.complaints}</td><td class="n">${x.p_vs_rest.toFixed(4)}</td>
    <td>${x.elevated?'<span class="tag crit">elevated</span>':'<span class="tag info">-</span>'}</td></tr>`).join('');
  d.innerHTML=`
    <div style="font-weight:600;margin-bottom:10px">Investigation file — C-${String(cid).padStart(3,'0')}
      <span class="mono" style="font-size:11px;color:var(--ink-3)">grain ${f.warehouse_grain}</span></div>
    <div class="g2">
      <div>
        <div class="eyebrow" style="margin-bottom:6px">Chronology</div>
        ${f.chronology.map(e=>`<div style="font-size:13px;padding:3px 0"><span class="mono" style="color:var(--ink-3)">day ${e.day}</span> ${e.event}</div>`).join('')}
        <div class="eyebrow" style="margin:12px 0 6px">What the correction changed</div>
        <div style="font-size:13.5px">&Delta;FFR ${f.correction.delta_ffr} — ${f.correction.meaning}
          ${f.correction.grey_zone_delivery?'<span class="tag warn">grey zone</span>':''}</div>
        <div class="eyebrow" style="margin:12px 0 6px">Device context</div>
        <div style="font-size:13.5px" class="mono">${f.device.model_version} · ${f.device.scanner} · ${f.device.detector_at_scan}
          ${f.device.release_flag.elevated?'<span class="tag crit">release cohort elevated</span>':''}</div>
      </div>
      <div>
        <div class="eyebrow" style="margin-bottom:6px">Isolated or systemic? (significance-tested)</div>
        <div class="tw"><table><thead><tr><th>Scope</th><th class="n">Cases</th><th class="n">Complaints</th><th class="n">p</th><th></th></tr></thead><tbody>${sib}</tbody></table></div>
        <div class="eyebrow" style="margin:12px 0 6px">MDR assessment (decision support)</div>
        ${f.mdr_assessment.rule_trace.map(t=>`<div style="font-size:12.5px;padding:2px 0">• ${t}</div>`).join('')}
        <div style="font-size:11.5px;color:var(--ink-3);margin-top:4px">${f.mdr_assessment.disclaimer}</div>
      </div>
    </div>
    <div class="ctl" style="margin-top:14px" id="invDecideRow" data-cid="${cid}">
      <select id="invDecision">
        <option value="mdr_reportable" ${f.mdr_assessment.suggested==='mdr_reportable'?'selected':''}>mdr_reportable</option>
        <option value="not_reportable" ${f.mdr_assessment.suggested==='not_reportable'?'selected':''}>not_reportable</option>
      </select>
      <input id="invRationale" placeholder="documented rationale (required, substantive)"
        style="flex:1 1 260px;font:13px 'IBM Plex Sans',sans-serif;padding:6px 9px;background:var(--surface);color:var(--ink);border:1px solid var(--rule-2)">
      <button class="btn" id="invDecide">Record decision</button>
      <button class="btn" id="invClose">Close &amp; seal record</button>
      <span id="invOut" style="font-size:12.5px"></span>
    </div>`;
  $('invDecide').onclick=async()=>{
    const res=await fetch(`/api/investigations/${cid}/decide`,{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({decision:$('invDecision').value,
        actor:$('invActor').value,rationale:$('invRationale').value})});
    const j=await res.json();
    $('invOut').innerHTML=res.ok
      ?`<span class="tag ok">decided</span>${j.late?' <span class="tag crit">LATE</span>':''}`
      :`<span class="tag crit">refused</span> ${j.detail}`;
    loadInvestigations();
  };
  $('invClose').onclick=async()=>{
    const res=await fetch(`/api/investigations/${cid}/close`,{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({actor:$('invActor').value})});
    const j=await res.json();
    $('invOut').innerHTML=res.ok
      ?`<span class="tag ok">sealed</span> <span class="mono" style="font-size:11px">${j.manifest_sha256.slice(0,16)}…</span>`
      :`<span class="tag crit">refused</span> ${j.detail}`;
    loadInvestigations();
  };
}

function wireInvestigations(){
  $('invBoard').onclick=async e=>{
    const row=e.target.closest('tr[data-inv]');if(!row)return;
    const cid=+row.dataset.inv;
    if(e.target.closest('.invOpen')){
      const res=await fetch(`/api/investigations/${cid}/open`,{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({actor:$('invActor').value})});
      if(res.ok){await loadInvestigations();showInvestigation(cid);}
      return;
    }
    if(e.target.closest('.invView')||e.target.closest('td')){showInvestigation(cid);}
  };
}

function drawPlatform(){''',
"process renderers")

# 4 ── boot ──────────────────────────────────────────────────────────────
swap('''    wireCrossLinks();wireActions();wireSigning();''',
'''    wireCrossLinks();wireActions();wireSigning();wireShadow();wireInvestigations();''',
"boot wiring 1")
swap('''    try{await loadActions();await loadSigned();}''',
'''    try{await loadActions();await loadSigned();
        await loadShadow();await loadInvestigations();}''',
"boot wiring 2")

p.write_text(s, encoding="utf-8")
print(f"patched {n0} -> {len(s)} bytes; all anchors applied")
