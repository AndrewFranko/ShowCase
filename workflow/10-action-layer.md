# Iteration 10 — The action layer: from dashboard to tool

## The criticism that drove it
"This is still a glorified dashboard. Where is real functionality?" — correct. The
portal observed; nothing could be owned, acted on, or produced. The read-only rule
had been over-applied: the regulatory line forbids writing to the CASE pipeline,
not writing workflow state ABOUT findings — the latter is what QMS software
(complaint handling) does all day.

## What was built
- **Work items** (spine/actions.py): findings auto-derive into owned items
  (disparity escalations, confirmed regressions, excess-rejection sites, hazard
  reviews). Five-state lifecycle (open → acknowledged → investigating →
  resolved/dismissed, reopen allowed), mandatory actor + note on every transition,
  append-only event log, idempotent sync that never resurrects closed items, and
  every item pins the warehouse grain hash it was raised from.
- **Evidence signing**: verify-before-sign, pack frozen to disk, signature
  recorded, RE-verified on every read — an edited pack shows BROKEN, not hidden.
- **Briefing export**: self-contained HTML artifact (headline numbers, open work,
  signed evidence, warehouse grain) with a download header.
- **Actions lens** in the client: inbox with per-card transition controls, inline
  refusals, audit-trail viewer, open-count badge; signing UI in the Evidence lens.

## The boundary, re-assessed formally
Validation plan Amendment A (its own §6 trigger honoured): classification
unchanged — production/QMS software. Writes go to a SEPARATE store
(data/actions.duckdb); the spine stays read-only in source; no write route accepts
a case identifier. Guardrails narrowed, not removed:
`test_write_routes_are_confined_to_the_action_layer`,
`test_action_store_is_not_the_spine`.

## Five real defects found by building and testing it
1. **`at` is a DuckDB reserved word** — schema failed at first touch.
2. **Mixed connection configs**: DuckDB refuses read_only + writable connects to
   one file within a process. First hardening attempt broke every read that
   followed a write. Resolution: uniform writable short-lived connections +
   bounded retry for cross-process lock contention.
3. **Read-only rootfs vs the write path**: the container 500'd on sync — workflow
   state needs a DECLARED writable volume. `/state` volume added, owned by the
   app user, ACTIONS_DB/EVIDENCE_DIR env-configurable. The container forced the
   correct production design.
4. **Playwright role-name matching is substring**: "Sync findings" collided with
   name="Findings"; the badge changed "Actions"' accessible name until made
   aria-hidden. Fixture now uses structural selectors.
5. **Windows uvicorn multi-worker wedging** (WinError 10022): requests hung
   forever on a wedged worker → intermittent hydration failures with zero 500s
   logged. Windows deploy defaults to 1 worker (documented); client fetches carry
   AbortSignal.timeout(20s) so a hang is a visible error, never a silent stall.
   Plus one test race of my own making (asserting before the sync re-render).

## Verified
| Suite | Result |
|---|---|
| fast (incl. 9 action-layer tests) | 93 passed |
| in-process browser | 23 passed |
| deployed browser vs local (8091) | 35 passed ×3 consecutive |
| deployed browser vs container (8088) | 35 passed |
