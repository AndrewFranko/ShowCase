# UX assessment — Cycle 1 (gate pass)

Method as cycle 0 (heuristic evaluation + measurement harness; not real-user
testing). Fresh state via `make reset-state`, harness golden paths updated to the
cycle-1 UI (path changes called out below, per protocol).

## Task outcome: 6 of 6 complete (baseline: 3 of 6)

| Task | Baseline | Cycle 1 | Delta |
|---|---|---|---|
| T1 triage board | ok, but manual scan of 81 rows | ok — default Overdue view, urgency-sorted, first match is the answer | scan eliminated |
| T3 isolated/systemic | harness false-fail | ok (harness `inner_text` casefold fix — CSS uppercase trap, 2nd occurrence in this codebase) | instrumentation |
| T2 decide + seal | ok, 3 interactions | ok, 3 interactions; seal now lands on the record view | equal cost, better end-state |
| T4 locate sealed record | **FAIL** (API fallback only) | ok — Closed filter → Record, 3 interactions, 241 ms | unblocked |
| T5 satisfiable policy | **FAIL** (mathematically impossible at hardcoded 8%) | ok — tolerance dial → 12%, g=0.08 row satisfies brief; freeze+sign works | unblocked |
| T6 named FN list | ok | ok | — |

Totals: interactions 9→12 (more tasks *completable*, so more interactions is the
success condition here), wall 1.2s→3.0s (T5 now does real work).

## Verification of cycle-0 fixes
All four sev-≥3 findings have Playwright regression tests, green on the local
deploy and the container: F1/F2/F3/F4 → `test_f1_…` `test_f2_…` `test_f3_…`
`test_f4_…` in `tests/e2e/test_deployed.py`.

## New findings this pass (none at sev ≥3)
| # | Sev | Finding |
|---|---|---|
| G1 | 2 | Record view has no explicit back-to-board control (scroll works) |
| G2 | 1 | Drawer content persists across board filter switches |

One test-race in the new F1 regression test was found and fixed (waiting on the
readout label instead of the re-rendered data), and one harness defect (case-
sensitive match against CSS-uppercased text — same trap as workflow/06).

## Gate: **zero severity-≥3 findings → loop exits after 1 fix cycle.**
Open sev-≤2 items (F6, F8-partial, F10, G1, G2) are filed as `ux_finding` work
items in the portal's own Actions inbox — the dogfooding loop: 12 filed,
7 resolved through the portal's lifecycle with notes naming their regression
tests, 5 open.
