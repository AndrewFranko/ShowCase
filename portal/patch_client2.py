import pathlib
p = pathlib.Path(__file__).resolve().parent.parent / "app" / "static" / "index.html"
s = p.read_text(encoding="utf-8")

DISP = '''  <div class="panel"><div class="ph"><span class="eyebrow">Quality · iteration 02</span>
    <h2>Subgroup performance disparity</h2>
    <p id="dispPolicy">…</p></div>
    <div class="pb"><div class="tw"><table id="disp"><thead><tr>
      <th>Axis</th><th>Arm</th><th class="n">Cases</th><th style="width:100px">Rate</th>
      <th class="n">95% CI</th><th class="n">vs best</th><th>Status</th>
    </tr></thead><tbody></tbody></table></div></div></div>

  <div class="panel"><div class="ph"><span class="eyebrow">Quality · cross-reference</span>'''
anchor_q = '  <div class="panel"><div class="ph"><span class="eyebrow">Quality · cross-reference</span>'
assert anchor_q in s, "quality anchor not found"
s = s.replace(anchor_q, DISP, 1)

CONF = '''  <div class="panel"><div class="ph"><span class="eyebrow">Field service · iteration 03</span>
    <h2>Attributable rejection</h2>
    <p id="confNote">…</p></div>
    <div class="pb"><div class="tw"><table id="conf"><thead><tr>
      <th>Site</th><th class="n">Cases</th><th class="n">Observed</th><th class="n">Expected</th>
      <th style="width:100px">Excess</th><th class="n">Med. HR</th><th class="n">Recoverable</th>
    </tr></thead><tbody></tbody></table></div></div></div>

  <div class="panel"><div class="ph"><span class="eyebrow">Field service · silent failure</span>'''
anchor_f = '  <div class="panel"><div class="ph"><span class="eyebrow">Field service · silent failure</span>'
assert anchor_f in s, "field anchor not found"
s = s.replace(anchor_f, CONF, 1)

p.write_text(s, encoding="utf-8")
for m in ('id="disp"', 'id="conf"', 'id="dispPolicy"', 'id="confNote"'):
    print(f"  {'ok ' if m in s else 'MISSING'} {m}")
