"""Interactive charts: hover tooltips with exact values on every canvas,
pointer affordance + click-through where a drill-down exists, and a
reduced-motion-guarded lens transition. Pure additive layer - draw functions
register hit regions; a shared handler positions one fixed tooltip element.
No IDs or asserted strings change."""
import pathlib

P = pathlib.Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"
s = P.read_text(encoding="utf-8")
n0 = len(s)

def sub(old, new, count=1):
    global s
    assert s.count(old) == count, f"anchor x{s.count(old)} (want {count}): {old[:70]!r}"
    s = s.replace(old, new, count)

# ---------------------------------------------------------------- CSS
sub("""footer{margin-top:34px;padding-top:20px;border-top:1px solid var(--rule);
  font-size:12.5px;color:var(--ink-3);line-height:1.6}""",
    """footer{margin-top:34px;padding-top:20px;border-top:1px solid var(--rule);
  font-size:12.5px;color:var(--ink-3);line-height:1.6}
#tip{position:fixed;z-index:60;pointer-events:none;display:none;max-width:300px;
  background:var(--surface);border:1px solid var(--rule-2);box-shadow:var(--shadow);
  padding:8px 11px;font:11.5px "IBM Plex Mono",monospace;line-height:1.6;color:var(--ink)}
#tip .t{display:block;font:600 9.5px "IBM Plex Mono",monospace;letter-spacing:.08em;
  text-transform:uppercase;color:var(--ink-3);margin-bottom:3px}
#tip b{color:var(--accent)}
canvas.hit{cursor:crosshair}
@media (prefers-reduced-motion:no-preference){
  .lens.on{animation:lensIn .16s ease-out}
  @keyframes lensIn{from{opacity:.4;transform:translateY(3px)}to{opacity:1;transform:none}}
}""")

# ---------------------------------------------------------------- framework after grid()
sub("""const LENSES=[['findings','Findings'],['ops','Operations'],['quality','Quality'],""",
    """/* ------------------------------------------------ chart interaction layer
   Draw functions register hit regions (rects {x,y,w,h} or points {x,y,r}) in
   CSS-pixel space; one fixed #tip element follows the pointer. Regions with a
   `go` hash navigate on click and show a pointer cursor. */
const tipEl=document.createElement('div');tipEl.id='tip';document.body.appendChild(tipEl);
const HITMAP={};
function setHits(id,regions){
  HITMAP[id]=regions;
  const cv=$(id);if(!cv||cv._hitBound)return;cv._hitBound=true;cv.classList.add('hit');
  const find=e=>{
    let best=null,bd=1e9;
    for(const r of (HITMAP[id]||[])){
      let d;
      if(r.w!=null){
        if(e.offsetX<r.x||e.offsetX>r.x+r.w||e.offsetY<r.y||e.offsetY>r.y+r.h)continue;
        d=Math.abs(e.offsetX-(r.x+r.w/2));
      }else{
        d=Math.hypot(e.offsetX-r.x,e.offsetY-r.y);
        if(d>(r.r||14))continue;
      }
      if(d<bd){bd=d;best=r;}
    }
    return best;
  };
  cv.addEventListener('mousemove',e=>{
    const r=find(e);
    if(!r){tipEl.style.display='none';cv.style.cursor='crosshair';return;}
    cv.style.cursor=r.go?'pointer':'crosshair';
    tipEl.innerHTML=r.tip;tipEl.style.display='block';
    let px=e.clientX+14;
    if(px+tipEl.offsetWidth>innerWidth-8)px=e.clientX-tipEl.offsetWidth-14;
    let py=e.clientY+12;
    if(py+tipEl.offsetHeight>innerHeight-8)py=e.clientY-tipEl.offsetHeight-12;
    tipEl.style.left=Math.max(4,px)+'px';tipEl.style.top=Math.max(4,py)+'px';
  });
  cv.addEventListener('mouseleave',()=>{tipEl.style.display='none';});
  cv.addEventListener('click',e=>{const r=find(e);if(r&&r.go)location.hash=r.go;});
}

const LENSES=[['findings','Findings'],['ops','Operations'],['quality','Quality'],""")

# ---------------------------------------------------------------- effort bars
sub("""  const bw=pw/d.length;
  d.forEach((b,i)=>{
    const bx=L+i*bw,act=b.hours*b.actionable_rate,con=b.hours-act;
    const hc=ph*con/mx,ha=ph*act/mx;
    x.globalAlpha=.85;x.fillStyle=css('--flow-hi');x.fillRect(bx+3,T+ph-hc,bw-6,hc);
    x.globalAlpha=1;x.fillStyle=css('--flow-lo');x.fillRect(bx+3,T+ph-hc-ha,bw-6,ha);
    x.fillStyle=css('--ink-3');x.textAlign='center';x.fillText(b.min_bucket,bx+bw/2,h-28);
    x.fillStyle=css('--crit');x.fillText(pct(b.actionable_rate,0),bx+bw/2,h-13);
  });""",
    """  const bw=pw/d.length,effortHits=[];
  d.forEach((b,i)=>{
    const bx=L+i*bw,act=b.hours*b.actionable_rate,con=b.hours-act;
    const hc=ph*con/mx,ha=ph*act/mx;
    x.globalAlpha=.85;x.fillStyle=css('--flow-hi');x.fillRect(bx+3,T+ph-hc,bw-6,hc);
    x.globalAlpha=1;x.fillStyle=css('--flow-lo');x.fillRect(bx+3,T+ph-hc-ha,bw-6,ha);
    x.fillStyle=css('--ink-3');x.textAlign='center';x.fillText(b.min_bucket,bx+bw/2,h-28);
    x.fillStyle=css('--crit');x.fillText(pct(b.actionable_rate,0),bx+bw/2,h-13);
    const band=i===d.length-1?`&ge;${b.min_bucket} min`:`${b.min_bucket}&ndash;${b.min_bucket+10} min`;
    effortHits.push({x:bx+1,y:T,w:bw-2,h:ph,go:'#lens=ops',
      tip:`<span class="t">${band}</span>${num(b.cases)} cases &middot; ${b.hours.toFixed(0)} h`+
          `<br>changed the answer: <b>${pct(b.actionable_rate,1)}</b> (${b.actionable} case${b.actionable===1?'':'s'})`});
  });
  setHits('vizEffort',effortHits);""")

# ---------------------------------------------------------------- delta histogram
sub("""  const bw=pw/HIST.length;
  HIST.forEach((b,i)=>{
    const bx=L+i*bw,hu=ph*b.unchanged/mx,hc=ph*b.crossed/mx;
    x.globalAlpha=.8;x.fillStyle=css('--flow-hi');x.fillRect(bx+1,T+ph-hu,bw-2,hu);
    x.globalAlpha=1;x.fillStyle=css('--flow-lo');x.fillRect(bx+1,T+ph-hu-hc,bw-2,hc);
  });""",
    """  const bw=pw/HIST.length,step=0.13/HIST.length,deltaHits=[];
  HIST.forEach((b,i)=>{
    const bx=L+i*bw,hu=ph*b.unchanged/mx,hc=ph*b.crossed/mx;
    x.globalAlpha=.8;x.fillStyle=css('--flow-hi');x.fillRect(bx+1,T+ph-hu,bw-2,hu);
    x.globalAlpha=1;x.fillStyle=css('--flow-lo');x.fillRect(bx+1,T+ph-hu-hc,bw-2,hc);
    deltaHits.push({x:bx,y:T,w:bw,h:ph,
      tip:`<span class="t">|&Delta;FFR| ${(i*step).toFixed(3)}&ndash;${((i+1)*step).toFixed(3)}</span>`+
          `${num(b.unchanged+b.crossed)} corrections`+
          `<br>crossed 0.80: <b>${num(b.crossed)}</b> &middot; unchanged: ${num(b.unchanged)}`});
  });
  setHits('vizDelta',deltaHits);""")

# ---------------------------------------------------------------- release points
sub("""  makes.forEach(m=>{
    const pts=vers.map((v,i)=>{
      const r=REL.find(z=>z.scanner_make===m&&z.model_version===v);
      return r?{x:xf(i),y:T+ph-ph*val(r)/mx,r}:null;}).filter(Boolean);
    if(pts.length<2)return;""",
    """  const relHits=[];
  makes.forEach(m=>{
    const pts=vers.map((v,i)=>{
      const r=REL.find(z=>z.scanner_make===m&&z.model_version===v);
      return r?{x:xf(i),y:T+ph-ph*val(r)/mx,r}:null;}).filter(Boolean);
    pts.forEach(p=>relHits.push({x:p.x,y:p.y,r:13,go:'#release='+p.r.model_version,
      tip:`<span class="t">${m} &middot; ${p.r.model_version}</span>`+
          `standardised rate <b>${pct(val(p.r),2)}</b> &middot; n=${num(p.r.accepted_cases)}`+
          `<br>lift ${p.r.lift_vs_first_release.toFixed(2)}x &middot; p=${p.r.p_value.toFixed(4)}`+
          `<br><span class="tag ${p.r.signal==='regression'?'crit':'ok'}">${p.r.signal}</span>`}));
    if(pts.length<2)return;""")

sub("""    x.fillText(m,L+pw+10,last.y+4);x.font='11px "IBM Plex Mono", monospace';
  });
  const reg=REL.find(r=>r.signal==='regression');""",
    """    x.fillText(m,L+pw+10,last.y+4);x.font='11px "IBM Plex Mono", monospace';
  });
  setHits('vizRelease',relHits);
  const reg=REL.find(r=>r.signal==='regression');""")

# ---------------------------------------------------------------- detector points
sub("""  DET.migrated.forEach(s=>{
    const sw=s.detector_switch_day;""",
    """  const detHits=[];
  if(DET.control&&DET.control.series)DET.control.series.forEach(p=>detHits.push({
    x:xf(p.day_bucket),y:yf(p.median_tpv),r:10,
    tip:`<span class="t">control site &middot; day ${p.day_bucket}</span>`+
        `median TPV <b>${num(p.median_tpv)}</b> mm&sup3; &middot; n=${p.n} &middot; never migrated`}));
  DET.migrated.forEach(s=>{
    const sw=s.detector_switch_day;""")

sub("""      seg.forEach(p=>{x.beginPath();x.arc(xf(p.day_bucket),yf(p.median_tpv),2.6,0,7);x.fillStyle=css(tok);x.fill()});
    });
  });""",
    """      seg.forEach(p=>{x.beginPath();x.arc(xf(p.day_bucket),yf(p.median_tpv),2.6,0,7);x.fillStyle=css(tok);x.fill();
        detHits.push({x:xf(p.day_bucket),y:yf(p.median_tpv),r:10,go:'#site='+s.site_id,
          tip:`<span class="t">${s.site_name} &middot; day ${p.day_bucket}</span>`+
              `${det} &middot; median TPV <b>${num(p.median_tpv)}</b> mm&sup3; &middot; n=${p.n}`+
              `<br>detector swap at day ${sw}`});});
    });
  });
  setHits('vizDetector',detHits);""")

# ---------------------------------------------------------------- disparity dots
sub("""  arms.forEach((a,i)=>{
    const y=T+rowH*(i+.5);
    const col=a.escalate?css('--crit'):a.fdr_significant?css('--warn'):css('--ink-3');""",
    """  const dispHits=[];
  arms.forEach((a,i)=>{
    const y=T+rowH*(i+.5);
    const col=a.escalate?css('--crit'):a.fdr_significant?css('--warn'):css('--ink-3');
    dispHits.push({x:L+pw*a.rate/mx,y,r:Math.max(10,rowH/2),go:'#lens=quality',
      tip:`<span class="t">${a.axis} &middot; ${a.level}</span>`+
          `rate <b>${pct(a.rate,2)}</b> &middot; n=${num(a.n)}`+
          `<br>95% CI ${pct(a.ci_low,1)}&ndash;${pct(a.ci_high,1)} &middot; ${a.disparity_vs_best.toFixed(2)}x vs best`+
          `<br><span class="tag ${a.escalate?'crit':a.fdr_significant?'warn':'info'}">${a.escalate?'escalate':a.fdr_significant?'significant only':'no material difference'}</span>`});""")

sub("""    x.fillText(a.axis.replace('_band','').replace('_at_scan','').slice(0,13),6,y+3.5);
  });""",
    """    x.fillText(a.axis.replace('_band','').replace('_at_scan','').slice(0,13),6,y+3.5);
  });
  setHits('vizDisparity',dispHits);""")

# ---------------------------------------------------------------- confidence bins
sub("""  d.forEach((p,i)=>{x.fillStyle=css('--ink-3');x.textAlign='center';x.fillText(p.confidence.toFixed(1),xf(i),h-22)});""",
    """  const confHits=[];
  d.forEach((p,i)=>{x.fillStyle=css('--ink-3');x.textAlign='center';x.fillText(p.confidence.toFixed(1),xf(i),h-22);
    confHits.push({x:xf(i)-(pw/d.length)/2,y:T,w:pw/d.length,h:ph,
      tip:`<span class="t">confidence ${p.confidence.toFixed(1)}</span>`+
          `${num(p.cases)} cases &middot; median <b>${p.median_min.toFixed(0)} min</b>`+
          `<br>actionable rate <b>${pct(p.actionable_rate,1)}</b>`});});
  setHits('vizConfidence',confHits);""")

# ---------------------------------------------------------------- frontier strata columns
sub("""  const el=STRATA.filter(s=>s.actionable_correction_rate<=tol).length;
  if(el){const px=L+pw*el/STRATA.length;""",
    """  const frontHits=STRATA.map((st,i)=>({
    x:L+pw*i/STRATA.length,y:T,w:pw/STRATA.length,h:ph,
    tip:`<span class="t">${st.stratum}</span>`+
        `${num(st.accepted_cases)} cases &middot; rate <b>${pct(st.actionable_correction_rate,2)}</b>`+
        `<br>cumulative volume ${pct(st.cumulative_share,0)} &middot; ${st.median_analyst_min.toFixed(0)} min median`+
        `<br>${st.actionable_correction_rate<=tol?'<span class="tag ok">within tolerance</span>':'<span class="tag crit">above tolerance</span>'}`}));
  setHits('vizFrontier',frontHits);
  const el=STRATA.filter(s=>s.actionable_correction_rate<=tol).length;
  if(el){const px=L+pw*el/STRATA.length;""")

P.write_text(s, encoding="utf-8")
print(f"patched: {n0} -> {len(s)} bytes")
