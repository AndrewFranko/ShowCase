"""
UX measurement harness - NOT a pass/fail test suite.

Drives the six persona benchmark tasks (plan: T1-T6) along their golden paths
against the deployed UI and records what each task COSTS: interactions, wall
time, and steps. The numbers are the baseline every fix cycle is measured
against; the qualitative findings come from the separate browser walkthrough.

Counting rules, so cycles stay comparable:
  * an "interaction" is one click, one option-select, or one text-field fill
    (a fill counts once regardless of characters - keystroke counts would just
    measure rationale length);
  * waits are included in wall time - a slow render IS a UX cost;
  * the golden path is the cheapest route the CURRENT UI permits. When a fix
    shortens a path, the script is updated and the change is called out in the
    cycle's findings file. That is the point: the harness measures the UI as it
    is, not as the script wishes it were.

Usage:
    python tests/ux/measure_tasks.py [cycle_number]
    -> writes ux/cycle-<n>-metrics.json
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BASE = os.environ.get("DEPLOY_BASE", "http://127.0.0.1:8091")
OUT_DIR = ROOT / "ux"


class Task:
    def __init__(self, page, name: str, description: str):
        self.page, self.name, self.description = page, name, description
        self.interactions = 0
        self.notes: list[str] = []
        self.t0 = time.perf_counter()
        self.ok = False

    # -- counted interaction primitives ------------------------------------
    def click(self, selector: str, note: str = ""):
        self.page.locator(selector).first.click()
        self.interactions += 1
        if note:
            self.notes.append(note)

    def fill(self, selector: str, value: str):
        self.page.locator(selector).fill(value)
        self.interactions += 1

    def select(self, selector: str, value: str):
        self.page.locator(selector).select_option(value)
        self.interactions += 1

    def set_range(self, selector: str, value: str):
        self.page.locator(selector).evaluate(
            "(el,v)=>{el.value=v;el.dispatchEvent(new Event('input'))}", value)
        self.interactions += 1

    def done(self, ok: bool = True):
        self.ok = ok
        self.ms = round((time.perf_counter() - self.t0) * 1000)

    def result(self) -> dict:
        return {"task": self.name, "description": self.description,
                "completed": self.ok, "interactions": self.interactions,
                "wall_ms": self.ms, "notes": self.notes}


def fresh(page):
    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_selector('body[data-ready="1"]', state="attached",
                           timeout=45_000)


def digits(text: str) -> int:
    return int(re.sub(r"\D", "", text) or 0)


def main() -> None:
    cycle = sys.argv[1] if len(sys.argv) > 1 else "0"
    results = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        auth = os.environ.get("DEPLOY_AUTH", "")
        creds = None
        if auth and ":" in auth:
            u, pwd = auth.split(":", 1)
            creds = {"username": u, "password": pwd}
        page = browser.new_context(http_credentials=creds).new_page()
        fresh(page)

        # ---- T1: triage - most urgent overdue false-negative, open it ----
        t = Task(page, "T1",
                 "P1: find the most urgent overdue false-negative; open it")
        t.click('#nav button[data-k="quality"]', "navigate to Quality")
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
        results.append(t.result())

        # ---- T3: isolated or systemic? (before sealing - the record view
        # correctly replaces the file view afterwards) -----------------------
        t = Task(page, "T3", "P1: is this complaint isolated or systemic?")
        # casefold: .eyebrow headers are CSS-uppercased and inner_text returns
        # the RENDERED text - a case-sensitive match reads as "table missing".
        # (Second time this trap has bitten this codebase; see workflow/06.)
        body = page.locator("#invDrawer").inner_text().casefold()
        has_table = "isolated or systemic" in body
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
        results.append(t.result())

        # ---- T4: audit trail + sealed hash of a decided-LATE case ---------
        fresh(page)
        t = Task(page, "T4",
                 "P2: locate audit trail and sealed hash of a LATE decision")
        t.click('#nav button[data-k="quality"]', "navigate to Quality")
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
        results.append(t.result())

        # ---- T5: pick guard band (>=600h, FN<=5), freeze & sign -----------
        fresh(page)
        t = Task(page, "T5",
                 "P3: guard band with >=600h returned and FN<=5; freeze+sign")
        t.click('#nav button[data-k="ops"]', "navigate to Operations")
        page.wait_for_selector("#shCurve tbody tr")
        # Cycle-1 UI: the brief needs headroom above the 8% default, so the
        # golden path raises the (new) tolerance dial first.
        t.set_range("#shTol", "0.12")
        page.wait_for_timeout(800)
        curve = page.eval_on_selector_all(
            "#shCurve tbody tr",
            """rs => rs.map(r => ({
                 g: r.cells[0].innerText, hours: r.cells[2].innerText,
                 fn: r.cells[4].innerText}))""")
        pick = None
        for c in curve:
            if digits(c["hours"]) >= 600 and digits(c["fn"]) <= 5:
                pick = c["g"]
        if pick is None:
            t.notes.append("no curve row satisfies the brief")
            t.done(False)
        else:
            t.notes.append(f"curve row satisfying brief: g={pick}")
            t.set_range("#shGuard", pick)
            page.wait_for_timeout(700)
            t.click("#shSign", "freeze policy")
            page.wait_for_selector('#shSignOut:has-text("signed")')
            t.done(True)
        results.append(t.result())

        # ---- T6: named would-be-FN list at that policy --------------------
        t = Task(page, "T6", "P3: produce the named would-be-FN list")
        fn_rows = page.locator("#shLedger .tag", has_text="false negative")
        n = fn_rows.count()
        t.notes.append(f"{n} FN rows visible in the ledger")
        t.done(n > 0 or "no changed answers" in
               page.locator("#shLedger").inner_text())
        results.append(t.result())

        browser.close()

    OUT_DIR.mkdir(exist_ok=True)
    payload = {
        "cycle": cycle,
        "base": BASE,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "counting_rules": "1 interaction = click/select/fill; waits included in wall time",
        "tasks": results,
        "totals": {
            "completed": sum(1 for r in results if r["completed"]),
            "of": len(results),
            "interactions": sum(r["interactions"] for r in results),
            "wall_ms": sum(r["wall_ms"] for r in results),
        },
    }
    out = OUT_DIR / f"cycle-{cycle}-metrics.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload["totals"], indent=2))
    for r in results:
        print(f"  {r['task']}: {'ok ' if r['completed'] else 'FAIL'}"
              f" {r['interactions']:2d} interactions {r['wall_ms']:6d} ms"
              f"  {r['notes'][:2]}")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
