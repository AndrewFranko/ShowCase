"""Per-device corrections series + per-clinic statistics.

API: device_detail gains a weekly corrections series (count, minutes, mean
binary change level); /api/hospitals gains per-clinic workload/change stats;
hospital_detail gains the same weekly series scoped to the clinic.
UI: a chart in the device drawer and the hospital drawer; two new columns on
the Hospitals table."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]

def sub(path, old, new, count=1):
    p = ROOT / path
    s = p.read_text(encoding="utf-8")
    assert s.count(old) == count, f"{path}: anchor x{s.count(old)}: {old[:60]!r}"
    p.write_text(s.replace(old, new, count), encoding="utf-8")

WEEKLY_SQL = '''
        SELECT date_trunc('week', t.resolved_at)::date AS week,
               count(*)                                AS corrections,
               sum(t.actual_min)::int                  AS minutes,
               round(avg(g.blocks_changed_pct)::numeric, 1) AS mean_change_pct
        FROM ticket t
        LEFT JOIN geometry_delta g USING (ticket_id)
        WHERE t.{scope} = %s AND t.status = 'resolved'
        GROUP BY 1 ORDER BY 1'''

# ------------------------------------------------------------------ app.py
sub("caseops/app.py",
    '''    fda_rows = q(con, "SELECT payload, fetched_at FROM fda_signal WHERE make = %s AND model = %s",
                 [d["make"], d["model"]])''',
    '''    d["weekly"] = q(con, """''' + WEEKLY_SQL.format(scope="device_id") + '''""",
                    [device_id])
    fda_rows = q(con, "SELECT payload, fetched_at FROM fda_signal WHERE make = %s AND model = %s",
                 [d["make"], d["model"]])''')

sub("caseops/app.py",
    '''        SELECT h.*, count(DISTINCT d.device_id) AS devices,
               count(DISTINCT t.ticket_id) FILTER (WHERE t.status <> 'resolved') AS open_tickets,
               count(DISTINCT i.incident_id) FILTER (WHERE i.status = 'open')    AS open_incidents,
               max(c.occurred_at)                                                AS last_change
        FROM hospital h
        LEFT JOIN device d USING (hospital_id)
        LEFT JOIN ticket t USING (hospital_id)
        LEFT JOIN incident i ON i.hospital_id = h.hospital_id
        LEFT JOIN hospital_change c ON c.hospital_id = h.hospital_id
        GROUP BY h.hospital_id ORDER BY open_tickets DESC, h.name""")''',
    '''        SELECT h.*, count(DISTINCT d.device_id) AS devices,
               count(DISTINCT t.ticket_id) FILTER (WHERE t.status <> 'resolved') AS open_tickets,
               count(DISTINCT t.ticket_id) FILTER (WHERE t.status = 'resolved')  AS resolved_tickets,
               round(percentile_cont(0.5) WITHIN GROUP (ORDER BY t.actual_min)::numeric, 0)
                                                                                 AS median_min,
               round(avg(g.blocks_changed_pct)::numeric, 1)                      AS mean_change_pct,
               count(DISTINCT i.incident_id) FILTER (WHERE i.status = 'open')    AS open_incidents,
               max(c.occurred_at)                                                AS last_change
        FROM hospital h
        LEFT JOIN device d USING (hospital_id)
        LEFT JOIN ticket t USING (hospital_id)
        LEFT JOIN geometry_delta g ON g.ticket_id = t.ticket_id
        LEFT JOIN incident i ON i.hospital_id = h.hospital_id
        LEFT JOIN hospital_change c ON c.hospital_id = h.hospital_id
        GROUP BY h.hospital_id ORDER BY open_tickets DESC, h.name""")''')

sub("caseops/app.py",
    '''    h["open_tickets"] = q(con, """
        SELECT t.*, a.name AS analyst FROM ticket t''',
    '''    h["weekly"] = q(con, """''' + WEEKLY_SQL.format(scope="hospital_id") + '''""",
                    [hospital_id])
    h["open_tickets"] = q(con, """
        SELECT t.*, a.name AS analyst FROM ticket t''')

# ------------------------------------------------------------------ UI
UI = "caseops/static/index.html"

# hospitals table: two stat columns
sub(UI,
    '''    <div class="tw"><table id="hosp"><thead><tr>
      <th>Hospital</th><th>Region</th><th class="n">Devices</th>
      <th class="n">Open tickets</th><th class="n">Incidents</th><th>Last change</th></tr></thead><tbody></tbody></table></div></div>''',
    '''    <div class="tw"><table id="hosp"><thead><tr>
      <th>Hospital</th><th>Region</th><th class="n">Devices</th>
      <th class="n">Open</th><th class="n">Resolved</th><th class="n">Med min</th>
      <th class="n">Chg %</th><th class="n">Incidents</th><th>Last change</th></tr></thead><tbody></tbody></table></div></div>''')

sub(UI,
    '''  $('hosp').tBodies[0].innerHTML=HOSPITALS.map(h=>`<tr class="clk" data-h="${h.hospital_id}">
    <td><b>${esc(h.name)}</b></td><td>${h.region}</td>
    <td class="n">${h.devices}</td><td class="n">${h.open_tickets}</td>
    <td class="n">${h.open_incidents?`<span class="tag crit">${h.open_incidents}</span>`:'0'}</td>
    <td class="mini">${dt(h.last_change)}</td></tr>`).join('');''',
    '''  $('hosp').tBodies[0].innerHTML=HOSPITALS.map(h=>`<tr class="clk" data-h="${h.hospital_id}">
    <td><b>${esc(h.name)}</b></td><td>${h.region}</td>
    <td class="n">${h.devices}</td><td class="n">${h.open_tickets}</td>
    <td class="n">${num(h.resolved_tickets)}</td><td class="n">${h.median_min??'-'}</td>
    <td class="n">${h.mean_change_pct??'-'}</td>
    <td class="n">${h.open_incidents?`<span class="tag crit">${h.open_incidents}</span>`:'0'}</td>
    <td class="mini">${dt(h.last_change)}</td></tr>`).join('');''')

# device drawer: corrections chart section + draw call
sub(UI,
    '''    <div class="sect"><span class="eyebrow">Cases on this device (${d.open_count} open)</span>''',
    '''    <div class="sect"><span class="eyebrow">Corrections per week &middot; bars = resolved, line = binary change %</span>
      <canvas id="dvChart" height="120"></canvas></div>
    <div class="sect"><span class="eyebrow">Cases on this device (${d.open_count} open)</span>''')

sub(UI,
    '''    <div class="sect"><span class="eyebrow">Vendor page (${esc(d.make)})</span>
      ${d.vendor_page?`${d.vendor_page.reachable?(d.vendor_page.changed?'<span class="tag warn">changed since last check</span>':'<span class="tag ok">unchanged</span>'):'<span class="tag crit">unreachable</span>'}
        <span class="mini"> &middot; checked ${dt(d.vendor_page.fetched_at)}</span>`
      :'<span class="mini">not checked yet</span>'}</div>`);
}''',
    '''    <div class="sect"><span class="eyebrow">Vendor page (${esc(d.make)})</span>
      ${d.vendor_page?`${d.vendor_page.reachable?(d.vendor_page.changed?'<span class="tag warn">changed since last check</span>':'<span class="tag ok">unchanged</span>'):'<span class="tag crit">unreachable</span>'}
        <span class="mini"> &middot; checked ${dt(d.vendor_page.fetched_at)}</span>`
      :'<span class="mini">not checked yet</span>'}</div>`);
  drawWeekly('dvChart',d.weekly);
}''')

# hospital drawer: stats chips + chart
sub(UI,
    '''  openDrawer(esc(h.name),`
    <div class="mini" style="margin-bottom:10px">${h.region} &middot; ${h.site_class}</div>''',
    '''  const hs=HOSPITALS.find(x=>x.hospital_id===h.hospital_id)||{};
  openDrawer(esc(h.name),`
    <div class="mini" style="margin-bottom:10px">${h.region} &middot; ${h.site_class}</div>
    <div class="sect"><span class="eyebrow">Clinic statistics</span>
      <div class="tix">
        <span class="chip">${num(hs.resolved_tickets??0)} resolved</span>
        <span class="chip">${hs.open_tickets??0} open</span>
        <span class="chip">median ${hs.median_min??'-'} min</span>
        <span class="chip">change ${hs.mean_change_pct??'-'}%</span>
        <span class="chip">${hs.open_incidents??0} open incident(s)</span>
      </div></div>
    <div class="sect"><span class="eyebrow">Corrections per week &middot; bars = resolved, line = binary change %</span>
      <canvas id="hoChart" height="120"></canvas></div>''')

sub(UI,
    '''      ${h.incidents.length?h.incidents.slice(0,5).map(i=>`<div class="mini"><span class="mono">${dt(i.reported_at)}</span> <span class="tag ${i.severity>2?'crit':'warn'}">S${i.severity}</span> ${esc(i.kind)} (${i.status})</div>`).join(''):'<div class="mini">none</div>'}</div>`);
});''',
    '''      ${h.incidents.length?h.incidents.slice(0,5).map(i=>`<div class="mini"><span class="mono">${dt(i.reported_at)}</span> <span class="tag ${i.severity>2?'crit':'warn'}">S${i.severity}</span> ${esc(i.kind)} (${i.status})</div>`).join(''):'<div class="mini">none</div>'}</div>`);
  drawWeekly('hoChart',h.weekly);
});''')

# shared weekly chart renderer
sub(UI,
    '''/* ------------------------------------------------ state + boot */''',
    '''function drawWeekly(id,weekly){
  const cv=$(id);if(!cv)return;
  if(!weekly||!weekly.length){cv.replaceWith(Object.assign(document.createElement('div'),
    {className:'mini',textContent:'no resolved corrections yet'}));return}
  const w=cv.clientWidth||400,dpr=devicePixelRatio||1,h=120;
  cv.width=w*dpr;cv.height=h*dpr;cv.style.height=h+'px';
  const x=cv.getContext('2d');x.setTransform(dpr,0,0,dpr,0,0);x.clearRect(0,0,w,h);
  x.font='9px "IBM Plex Mono", monospace';
  const L=26,R=30,T=8,B=20,pw=w-L-R,ph=h-T-B;
  const mxc=Math.max(...weekly.map(r=>r.corrections))*1.15||1;
  const bw=pw/weekly.length;
  x.strokeStyle=css('--rule');[0,1].forEach(f=>{const y=T+ph*f;
    x.beginPath();x.moveTo(L,y);x.lineTo(L+pw,y);x.stroke()});
  x.fillStyle=css('--ink-3');x.textAlign='right';
  x.fillText(String(Math.round(mxc)),L-4,T+8);x.fillText('0',L-4,T+ph);
  weekly.forEach((r,i)=>{const bh=ph*r.corrections/mxc;
    x.fillStyle=css('--accent-2');x.globalAlpha=.75;
    x.fillRect(L+i*bw+1,T+ph-bh,Math.max(2,bw-2),bh);x.globalAlpha=1;
    if(i%4===0){x.fillStyle=css('--ink-3');x.textAlign='center';
      x.fillText(String(r.week).slice(5,10),L+i*bw+bw/2,h-7)}});
  const chg=weekly.map(r=>r.mean_change_pct).filter(v=>v!=null);
  if(chg.length>1){
    const mxg=Math.max(...chg)*1.15||1;
    x.beginPath();let started=false;
    weekly.forEach((r,i)=>{if(r.mean_change_pct==null)return;
      const px=L+i*bw+bw/2,py=T+ph-ph*r.mean_change_pct/mxg;
      started?x.lineTo(px,py):x.moveTo(px,py);started=true});
    x.strokeStyle=css('--crit');x.lineWidth=1.8;x.stroke();
    x.fillStyle=css('--crit');x.textAlign='left';
    x.fillText(Math.round(Math.max(...chg))+'%',L+pw+4,T+8);
  }
}

/* ------------------------------------------------ state + boot */''')

print("app.py + index.html patched for per-device/per-clinic charts")
