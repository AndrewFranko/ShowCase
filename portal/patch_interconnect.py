"""Interconnect the portal: Ask box, hash deep-links, cross-lens navigation,
site card. Every anchor is asserted so a silent partial apply is impossible
(the &middot;-vs-· lesson from the last client patch)."""
import pathlib

p = pathlib.Path(__file__).resolve().parent.parent / "app" / "static" / "index.html"
s = p.read_text(encoding="utf-8")
n0 = len(s)

def swap(old, new, what):
    global s
    assert old in s, f"anchor missing: {what}"
    s = s.replace(old, new, 1)

# 1 ── Ask box in the header ─────────────────────────────────────────────
swap('<span class="synthetic">Synthetic data &middot; no Heartflow records</span>',
'''<span class="synthetic">Synthetic data &middot; no Heartflow records</span>
  <div class="ctl" style="margin-top:22px;max-width:680px">
    <input id="askIn" type="text" placeholder="Ask the spine — e.g. any confirmed regressions?"
      style="flex:1 1 300px;font:13.5px 'IBM Plex Sans',sans-serif;padding:9px 12px;
      background:var(--surface);color:var(--ink);border:1px solid var(--rule-2)">
    <button class="btn" id="askBtn">Ask</button>
  </div>
  <div id="askOut" class="verdict" style="display:none;max-width:680px;margin-top:10px"></div>''',
"ask box")

# 2 ── site card panel at the top of the Field lens ──────────────────────
swap('<section class="lens" id="l-field">',
'''<section class="lens" id="l-field">
  <div class="panel" id="siteCardPanel" style="display:none">
    <div class="ph"><span class="eyebrow">Site card &middot; every lens at once</span>
      <h2 id="scName">&hellip;</h2>
      <p>Conformance, hazard realisations, release exposure and complaints for one
      site &mdash; four systems today, one card here.</p></div>
    <div class="pb">
      <div class="statrow" id="scStats"></div>
      <div class="g2" style="margin-top:16px">
        <div><div class="eyebrow" style="margin-bottom:8px">Hazards realised here</div>
          <div id="scHaz"></div>
          <div class="eyebrow" style="margin:14px 0 8px">By release</div>
          <div class="tw"><table id="scRel"><thead><tr><th>Model</th>
            <th class="n">Cases</th><th class="n">Actionable</th></tr></thead>
            <tbody></tbody></table></div></div>
        <div><div class="eyebrow" style="margin-bottom:8px">Complaints from this site</div>
          <div id="scComp"></div></div>
      </div>
    </div></div>''',
"site card panel")

# 3 ── complaint filter chip slot ────────────────────────────────────────
swap('<div class="tw" style="max-height:340px;overflow-y:auto"><table id="comp">',
'''<div><div id="compFilter" style="margin-bottom:8px"></div>
      <div class="tw" style="max-height:340px;overflow-y:auto"><table id="comp">''',
"complaint filter slot")
swap('''<th>ID</th><th>Type</th><th class="n">Day</th><th>MDR</th></tr></thead><tbody></tbody></table></div>
      <div class="trace" id="trace"></div>''',
'''<th>ID</th><th>Type</th><th class="n">Day</th><th>MDR</th></tr></thead><tbody></tbody></table></div></div>
      <div class="trace" id="trace"></div>''',
"complaint table wrapper close")

# 4 ── nav → openLens with hash sync ─────────────────────────────────────
swap('''$('nav').onclick=e=>{const b=e.target.closest('button');if(!b)return;
  document.querySelectorAll('#nav button').forEach(x=>x.setAttribute('aria-selected',x===b));
  document.querySelectorAll('.lens').forEach(s=>s.classList.toggle('on',s.id==='l-'+b.dataset.k));
  redraw();};''',
'''function openLens(k,updateHash=true){
  const b=document.querySelector('#nav button[data-k="'+k+'"]');if(!b)return;
  document.querySelectorAll('#nav button').forEach(x=>x.setAttribute('aria-selected',x===b));
  document.querySelectorAll('.lens').forEach(s=>s.classList.toggle('on',s.id==='l-'+k));
  if(updateHash&&location.hash!=='#lens='+k)history.replaceState(null,'','#lens='+k);
  redraw();
}
$('nav').onclick=e=>{const b=e.target.closest('button');if(b)openLens(b.dataset.k);};

function applyHash(){
  const h=new URLSearchParams(location.hash.slice(1));
  const lens=h.get('lens');
  if(h.get('complaint')!=null){openLens('quality',false);trace(h.get('complaint'));return;}
  if(h.get('site')!=null){showSite(+h.get('site'));return;}
  if(h.get('hazard')){openLens('quality',false);loadComplaints({hazard_id:h.get('hazard')});return;}
  if(h.get('release')){openLens('quality',false);loadComplaints({model_version:h.get('release')});return;}
  if(lens)openLens(lens,false);
}
addEventListener('hashchange',applyHash);''',
"nav handler → openLens + hash router")

# 5 ── complaints become reloadable with filters ─────────────────────────
swap('''  const cs=await get('/api/quality/complaints');
  $('comp').tBodies[0].innerHTML=cs.map(c=>`<tr class="clk" data-id="${c.complaint_id}">
    <td class="mono">C-${String(c.complaint_id).padStart(3,'0')}</td>
    <td>${c.complaint_type.replace(/_/g,' ')}</td><td class="n">${c.complaint_day}</td>
    <td>${c.mdr_reportable?'<span class="tag crit">MDR</span>':'<span class="tag info">no</span>'}</td></tr>`).join('');
  $('comp').onclick=e=>{const r=e.target.closest('tr');if(r&&r.dataset.id)trace(r.dataset.id)};
  if(cs.length)trace((cs.find(c=>c.hazard_id==='H-014')||cs[0]).complaint_id);
}''',
'''  await loadComplaints();
}

async function loadComplaints(filter){
  const qs=filter?'?'+new URLSearchParams(filter):'';
  const cs=await get('/api/quality/complaints'+qs);
  $('compFilter').innerHTML=filter
    ?`<span class="tag warn">filtered: ${Object.entries(filter).map(([k,v])=>k.replace('_id','')+' = '+v).join(', ')}
       &middot; ${cs.length} complaint(s)</span>
      <button class="btn" id="clearComp" style="margin-left:8px;padding:2px 8px;font-size:10.5px">clear</button>`
    :'';
  const cb=$('clearComp');if(cb)cb.onclick=()=>loadComplaints();
  $('comp').tBodies[0].innerHTML=cs.length?cs.map(c=>`<tr class="clk" data-id="${c.complaint_id}">
    <td class="mono">C-${String(c.complaint_id).padStart(3,'0')}</td>
    <td>${c.complaint_type.replace(/_/g,' ')}</td><td class="n">${c.complaint_day}</td>
    <td>${c.mdr_reportable?'<span class="tag crit">MDR</span>':'<span class="tag info">no</span>'}</td></tr>`).join('')
    :'<tr><td colspan="4" style="color:var(--ink-3)">no complaints match this filter</td></tr>';
  $('comp').onclick=e=>{const r=e.target.closest('tr');if(r&&r.dataset.id)trace(r.dataset.id)};
  if(cs.length)trace((cs.find(c=>c.hazard_id==='H-014')||cs[0]).complaint_id);
}''',
"loadComplaints with filters")

# 6 ── hazard + engineering rows become cross-links ──────────────────────
swap("$('haz').tBodies[0].innerHTML=hz.map(h=>`<tr><td class=\"mono\">${h.hazard_id}</td>",
"$('haz').tBodies[0].innerHTML=hz.map(h=>`<tr class=\"clk\" data-hazard=\"${h.hazard_id}\"><td class=\"mono\">${h.hazard_id}</td>",
"hazard rows clickable")
swap('''  $('rel').tBodies[0].innerHTML=REL.map(r=>{
    const cls={regression:'crit',improved:'ok',unconfirmed:'warn',stable:'info'}[r.signal];
    return `<tr><td class="mono">${r.model_version}</td>''',
'''  $('rel').tBodies[0].innerHTML=REL.map(r=>{
    const cls={regression:'crit',improved:'ok',unconfirmed:'warn',stable:'info'}[r.signal];
    return `<tr class="clk" data-release="${r.model_version}"><td class="mono">${r.model_version}</td>''',
"release rows clickable")

# 7 ── conformance + site-list rows link to the site card ────────────────
swap("$('conf').tBodies[0].innerHTML=c.sites.map(s=>`<tr>",
"$('conf').tBodies[0].innerHTML=c.sites.map(s=>`<tr class=\"clk\" data-site=\"${s.site_id}\">",
"conformance rows clickable")
swap('''    return `<tr><td>${x.site_name}<div style="font-size:10.5px;color:var(--ink-3)">${x.region} &middot; ${x.site_class}</div></td>''',
'''    return `<tr class="clk" data-site="${x.site_id}"><td>${x.site_name}<div style="font-size:10.5px;color:var(--ink-3)">${x.region} &middot; ${x.site_class}</div></td>''',
"site list rows clickable")

# 8 ── trace site hop links to the card ──────────────────────────────────
swap("hop('-> Site',`${c.site_name}<br>",
"hop('-> Site',`<a href=\"#site=${c.site_id}\" style=\"color:var(--accent-2)\">${c.site_name}</a><br>",
"trace site link")

# 9 ── site card renderer + ask + delegated wiring, before boot ──────────
swap("function redraw(){",
'''async function showSite(id){
  const s=await get('/api/site/'+id);
  openLens('field',false);
  history.replaceState(null,'','#site='+id);
  $('scName').textContent=s.site_name+' — '+s.region;
  const cf=s.conformance;
  $('scStats').innerHTML=[
    [s.cases,'cases'],[pct(s.reject_rate),'reject rate'],
    [cf?pct(cf.expected_reject_rate):'—','expected from mix'],
    [cf?(cf.excess_reject_rate>=0?'+':'')+pct(cf.excess_reject_rate):'—','excess'],
    [s.median_heart_rate.toFixed(0),'median HR'],[pct(s.nitro_rate,0),'nitro'],
    [s.scanner_make+' '+s.scanner_model,'scanner'],
    [s.detector_switch_day!=null?'day '+s.detector_switch_day:'never','detector swap'],
  ].map(([v,k])=>`<div><span class="v" style="font-size:17px">${v}</span><span class="k">${k}</span></div>`).join('');
  $('scHaz').innerHTML=s.hazards.length?s.hazards.map(h=>
    `<a href="#hazard=${h.hazard_id}" class="tag crit" style="margin:0 6px 6px 0;text-decoration:none">${h.hazard_id} ×${h.matches}</a>`).join('')
    :'<span style="color:var(--ink-3);font-size:13px">none realised</span>';
  $('scRel').tBodies[0].innerHTML=s.by_release.map(r=>
    `<tr><td class="mono">${r.model_version}</td><td class="n">${r.accepted_cases}</td>
     <td class="n">${pct(r.actionable_correction_rate,2)}</td></tr>`).join('');
  $('scComp').innerHTML=s.complaints.length?s.complaints.map(c=>
    `<a href="#complaint=${c.complaint_id}" style="display:block;padding:6px 0;border-bottom:1px solid var(--rule);color:var(--ink);text-decoration:none">
      <span class="mono">C-${String(c.complaint_id).padStart(3,'0')}</span>
      &middot; ${c.complaint_type.replace(/_/g,' ')} &middot; day ${c.complaint_day}
      ${c.mdr_reportable?'<span class="tag crit">MDR</span>':''}</a>`).join('')
    :'<span style="color:var(--ink-3);font-size:13px">no complaints from this site</span>';
  const panel=$('siteCardPanel');panel.style.display='block';
  panel.scrollIntoView({behavior:'smooth',block:'start'});
}

async function doAsk(){
  const q=$('askIn').value.trim();if(!q)return;
  const r=await get('/api/ask?q='+encodeURIComponent(q));
  const out=$('askOut');out.style.display='block';
  if(r.error){
    out.innerHTML=`<b>Won't guess.</b> ${r.error}<div style="margin-top:6px;font-size:12.5px">
      Try: ${r.try.slice(0,4).map(t=>`<a href="#" class="askTry" style="color:var(--accent-2)">${t}</a>`).join(' &middot; ')}</div>`;
  }else{
    out.innerHTML=`${r.answer} ${r.open?`<a href="#" class="askOpen" data-open='${JSON.stringify(r.open)}' style="color:var(--accent-2);font-weight:600">Open &rarr;</a>`:''}
      <div style="font-size:11px;color:var(--ink-3);margin-top:6px">intent: ${r.provenance.resolved_intent}
      &middot; deterministic router over spine/metrics.py &middot; no external LLM</div>`;
  }
  out.onclick=e=>{
    const t=e.target.closest('.askTry');if(t){e.preventDefault();$('askIn').value=t.textContent;doAsk();return;}
    const o=e.target.closest('.askOpen');if(o){e.preventDefault();
      const spec=JSON.parse(o.dataset.open);
      if(spec.site!=null)showSite(spec.site);
      else if(spec.hazard){openLens('quality');loadComplaints({hazard_id:spec.hazard});}
      else openLens(spec.lens);}
  };
}

function wireCrossLinks(){
  $('askBtn').onclick=doAsk;
  $('askIn').onkeydown=e=>{if(e.key==='Enter')doAsk()};
  $('haz').onclick=e=>{const r=e.target.closest('tr[data-hazard]');if(!r)return;
    loadComplaints({hazard_id:r.dataset.hazard});
    document.querySelector('#comp').scrollIntoView({behavior:'smooth',block:'center'});};
  $('rel').onclick=e=>{const r=e.target.closest('tr[data-release]');if(!r)return;
    openLens('quality');loadComplaints({model_version:r.dataset.release});};
  const siteClick=e=>{const r=e.target.closest('tr[data-site]');if(r)showSite(+r.dataset.site);};
  $('conf').onclick=siteClick;$('sites').onclick=siteClick;
  document.body.addEventListener('click',e=>{
    const a=e.target.closest('a[href^="#site="],a[href^="#hazard="],a[href^="#complaint="]');
    if(!a)return;e.preventDefault();
    history.replaceState(null,'',a.getAttribute('href'));applyHash();});
}

function redraw(){''',
"showSite + ask + wiring")

# 10 ── boot: wire links and honour a deep link ──────────────────────────
swap('''    await frontier();await evidencePack();
    redraw();
    // Explicit readiness contract''',
'''    await frontier();await evidencePack();
    wireCrossLinks();
    if(location.hash)applyHash();else redraw();
    // Explicit readiness contract''',
"boot wiring")

p.write_text(s, encoding="utf-8")
print(f"patched {n0} -> {len(s)} bytes; all 10 anchor groups applied")
