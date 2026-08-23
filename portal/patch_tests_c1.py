"""Cycle-1 regression tests (one per fixed finding) + lifecycle test update."""
import pathlib

p = pathlib.Path(__file__).resolve().parent.parent / "tests" / "e2e" / "test_deployed.py"
s = p.read_text(encoding="utf-8")

OLD = '''    deployed.locator("#invClose").click()
    expect(deployed.locator("#invOut")).to_contain_text("sealed")'''
NEW = '''    deployed.locator("#invClose").click()
    # Cycle-1 F4/F2: sealing transitions the drawer to the sealed-record view
    deployed.wait_for_selector(
        '#invDrawer:has-text("Sealed investigation record")')
    assert re.search(r"[0-9a-f]{64}",
                     deployed.locator("#invDrawer").inner_text())'''
assert OLD in s, "lifecycle seal anchor"
s = s.replace(OLD, NEW, 1)

SUITE = '''

# ------------------------------------------------------------------ UX cycle 1
def test_f1_policy_brief_is_satisfiable_with_the_tolerance_dial(deployed):
    """Regression for cycle-0 F1 (sev 4): with tolerance raised, at least one
    guard row must satisfy the benchmark brief (>=600h returned, FN<=5)."""
    deployed.locator('#nav button[data-k="ops"]').click()
    deployed.wait_for_selector("#shTol")
    deployed.locator("#shTol").evaluate(
        "(el)=>{el.value='0.12';el.dispatchEvent(new Event('input'))}")
    deployed.wait_for_function(
        "() => document.getElementById('shTolOut').textContent.startsWith('12')")
    deployed.wait_for_selector("#shCurve tbody tr")
    rows = deployed.locator("#shCurve tbody tr")
    satisfiable = False
    for i in range(rows.count()):
        cells = rows.nth(i).locator("td")
        hours = int(re.sub(r"\\D", "", cells.nth(2).inner_text()) or 0)
        fn = int(re.sub(r"\\D", "", cells.nth(4).inner_text()) or 0)
        if hours >= 600 and fn <= 5:
            satisfiable = True
    assert satisfiable, "T5 brief unsatisfiable even with the tolerance dial"
    # F5 bundle: the FTE assumptions must be visible, not just in the payload
    expect(deployed.locator("#shStats")).to_contain_text("productive")


def test_f3_board_defaults_to_urgency_triage(deployed):
    """Regression for F3 (sev 3): default view is Overdue, most-urgent first,
    with counted quick filters."""
    deployed.locator('#nav button[data-k="quality"]').click()
    deployed.wait_for_selector("#invFilters [data-f]")
    pressed = deployed.locator('#invFilters [data-f][aria-pressed="true"]')
    assert pressed.get_attribute("data-f") == "overdue"
    for f in ("overdue", "actionable", "closed", "all"):
        label = deployed.locator(f'#invFilters [data-f="{f}"]').inner_text()
        assert re.search(r"\\(\\d+\\)", label), f"filter {f} lacks a count"
    clocks = [int(re.sub(r"[^\\d-]", "", c.inner_text().replace("OVERDUE", "")))
              for c in deployed.locator(
                  "#invBoard tr[data-inv] td:nth-child(4)").all()[:8]]
    assert clocks == sorted(clocks), f"not urgency-sorted: {clocks}"


def test_f4_sealed_investigation_offers_no_decision_controls(deployed):
    """Regression for F4 (sev 3): a closed investigation renders the record view
    with no live decision controls - prevention, not error messages."""
    deployed.locator('#nav button[data-k="quality"]').click()
    deployed.wait_for_selector("#invFilters [data-f]")
    deployed.locator('#invFilters [data-f="closed"]').click()
    rows = deployed.locator("#invBoard tr[data-inv]")
    if rows.count() == 0:
        pytest.skip("no closed investigation in state")
    assert rows.first.locator(".invView").inner_text() == "Record"
    rows.first.locator(".invView").click()
    deployed.wait_for_selector(
        '#invDrawer:has-text("Sealed investigation record")')
    assert deployed.locator("#invDrawer #invDecide").count() == 0
    assert deployed.locator("#invDrawer #invClose").count() == 0


def test_f2_sealed_record_reachable_and_verified_posthoc(deployed):
    """Regression for F2 (sev 4): manifest hash, verification status and the
    as-sealed audit trail reachable from the board at any later time."""
    deployed.locator('#nav button[data-k="quality"]').click()
    deployed.wait_for_selector("#invFilters [data-f]")
    deployed.locator('#invFilters [data-f="closed"]').click()
    rows = deployed.locator("#invBoard tr[data-inv]")
    if rows.count() == 0:
        pytest.skip("no closed investigation in state")
    rows.first.locator(".invView").click()
    deployed.wait_for_selector(
        '#invDrawer:has-text("Sealed investigation record")')
    body = deployed.locator("#invDrawer").inner_text()
    assert re.search(r"[0-9a-f]{64}", body), "manifest hash not shown"
    assert "verified" in body
    assert "\\u2192" in body or "->" in body, "as-sealed audit trail missing"
    assert "#investigation=" in deployed.url, "deep link not set (F9)"
'''
s = s.rstrip() + "\n" + SUITE
p.write_text(s, encoding="utf-8")
print("regression tests appended; lifecycle updated")
