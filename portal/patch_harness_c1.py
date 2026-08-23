"""Update the measurement harness's golden paths for the cycle-1 UI."""
import pathlib

p = pathlib.Path(__file__).resolve().parent.parent / "tests" / "ux" / "measure_tasks.py"
s = p.read_text(encoding="utf-8")

OLD_T1 = '''        t.click('#nav button[data-k="quality"]', "navigate to Quality")
        page.wait_for_selector("#invBoard tbody tr")
        # Current UI has no sort/filter: the persona must SCAN 81 rows. The
        # harness emulates the cheapest honest route: read rows in DOM order,
        # pick the overdue false_negative with the most negative clock.
        rows = page.eval_on_selector_all(
            "#invBoard tr[data-inv]",
            """rs => rs.map(r => ({
                 inv: r.dataset.inv,
                 type: r.cells[1].innerText,
                 clock: r.cells[3].innerText,
                 openable: !!r.querySelector('.invOpen')}))""")
        cands = [r for r in rows
                 if "false negative" in r["type"] and "OVERDUE" in r["clock"]
                 and r["openable"]]
        if not cands:
            t.notes.append("no openable overdue false-negative left in state")
            t.done(False)
        else:
            target = min(cands, key=lambda r: digits(r["clock"]) * -1)
            t.notes.append(f"scanned {len(rows)} rows manually (no sort/filter)")
            t.click(f'#invBoard tr[data-inv="{target["inv"]}"] .invOpen',
                    "open investigation")
            page.wait_for_selector("#invDrawer #invDecide")
            t.done(True)
            t1_target = target["inv"]
        results.append(t.result())'''
NEW_T1 = '''        t.click('#nav button[data-k="quality"]', "navigate to Quality")
        page.wait_for_selector("#invBoard tbody tr")
        # Cycle-1 UI: board defaults to Overdue, urgency-sorted - the golden path
        # is "take the first openable false-negative near the top".
        rows = page.eval_on_selector_all(
            "#invBoard tr[data-inv]",
            """rs => rs.map(r => ({
                 inv: r.dataset.inv,
                 type: r.cells[1].innerText,
                 openable: !!r.querySelector('.invOpen')}))""")
        cands = [r for r in rows
                 if "false negative" in r["type"] and r["openable"]]
        if not cands:
            t.notes.append("no openable overdue false-negative left in state")
            t.done(False)
        else:
            target = cands[0]   # urgency sort makes the first match the answer
            t.notes.append("default Overdue view is urgency-sorted; no scan")
            t.click(f'#invBoard tr[data-inv="{target["inv"]}"] .invOpen',
                    "open investigation")
            page.wait_for_selector("#invDrawer #invDecide")
            t.done(True)
        results.append(t.result())'''
assert OLD_T1 in s, "T1 anchor"
s = s.replace(OLD_T1, NEW_T1, 1)

OLD_23 = '''        # ---- T2: decide with rationale, seal ------------------------------
        t = Task(page, "T2", "P1: decide with rationale and seal the record")
        t.fill("#invRationale",
               "Malfunction with potential to contribute to serious injury; "
               "mechanism documented in the assembled file.")
        t.click("#invDecide", "record decision")
        page.wait_for_selector('#invOut:has-text("decided")')
        t.click("#invClose", "close and seal")
        page.wait_for_selector('#invOut:has-text("sealed")')
        t.done(True)
        results.append(t.result())

        # ---- T3: isolated or systemic? ------------------------------------
        t = Task(page, "T3", "P1: is this complaint isolated or systemic?")
        # Answer must come from the sibling table already in the drawer
        body = page.locator("#invDrawer").inner_text()
        has_table = "Isolated or systemic" in body
        t.notes.append("sibling table present in drawer"
                       if has_table else "sibling table missing")
        elevated = page.locator("#invDrawer .tag", has_text="elevated").count()
        t.notes.append(f"{elevated} scope(s) flagged elevated")
        t.done(has_table)
        results.append(t.result())'''
NEW_23 = '''        # ---- T3: isolated or systemic? (before sealing - the record view
        # correctly replaces the file view afterwards) -----------------------
        t = Task(page, "T3", "P1: is this complaint isolated or systemic?")
        body = page.locator("#invDrawer").inner_text()
        has_table = "Isolated or systemic" in body
        t.notes.append("sibling table present in drawer"
                       if has_table else "sibling table missing")
        elevated = page.locator("#invDrawer .tag", has_text="elevated").count()
        t.notes.append(f"{elevated} scope(s) flagged elevated")
        t.done(has_table)
        results.append(t.result())

        # ---- T2: decide with rationale, seal ------------------------------
        t = Task(page, "T2", "P1: decide with rationale and seal the record")
        t.fill("#invRationale",
               "Malfunction with potential to contribute to serious injury; "
               "mechanism documented in the assembled file.")
        t.click("#invDecide", "record decision")
        page.wait_for_selector('#invOut:has-text("decided")')
        t.click("#invClose", "close and seal")
        page.wait_for_selector(
            '#invDrawer:has-text("Sealed investigation record")')
        t.done(bool(re.search(r"[0-9a-f]{64}",
                              page.locator("#invDrawer").inner_text())))
        results.append(t.result())'''
assert OLD_23 in s, "T2/T3 anchor"
s = s.replace(OLD_23, NEW_23, 1)

OLD_T4 = '''        t.click('#nav button[data-k="quality"]', "navigate to Quality")
        page.wait_for_selector("#invBoard tbody tr")
        late = page.locator('#invBoard tr[data-inv]',
                            has=page.locator(".tag", has_text="LATE")).first
        if late.count() == 0:
            t.notes.append("no LATE decision visible on the board")
            t.done(False)
        else:
            t.click(f'#invBoard tr[data-inv="{late.get_attribute("data-inv")}"]',
                    "open the item")
            page.wait_for_selector("#invDrawer")
            # The sealed hash is only shown transiently in #invOut at closing
            # time; afterwards there is NO route to it in the UI. The honest
            # fallback is the API - which is itself the finding.
            with urllib.request.urlopen(BASE + "/api/actions") as r:
                r.read()
            t.interactions += 1
            t.notes.append("sealed hash NOT reachable from the UI after the "
                           "fact; fell back to raw API - candidate high-sev "
                           "finding")
            t.done(False)
        results.append(t.result())'''
NEW_T4 = '''        t.click('#nav button[data-k="quality"]', "navigate to Quality")
        page.wait_for_selector("#invBoard tbody tr")
        t.click('#invFilters [data-f="closed"]', "filter to Closed")
        page.wait_for_selector("#invBoard tr[data-inv]")
        t.click("#invBoard tr[data-inv] .invView", "open Record")
        page.wait_for_selector(
            '#invDrawer:has-text("Sealed investigation record")')
        body = page.locator("#invDrawer").inner_text()
        found = re.search(r"[0-9a-f]{64}", body)
        t.notes.append("manifest + verification + as-sealed trail visible"
                       if found else "record view missing manifest")
        t.done(bool(found) and "LATE" in body)
        results.append(t.result())'''
assert OLD_T4 in s, "T4 anchor"
s = s.replace(OLD_T4, NEW_T4, 1)

OLD_T5 = '''        t.click('#nav button[data-k="ops"]', "navigate to Operations")
        page.wait_for_selector("#shCurve tbody tr")
        curve = page.eval_on_selector_all('''
NEW_T5 = '''        t.click('#nav button[data-k="ops"]', "navigate to Operations")
        page.wait_for_selector("#shCurve tbody tr")
        # Cycle-1 UI: the brief needs headroom above the 8% default, so the
        # golden path raises the (new) tolerance dial first.
        t.set_range("#shTol", "0.12")
        page.wait_for_timeout(800)
        curve = page.eval_on_selector_all('''
assert OLD_T5 in s, "T5 anchor"
s = s.replace(OLD_T5, NEW_T5, 1)

s = s.replace("import urllib.request\n", "")
p.write_text(s, encoding="utf-8")
print("harness updated for cycle-1 golden paths")
