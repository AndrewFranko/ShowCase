"""One-shot patch: bring app/static/index.html up to date with iterations 02-04.

The client was five iterations behind the API - disparity, conformance and evidence
packs were all live on the server and unreachable in the browser, which meant the
Playwright suite was testing a stale surface.
"""
import pathlib

p = pathlib.Path(__file__).resolve().parent.parent / "app" / "static" / "index.html"
s = p.read_text(encoding="utf-8")
before = len(s)

# --- nav gains an Evidence lens ---------------------------------------------
s = s.replace(
    "const LENSES=[['ops','Operations'],['quality','Quality'],['eng','Engineering'],['field','Field']];",
    "const LENSES=[['ops','Operations'],['quality','Quality'],['eng','Engineering'],\n"
    "              ['field','Field'],['evidence','Evidence']];")

# --- disparity panel into the Quality lens (iteration 02) -------------------
DISP_PANEL = '''  <div class="panel"><div class="ph"><span class="eyebrow">Quality &middot; iteration 02</span>
    <h2>Subgroup performance disparity</h2>
    <p id="dispPolicy">&hellip;</p></div>
    <div class="pb"><div class="tw"><table id="disp"><thead><tr>
      <th>Axis</th><th>Arm</th><th class="n">Cases</th><th style="width:100px">Rate</th>
      <th class="n">95% CI</th><th class="n">vs best</th><th>Status</th>
    </tr></thead><tbody></tbody></table></div></div></div>

  <div class="panel"><div class="ph"><span class="eyebrow">Quality &middot; cross-reference</span>'''
s = s.replace(
    '  <div class="panel"><div class="ph"><span class="eyebrow">Quality &middot; cross-reference</span>',
    DISP_PANEL)

# --- conformance panel into the Field lens (iteration 03) -------------------
CONF_PANEL = '''  <div class="panel"><div class="ph"><span class="eyebrow">Field service &middot; iteration 03</span>
    <h2>Attributable rejection</h2>
    <p id="confNote">&hellip;</p></div>
    <div class="pb"><div class="tw"><table id="conf"><thead><tr>
      <th>Site</th><th class="n">Cases</th><th class="n">Observed</th><th class="n">Expected</th>
      <th style="width:100px">Excess</th><th class="n">Med. HR</th><th class="n">Recoverable</th>
    </tr></thead><tbody></tbody></table></div></div></div>

  <div class="panel"><div class="ph"><span class="eyebrow">Field service &middot; silent failure</span>'''
s = s.replace(
    '  <div class="panel"><div class="ph"><span class="eyebrow">Field service &middot; silent failure</span>',
    CONF_PANEL)

# --- new Evidence lens (iteration 04) ---------------------------------------
EVIDENCE_LENS = '''<section class="lens" id="l-evidence">
  <div class="panel"><div class="ph"><span class="eyebrow">Iteration 04</span>
    <h2>Reproducible evidence pack</h2>
    <p>A number in a dashboard is not evidence. This carries the claim, the exact
    population, the method, the code version, a warehouse fingerprint, the stated
    limitations, and a manifest hash. The same warehouse state produces the same hash.</p></div>
    <div class="pb">
      <div class="ctl">
        <label class="eyebrow" for="claimSel">Claim</label>
        <select id="claimSel" style="font-family:'IBM Plex Mono',monospace;font-size:13px;padding:6px 9px;background:var(--surface-2);color:var(--ink);border:1px solid var(--rule-2)">
          <option value="frontier">automation_frontier</option>
          <option value="disparity">subgroup_disparity</option>
        </select>
        <button id="verifyBtn" style="background:var(--surface-2);border:1px solid var(--rule-2);color:var(--ink-2);font-family:'IBM Plex Mono',monospace;font-size:12px;padding:6px 11px;cursor:pointer">Fetch twice and compare hashes</button>
      </div>
      <div class="trace" id="packTrace"></div>
    </div></div>
</section>

<footer>Synthetic data. <span class="mono">GET /docs</span> for the OpenAPI schema.</footer>'''
s = s.replace(
    '<footer>Synthetic data. <span class="mono">GET /docs</span> for the OpenAPI schema.</footer>',
    EVIDENCE_LENS)

# --- renderers ---------------------------------------------------------------
RENDERERS = '''async function disparity(){
  const d=await get('/api/quality/disparity');
  const p=d.policy;
  $('dispPolicy').innerHTML=`Escalation is conjunctive and predetermined:
    FDR-significant (Benjamini-Hochberg q=${p.fdr_q}) <b>and</b> disparity &ge; ${p.min_disparity_ratio}x <b>and</b>
    arm &ge; ${p.min_arm_n} cases. ${p.comparisons} comparisons. ${p.note}`;
  const rows=[];
  for(const f of d.findings){
    for(const a of f.arms){
      const tag=a.escalate?['crit','escalate']
        :a.fdr_significant?['warn','significant only']:['info','-'];
      rows.push(`<tr><td class="mono" style="font-size:11.5px">${f.axis}</td>
        <td class="mono">${a.level}</td><td class="n">${a.n}</td>
        <td><span class="bar"><i style="width:${Math.min(100,a.rate*400).toFixed(0)}%"></i></span>
          <span class="mono" style="font-size:10.5px;color:var(--ink-3)">${pct(a.rate,2)}</span></td>
        <td class="n" style="font-size:11.5px">${pct(a.ci_low,1)}-${pct(a.ci_high,1)}</td>
        <td class="n">${a.disparity_vs_best.toFixed(2)}x</td>
        <td><span class="tag ${tag[0]}">${tag[1]}</span></td></tr>`);
    }
  }
  $('disp').tBodies[0].innerHTML=rows.join('');
}

async function conformance(){
  const c=await get('/api/field/conformance');
  const n=c.network;
  $('confNote').innerHTML=`Ranked by rejection <b>in excess of what case mix predicts</b>.
    Case mix explains <b>${pct(n.case_mix_variance_explained,1)}</b> of between-site variance -
    ${n.interpretation}.`;
  $('conf').tBodies[0].innerHTML=c.sites.map(s=>`<tr>
    <td>${s.site_name}<div style="font-size:10.5px;color:var(--ink-3)">${s.region} &middot; ${s.scanner_make}</div></td>
    <td class="n">${s.cases}</td><td class="n">${pct(s.observed_reject_rate)}</td>
    <td class="n">${pct(s.expected_reject_rate)}</td>
    <td><span class="bar"><i style="width:${Math.min(100,Math.max(0,s.excess_reject_rate)*400).toFixed(0)}%"></i></span>
      <span class="mono" style="font-size:10.5px;color:var(--ink-3)">${s.excess_reject_rate>=0?'+':''}${pct(s.excess_reject_rate)}</span></td>
    <td class="n">${s.median_heart_rate.toFixed(0)}</td>
    <td class="n">${s.recoverable_cases.toFixed(1)}</td></tr>`).join('');
}

async function evidencePack(){
  const which=$('claimSel').value;
  const pack=await get('/api/evidence/'+which);
  const c=pack.content;
  const ref=c.population.reference||c.population;
  const hop=(l,v)=>`<div class="hop"><div class="lbl">${l}</div><div>${v}</div></div>`;
  $('packTrace').innerHTML=
    hop('Claim',c.claim)+
    hop('Manifest',`<span class="mono" id="packHash">${pack.manifest_sha256}</span>`)+
    hop('Population',`reference n=<b>${ref.n}</b> &middot; sha <span class="mono" style="font-size:12px">${ref.case_id_sha256.slice(0,24)}...</span>`)+
    hop('Code version',`<span class="mono">${c.code_version}</span>`)+
    hop('Warehouse',`grain <span class="mono" style="font-size:12px">${c.spine_fingerprint.grain_sha256.slice(0,24)}...</span> &middot; ${c.spine_fingerprint.row_counts.fct_case_spine} cases`)+
    hop('Method',Object.entries(c.method).map(([k,v])=>`<b>${k}</b>: ${v}`).join('<br>'))+
    hop('Limitations','<ul style="margin:0;padding-left:18px">'+c.limitations.map(l=>`<li>${l}</li>`).join('')+'</ul>')+
    `<div id="hashCheck"></div>`;
}

async function engineering(){'''
s = s.replace("async function engineering(){", RENDERERS)

# --- wire it up ---------------------------------------------------------------
BOOT = '''  $('claimSel').onchange=evidencePack;
  $('verifyBtn').onclick=async()=>{
    const which=$('claimSel').value;
    const [a,b]=await Promise.all([get('/api/evidence/'+which),get('/api/evidence/'+which)]);
    const same=a.manifest_sha256===b.manifest_sha256;
    $('hashCheck').innerHTML=`<div class="finding" id="hashVerdict" data-same="${same}" style="background:${same?'var(--ok-bg)':'var(--crit-bg)'};border-color:${same?'var(--ok)':'var(--crit)'}">
      <b>${same?'Reproducible.':'NOT reproducible.'}</b> Two independent fetches
      ${same?'produced the identical manifest hash':'produced DIFFERENT hashes'}
      <span class="mono" style="font-size:12px">${a.manifest_sha256.slice(0,16)}...</span></div>`;
  };
  try{ await overview(); await frontier(); await quality(); await disparity();
       await engineering(); await field(); await conformance(); await evidencePack(); }'''
s = s.replace(
    "  try{ await overview(); await frontier(); await quality(); await engineering(); await field(); }",
    BOOT)

p.write_text(s, encoding="utf-8")
print(f"client patched: {before} -> {len(s)} bytes")
for marker in ("l-evidence", "async function disparity", "async function conformance",
               "async function evidencePack", "verifyBtn", "'evidence','Evidence'"):
    print(f"  {'ok ' if marker in s else 'MISSING'} {marker}")
