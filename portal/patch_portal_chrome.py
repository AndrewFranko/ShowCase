"""Restyle the client from narrative presentation to operational portal.

Keeps every ID, class and text the suites assert on (#heroBig, #heroCap contains
'confirmed the machine', #heroStats .v >= 4, .finding, canvas ids, nav labels,
foot ids). Changes: compact app bar, hero as lead-KPI band, findings as a dense
monitoring grid, sans-serif app typography, terse captions. Also fixes two
caption defects found in review: the n=1 '100%' headline (now pooled >=60 min)
and the Findings/Operations contradiction about effort vs impact.
"""
import pathlib

P = pathlib.Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"
s = P.read_text(encoding="utf-8")
n0 = len(s)

def sub(old, new, count=1):
    global s
    assert s.count(old) == count, f"anchor x{s.count(old)} (want {count}): {old[:70]!r}"
    s = s.replace(old, new, count)

# ---------------------------------------------------------------- typography: app sans
sub('h1,h2,h3{font-family:Spectral,Georgia,serif;margin:0;text-wrap:balance}',
    'h1,h2,h3{font-family:"IBM Plex Sans",system-ui,sans-serif;margin:0;text-wrap:balance}')

sub("font:600 14px Spectral,serif;color:var(--ink-2);white-space:nowrap}",
    'font:600 13px "IBM Plex Sans",sans-serif;color:var(--ink-2);white-space:nowrap}')

# ---------------------------------------------------------------- header -> app bar
sub("""header{padding:52px 0 26px}
header h1{font-size:clamp(30px,5.2vw,50px);font-weight:700;letter-spacing:-.025em;
  line-height:1.03;margin-top:14px}
header .thesis{max-width:62ch;margin-top:18px;font-size:18px;line-height:1.55;color:var(--ink-2)}
header .thesis b{color:var(--ink);font-weight:600}""",
    """header{padding:16px 0 10px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
header h1{font-size:17px;font-weight:650;letter-spacing:-.01em;line-height:1.2}
header .brand{display:flex;align-items:baseline;gap:10px;min-width:0;flex-wrap:wrap}""")

sub("""  font:600 10.5px "IBM Plex Mono",monospace;letter-spacing:.09em;text-transform:uppercase;margin-top:18px}""",
    """  font:600 10px "IBM Plex Mono",monospace;letter-spacing:.09em;text-transform:uppercase}""")

sub("""<header>
  <span class="eyebrow">One case ledger &middot; seven source systems &middot; read-only</span>
  <h1>What the humans are actually for</h1>
  <p class="thesis">Cost of revenue is analyst minutes, and the margin plan is to automate
  them away. Before that can be done safely, someone has to answer a question nobody
  currently measures: <b>when a person corrects the machine, does the patient's answer
  change?</b></p>
  <span class="synthetic">Synthetic data &middot; no Heartflow records</span>
  <div class="ctl" style="margin-top:22px;max-width:680px">
    <input id="askIn" type="text" placeholder="Ask the spine — e.g. any confirmed regressions?"
      style="flex:1 1 300px;font:13.5px 'IBM Plex Sans',sans-serif;padding:9px 12px;
      background:var(--surface);color:var(--ink);border:1px solid var(--rule-2)">
    <button class="btn" id="askBtn">Ask</button>
  </div>
  <div id="askOut" class="verdict" style="display:none;max-width:680px;margin-top:10px"></div>
</header>""",
    """<header>
  <div class="brand">
    <h1>Case Spine</h1>
    <span class="eyebrow">one case ledger &middot; 7 source systems &middot; read-only</span>
  </div>
  <span class="synthetic">Synthetic data &middot; no Heartflow records</span>
  <div class="ctl" style="margin:0 0 0 auto;flex:1 1 320px;max-width:520px">
    <input id="askIn" type="text" placeholder="Ask the spine — e.g. any confirmed regressions?"
      style="flex:1 1 220px;font:13px 'IBM Plex Sans',sans-serif;padding:7px 11px;
      background:var(--surface);color:var(--ink);border:1px solid var(--rule-2)">
    <button class="btn" id="askBtn">Ask</button>
  </div>
  <div id="askOut" class="verdict" style="display:none;flex-basis:100%;margin:0"></div>
</header>""")

# ---------------------------------------------------------------- hero -> lead-KPI band
sub(""".hero{background:var(--surface);border:1px solid var(--rule);box-shadow:var(--shadow);
  padding:30px 32px 26px;margin-bottom:24px}
.hero .big{font-family:"IBM Plex Mono",monospace;font-size:clamp(48px,10vw,84px);
  font-weight:600;letter-spacing:-.045em;line-height:.95;color:var(--accent);
  font-variant-numeric:tabular-nums}
.hero .cap{font-size:19px;line-height:1.45;margin-top:12px;max-width:56ch}
.hero .sub{font-size:14px;color:var(--ink-3);margin-top:12px;max-width:70ch}""",
    """.hero{background:var(--surface);border:1px solid var(--rule);box-shadow:var(--shadow);
  padding:16px 20px;margin-bottom:20px;display:grid;
  grid-template-columns:auto minmax(0,1fr);gap:4px 22px;align-items:center}
.hero .big{font-family:"IBM Plex Mono",monospace;font-size:clamp(30px,4.5vw,44px);
  font-weight:600;letter-spacing:-.04em;line-height:1;color:var(--accent);
  font-variant-numeric:tabular-nums;grid-row:span 2;align-self:center}
.hero .cap{font-size:13.5px;line-height:1.45;margin:2px 0 0}
.hero .sub{font-size:12px;color:var(--ink-3);margin:0;grid-column:2}
.hero .statrow{grid-column:1/-1}""")

sub("""  <div class="hero">
    <span class="eyebrow">The number this portal exists to produce</span>
    <div class="big" id="heroBig">&mdash;</div>
    <p class="cap" id="heroCap">&hellip;</p>
    <p class="sub" id="heroSub"></p>
    <div class="statrow" id="heroStats"></div>
  </div>""",
    """  <div class="hero">
    <div class="big" id="heroBig">&mdash;</div>
    <div style="min-width:0">
      <span class="eyebrow">Confirmation share of analyst time</span>
      <p class="cap" id="heroCap">&hellip;</p>
    </div>
    <p class="sub" id="heroSub"></p>
    <div class="statrow" id="heroStats"></div>
  </div>""")

# ---------------------------------------------------------------- finding cards -> dense grid
sub(""".finding-card{background:var(--surface);border:1px solid var(--rule);box-shadow:var(--shadow);
  margin-bottom:24px}
.fc-head{padding:20px 24px 16px;border-bottom:1px solid var(--rule)}
.fc-head .num{font:600 11px "IBM Plex Mono",monospace;letter-spacing:.12em;color:var(--accent)}
.fc-head h2{font-size:clamp(21px,3vw,27px);font-weight:600;letter-spacing:-.015em;
  margin-top:8px;line-height:1.18}
.fc-head p{margin:10px 0 0;font-size:15px;color:var(--ink-2);max-width:74ch;line-height:1.55}
.fc-body{padding:22px 24px}
.fc-foot{padding:16px 24px 18px;border-top:1px solid var(--rule);background:var(--surface-2);
  font-size:14px;line-height:1.55}""",
    """.finding-card{background:var(--surface);border:1px solid var(--rule);box-shadow:var(--shadow);
  margin-bottom:0;display:flex;flex-direction:column}
.fgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(440px,1fr));gap:18px;
  margin-bottom:20px}
@media (max-width:520px){.fgrid{grid-template-columns:1fr}}
.fc-head{padding:12px 16px 10px;border-bottom:1px solid var(--rule)}
.fc-head .num{font:600 9.5px "IBM Plex Mono",monospace;letter-spacing:.12em;color:var(--accent)}
.fc-head h2{font-size:15px;font-weight:600;letter-spacing:0;margin-top:4px;line-height:1.3}
.fc-head p{margin:5px 0 0;font-size:12.5px;color:var(--ink-3);max-width:none;line-height:1.5}
.fc-body{padding:14px 16px;flex:1}
.fc-foot{padding:10px 16px 12px;border-top:1px solid var(--rule);background:var(--surface-2);
  font-size:12.5px;line-height:1.5}""")

# panels a notch tighter, sans headings sized for chrome
sub(".ph h2{font-size:19px;font-weight:600;margin-top:5px}",
    ".ph h2{font-size:15px;font-weight:600;margin-top:4px}")

# narrow-viewport override written for the old hero padding
sub("  .hero{padding:22px}.fc-body{padding:16px}}",
    "  .hero{padding:14px 16px}.fc-body{padding:12px}}")

# ---------------------------------------------------------------- wrap the five cards
sub("""    <div class="statrow" id="heroStats"></div>
  </div>

  <article class="finding-card">""",
    """    <div class="statrow" id="heroStats"></div>
  </div>

  <div class="fgrid">
  <article class="finding-card">""")

sub("""    <div class="fc-foot" id="footDisparity">&hellip;</div>
  </article>

  <div class="note">""",
    """    <div class="fc-foot" id="footDisparity">&hellip;</div>
  </article>
  </div>

  <div class="note">""")

# ---------------------------------------------------------------- card heads: tool labels
sub("""      <span class="num">FINDING 01</span>
      <h2>The expensive cases are not the ones that matter</h2>
      <p>Every accepted case gets a human. Each bar is the analyst-hours spent at that level
      of effort, split by whether the correction moved an FFR value across the 0.80 decision
      threshold.</p>""",
    """      <span class="num">TELEMETRY</span>
      <h2>Analyst-hours by effort band</h2>
      <p>Accepted-case hours per effort band, split by whether the correction crossed the
      0.80 decision threshold.</p>""")

sub("""      <span class="num">FINDING 02</span>
      <h2>Most correction is confirmation</h2>
      <p>How far each correction moved the worst vessel's FFR. The mass at zero is work that
      produced no diagnostic change. The red tail is where the human earned the case.</p>""",
    """      <span class="num">CORRECTIONS</span>
      <h2>Correction depth (&Delta;FFR)</h2>
      <p>How far each correction moved the worst vessel's FFR. Mass at zero produced no
      diagnostic change.</p>""")

sub("""      <span class="num">FINDING 03</span>
      <h2>A release broke one scanner vendor and nothing else noticed</h2>
      <p>Actionable-correction rate by release, one line per scanner manufacturer. A
      regression confined to a single vendor's reconstructions is invisible in an aggregate
      metric &mdash; and invisible in any throughput dashboard, because the minutes barely
      moved.</p>""",
    """      <span class="num">RELEASE MONITOR</span>
      <h2>Actionable rate by release &times; scanner</h2>
      <p>One line per manufacturer. A vendor-confined regression is invisible in the
      aggregate.</p>""")

sub("""      <span class="num">FINDING 04</span>
      <h2>Two sites' plaque numbers fell by a third overnight</h2>
      <p>Median total plaque volume over time. Photon-counting detectors measure roughly a
      third less plaque than energy-integrating ones, and thresholds derived from the old
      detector do not transfer. Nothing failed: no rejection, no complaint, no alert. The
      numbers simply stepped.</p>""",
    """      <span class="num">DETECTOR MONITOR</span>
      <h2>Plaque volume by detector generation</h2>
      <p>Median total plaque volume over time, migrated sites vs a never-migrated
      control.</p>""")

sub("""      <span class="num">FINDING 05</span>
      <h2>Difficulty is not spread evenly across patients</h2>
      <p>Each dot is a subgroup with its 95% confidence interval. Distance from the
      best-performing arm is the disparity. Being statistically detectable is not the same
      as being worth acting on.</p>""",
    """      <span class="num">SUBGROUPS</span>
      <h2>Disparity vs best-performing arm</h2>
      <p>Each dot is a subgroup with its 95% CI. Escalation requires significance, effect
      size and arm size together.</p>""")

# ---------------------------------------------------------------- captions: terse + honest
# n=1 defect: last histogram bucket (80+ min, one case) was headlined as
# "cases over an hour, 100.0%". Pool everything >= 60 min instead.
sub("""  const f=d[0],l=d[d.length-1];
  $('footEffort').innerHTML=`Effort predicts impact: cases under 10 minutes changed the answer
    <b>${pct(f.actionable_rate,1)}</b> of the time; cases over an hour,
    <b>${pct(l.actionable_rate,1)}</b>. That is the good news &mdash; difficulty is visible
    <i>before</i> a human touches the case, which is what makes a stratified automation
    argument possible at all.
    <a href="#lens=ops" style="color:var(--accent-2);font-weight:600">Frontier &rarr;</a>`;""",
    """  const f=d[0],long=d.filter(b=>b.min_bucket>=60);
  const lc=long.reduce((s,b)=>s+b.cases,0),la=long.reduce((s,b)=>s+b.actionable,0);
  $('footEffort').innerHTML=`Under 10 min, <b>${pct(f.actionable_rate,1)}</b> of cases changed
    the answer; 60 min and over, <b>${pct(lc?la/lc:0,1)}</b> (${la}/${lc}). Difficulty is
    visible before a human touches the case.
    <a href="#lens=ops" style="color:var(--accent-2);font-weight:600">Frontier &rarr;</a>`;""")

sub("""  $('footDelta').innerHTML=`<b>${pct((f.unchanged+f.crossed)/tot,0)}</b> of corrections moved
    the value by less than 0.005 &mdash; below the reproducibility of invasive FFR itself.
    The question is not whether analysts are careful. It is whether this particular care is
    buying a different answer.`;""",
    """  $('footDelta').innerHTML=`<b>${pct((f.unchanged+f.crossed)/tot,0)}</b> of corrections moved
    the value by less than 0.005 &mdash; below the reproducibility of invasive FFR itself.`;""")

sub("""    ?`<b>${reg.model_version} on ${reg.scanner_make}</b> pushed the rate to
      <b>${pct(val(reg),2)}</b> &mdash; a ${reg.lift_vs_first_release.toFixed(2)}x lift,
      p&nbsp;=&nbsp;${reg.p_value.toFixed(4)} &mdash; while every other manufacturer stayed
      flat. Median analyst minutes barely moved, so nothing in a throughput view would have
      surfaced it. <a href="#release=${reg.model_version}" style="color:var(--accent-2);font-weight:600">See its complaints &rarr;</a>`""",
    """    ?`<b>${reg.model_version} on ${reg.scanner_make}</b>: <b>${pct(val(reg),2)}</b>,
      ${reg.lift_vs_first_release.toFixed(2)}x lift, p&nbsp;=&nbsp;${reg.p_value.toFixed(4)};
      other manufacturers flat. Minutes barely moved &mdash; invisible in throughput.
      <a href="#release=${reg.model_version}" style="color:var(--accent-2);font-weight:600">Complaints &rarr;</a>`""")

sub("""  $('footDetector').innerHTML=`Any nomogram percentile derived from energy-integrating data now
    misclassifies every patient at these sites. The dashed control site shows what no step
    looks like. <b>Detectable only because detector generation is resolved at scan time on the
    case row</b> &mdash; carry the site's current detector instead and the history silently
    rewrites itself. <a href="#site=${DET.migrated[0].site_id}" style="color:var(--accent-2);font-weight:600">Open the site card &rarr;</a>`;""",
    """  $('footDetector').innerHTML=`PCD measures roughly a third less plaque; EID-derived
    thresholds do not transfer. <b>Detected only because detector generation is resolved at
    scan time on the case row.</b>
    <a href="#site=${DET.migrated[0].site_id}" style="color:var(--accent-2);font-weight:600">Site card &rarr;</a>`;""")

sub("""  $('footDisparity').innerHTML=`<b>${esc}</b> arm(s) escalated. <b>${sig}</b> more are
    statistically significant but fall below the ${DISP.policy.min_disparity_ratio}x effect
    floor and are deliberately <i>not</i> escalated &mdash; on this many cases a small gap is
    easy to detect and not worth acting on. Escalation requires significance <i>and</i> effect
    size <i>and</i> a minimum arm size, all three.
    <a href="#lens=quality" style="color:var(--accent-2);font-weight:600">Full table &rarr;</a>`;""",
    """  $('footDisparity').innerHTML=`<b>${esc}</b> arm(s) escalated; <b>${sig}</b> significant
    but below the ${DISP.policy.min_disparity_ratio}x effect floor, deliberately not
    escalated. Escalation = significance <i>and</i> effect <i>and</i> arm size.
    <a href="#lens=quality" style="color:var(--accent-2);font-weight:600">Full table &rarr;</a>`;""")

sub("""  $('heroSub').textContent='That is not waste. It is the cost of a safety control nobody '+
    'has measured. Removing it is the margin plan; knowing which cases can safely lose it '+
    'is the prerequisite.';""",
    """  $('heroSub').textContent='The unmeasured cost of a safety control. The automation '+
    'question is which cases can safely lose it.';""")

# contradiction with the effort-band panel: impact DOES rise with effort
sub("""    <p>Analyst effort against auto-segmentation confidence. Effort is well predicted by
    confidence; diagnostic impact is only loosely related to either.</p>""",
    """    <p>Analyst effort against auto-segmentation confidence. Confidence predicts effort;
    impact rises with effort, but every band remains mostly confirmation.</p>""")

P.write_text(s, encoding="utf-8")
print(f"patched: {n0} -> {len(s)} bytes")
