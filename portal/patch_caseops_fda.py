"""Add the FDA-monitor view (device stats + openFDA signals) to the CaseOps UI."""
import pathlib

P = pathlib.Path(__file__).resolve().parents[1] / "caseops" / "static" / "index.html"
s = P.read_text(encoding="utf-8")
n0 = len(s)

def sub(old, new, count=1):
    global s
    assert s.count(old) == count, f"anchor x{s.count(old)}: {old[:60]!r}"
    s = s.replace(old, new, count)

sub("['forecast','Forecast'],['geometry','3D changes']];",
    "['forecast','Forecast'],['geometry','3D changes'],['fda','FDA monitor']];")

sub("<footer>CaseOps is the operational system",
    """<section class="view" id="v-fda">
  <div class="panel"><div class="ph"><h2>Statistics per device model</h2>
    <p>fleet, workload and 3D change level, per scanner model</p></div>
    <div class="tw"><table id="devStats"><thead><tr>
      <th>Model</th><th class="n">Fleet</th><th class="n">Hospitals</th><th class="n">PCD</th>
      <th class="n">Tickets</th><th class="n">Open</th><th class="n">Median min</th>
      <th class="n">Mean change %</th><th class="n">Mean disp mm</th></tr></thead><tbody></tbody></table></div></div>
  <div class="panel"><div class="ph"><h2>FDA databases &mdash; live monitoring</h2>
    <p id="fdaMeta"></p>
    <button class="btn" id="fdaRefresh" style="margin-left:auto">Refresh from openFDA</button></div>
    <div class="tw"><table id="fdaTbl"><thead><tr>
      <th>Model</th><th class="n">Our fleet</th><th class="n">MAUDE reports</th>
      <th class="n">Recalls</th><th>Top reported problem</th><th>Fetched</th></tr></thead><tbody></tbody></table></div></div>
  <div id="fdaCards"></div>
  <div class="mini" id="fdaDisc" style="margin-top:6px"></div>
</section>

<footer>CaseOps is the operational system""")

sub("summary(),board(),hospitals(),events(),forecast(),geo()]);",
    "summary(),board(),hospitals(),events(),forecast(),geo(),fdaLoad()]);")

sub("boot().catch(e=>{",
    """async function fdaLoad(){
  const stats=await get('/api/devices/stats');
  $('devStats').tBodies[0].innerHTML=stats.map(r=>`<tr>
    <td>${esc(r.make)} <b>${esc(r.model)}</b></td><td class="n">${r.fleet}</td>
    <td class="n">${r.hospitals}</td><td class="n">${r.pcd_units}</td>
    <td class="n">${num(r.tickets)}</td><td class="n">${r.open_tickets}</td>
    <td class="n">${r.median_min??'&mdash;'}</td>
    <td class="n">${r.mean_change_pct??'&mdash;'}</td>
    <td class="n">${r.mean_disp_mm??'&mdash;'}</td></tr>`).join('');
  let f;
  try{f=await get('/api/fda/signals')}catch(e){$('fdaMeta').textContent='cache unavailable';return}
  $('fdaDisc').textContent=f.disclaimer;
  if(!f.signals.length){
    $('fdaMeta').textContent='no cached signals yet — press Refresh (or run: python -m caseops.ingest fda)';
    $('fdaCards').innerHTML='';return}
  $('fdaMeta').textContent='MAUDE adverse events and recalls per model line, cached from api.fda.gov';
  $('fdaTbl').tBodies[0].innerHTML=f.signals.map(r=>{const p=r.payload;
    return `<tr><td>${esc(r.make)} <b>${esc(r.model)}</b> <span class="mini">("${esc(p.term)}")</span></td>
      <td class="n">${r.fleet}</td>
      <td class="n">${p.maude_total==null?'&mdash;':num(p.maude_total)}</td>
      <td class="n">${p.recall_total==null?'&mdash;':num(p.recall_total)}</td>
      <td class="mini">${p.top_problems[0]?esc(p.top_problems[0].problem)+' ('+num(p.top_problems[0].count)+')':'&mdash;'}</td>
      <td class="mini">${dt(r.fetched_at)}</td></tr>`}).join('');
  $('fdaCards').innerHTML=f.signals.map(r=>{const p=r.payload;
    return `<div class="panel"><div class="ph"><h2>${esc(r.make)} ${esc(r.model)}</h2>
      <p>${p.maude_total==null?'':num(p.maude_total)+' MAUDE reports'} &middot; ${p.recall_total==null?'':num(p.recall_total)+' recalls'}</p></div>
      <div class="pb"><div class="g2">
        <div><div class="eyebrow" style="margin-bottom:6px">Top reported problems (MAUDE)</div>${
          p.top_problems.length?p.top_problems.slice(0,7).map(t=>
            `<div class="mini" style="margin-bottom:4px"><span class="chip">${num(t.count)}</span> ${esc(t.problem)}</div>`).join('')
          :'<div class="mini">none reported</div>'}</div>
        <div><div class="eyebrow" style="margin-bottom:6px">Recent adverse events</div>${
          p.recent_events.length?p.recent_events.slice(0,3).map(e=>
            `<div class="mini" style="margin-bottom:7px"><span class="mono">${esc(e.date)}</span>
             <span class="tag ${e.event_type==='Injury'||e.event_type==='Death'?'crit':'warn'}">${esc(e.event_type||'?')}</span><br>
             ${esc(e.text.slice(0,180))}&hellip;</div>`).join('')
          :'<div class="mini">none</div>'}</div>
        <div><div class="eyebrow" style="margin-bottom:6px">Recalls &mdash; the news of reported problems</div>${
          p.recalls.length?p.recalls.slice(0,3).map(rc=>
            `<div class="card change" style="padding:8px 11px;margin-bottom:6px"><span class="mono mini">${esc(rc.date)}</span>
             <span class="tag ${String(rc.status).toLowerCase().includes('terminated')?'ok':'warn'}">${esc(rc.status||'')}</span><br>
             <span class="mini">${esc(rc.reason||rc.product)}</span></div>`).join('')
          :'<div class="mini">no recalls on file</div>'}</div>
      </div></div></div>`}).join('');
}
$('fdaRefresh').onclick=async()=>{
  $('fdaMeta').textContent='fetching from api.fda.gov\\u2026';
  try{const r=await post('/api/fda/refresh',{});
    $('fdaMeta').textContent=`refreshed ${r.updated}/${r.models} models (${r.errors} errors)`;
    await fdaLoad();
  }catch(e){$('fdaMeta').textContent='refresh failed: '+e.message}
};
boot().catch(e=>{""")

P.write_text(s, encoding="utf-8")
print(f"UI patched: {n0} -> {len(s)} bytes")
