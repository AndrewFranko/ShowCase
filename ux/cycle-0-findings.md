# UX assessment — Cycle 0 (baseline)

Method: heuristic evaluation / cognitive walkthrough by Claude driving the real
deployed UI at 8091, plus the Playwright measurement harness
(`ux/cycle-0-metrics.json`). This is a discount-usability method, **not real-user
testing**; severities are analyst judgement, 0–4 (4 = task-blocking).

Baseline task outcome: **3 of 6 benchmark tasks completable.**

## Findings (severity-ranked)

| # | Sev | Persona/Task | Finding | Heuristic |
|---|-----|--------------|---------|-----------|
| F1 | **4** | P3 / T5 | **The policy brief is mathematically unsatisfiable in the UI.** `/api/shadow` accepts a tolerance parameter but the UI hardcodes 8%; at 8% no guard band yields ≥600 h with FN ≤ 5. The program lead's core job — trading tolerance against guard — cannot be done. | User control & freedom |
| F2 | **4** | P2 / T4 | **The sealed record disappears from UI reach.** The manifest hash shows only transiently in `#invOut` at closing time; afterwards there is no route to the record, its hash, or its verification status. The process's own artifact is unreachable — the harness had to fall back to the raw API. | Visibility of system status; recognition over recall |
| F3 | **3** | P1 / T1 | **Triage requires manually scanning 81 rows in a 300 px scroll box.** No sort, no filter, no urgency grouping; overdue items are scattered. Harness note: "scanned 81 rows manually". | Efficiency of use |
| F4 | **3** | P1 / T2+ | **Post-seal, the decision controls remain live and fail with errors.** Clicking Decide on a sealed investigation returns "refused: cannot decide from state 'closed'". The backend gate is right; the UI offering the illegal action is wrong. Same for reopening a closed item from the board — the drawer shows stale actionable controls. | Error prevention |
| F5 | 2 | P3 | FTE/capacity assumptions (26 wk × 32.5 h) are in the API payload but never shown in the UI; the headline "0.64 FTE" is unanchored. | Help & documentation |
| F6 | 2 | P3 / T6 | Harm-ledger rows name cases but link nowhere; verifying one means leaving the product. | Recognition over recall |
| F7 | 2 | P1 | `#invRationale`, `#invDecision`, `#shGuard` carry no labels/ARIA; screen-reader and keyboard use is guesswork. | Accessibility |
| F8 | 2 | P3 | Freeze-policy feedback is a 12-char text blip; the signed pack's role is hardcoded "program lead". | Visibility of status |
| F9 | 2 | all | No deep link to a specific investigation (`#investigation=N`); a colleague cannot be sent to the exact item. | Flexibility |
| F10 | 2 | P1/P2 | Process items are invisible in the Actions inbox — two work surfaces that do not know about each other. | Consistency |
| H1 | – | harness | T3 false-negative in the harness itself (sibling table *is* present through sealing; live walkthrough confirms). Instrumentation to fix in the harness, not the product. | – |

## Cycle-1 implement list (all sev ≥3, plus cheap sev-2 in the same code)

- **F1**: tolerance slider beside the guard slider; curve + stats + ledger re-render on both; sign body carries both dials. *(bundles F5: assumptions line under the stats)*
- **F2**: `GET /api/investigations/{id}/record` (reads the sealed file, re-verifies, returns summary+manifest); closed items on the board get a Record view in the drawer showing hash + verification. *(bundles F9: `#investigation=N` deep link)*
- **F3**: board default-sorted by urgency (overdue first, most negative clock first), quick filters All / Overdue / Actionable / Closed with counts.
- **F4**: drawer becomes state-aware — decision controls render only for `under_investigation`; decided shows Close only; closed shows the sealed-record panel. *(bundles F7: labels/ARIA on the controls that remain)*

Deferred to backlog as open work items: F6, F8 (partial — role field made editable is cheap, included), F10.

## Exit-gate status: **4 findings at severity ≥3 → loop continues.**
