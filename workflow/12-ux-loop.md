# Iteration 12 — The UX loop: implement → Playwright → assessment, to gate

Plan: both business processes through a disciplined loop until an assessment
pass has zero severity-≥3 findings (cap 4 cycles). **Exited after 1 fix cycle.**

## Loop artifacts
- `ux/cycle-0-findings.md` / `-metrics.json` — baseline: **3/6 benchmark tasks
  completable**; 4 findings at sev ≥3, incl. one task (T5) *mathematically
  impossible* in the UI (tolerance hardcoded) and the process's own sealed
  artifact unreachable after the fact (T4).
- `ux/cycle-1-findings.md` / `-metrics.json` — after fixes: **6/6 tasks**,
  zero sev-≥3, two new sev-≤2 findings logged.
- `tests/ux/measure_tasks.py` — golden-path measurement harness (interactions,
  wall-time per task), updated per cycle with path changes called out.
- `deploy/reset_state.py` (`make reset-state`) — identical state per assessment.

## The rule that made it stick
**Every fixed finding got a Playwright regression test** (four new tests named
after the findings), so a fix cannot silently regress. And every finding —
fixed or open — is a `ux_finding` work item in the portal's own Actions inbox,
resolved through the portal's own lifecycle with the regression test named in
the closing note. The tool tracks its own defects.

## Honest notes
- The assessment is a Claude-driven heuristic evaluation / cognitive
  walkthrough — a discount-usability method, not real-user testing. Stated on
  every artifact.
- Two of the loop's five defects were in the loop's own instrumentation (a
  test race on a re-render; a case-sensitive match against CSS-uppercased
  text — the second occurrence of that exact trap in this codebase). Measured
  honestly rather than blamed on the product.
- "More interactions" (9→12) is success here: two previously impossible tasks
  became completable. Metrics need reading, not just collecting.

## Final state
100 fast · 23 in-process · **41 deployed-browser green on the local deploy AND
the container** (rebuilt at the gate). Open UX debt: 5 sev-≤2 items, tracked
in-product.
