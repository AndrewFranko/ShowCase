# Iteration 11 — Modelling the business processes, not the data

## The criticism
"Go deeper in use cases — the portal build is of no use." Correct: the portal
displayed analysis; a use case is a tool that does a specific person's job. Two
business processes are now modelled and implemented end to end, both grounded in
roles Heartflow is actively hiring or funding.

## Process 1 — Complaint investigation & MDR decision (21 CFR 820.198 / 803)
The Product Investigator's job (their open Austin req), as an enforced process:

    received → under_investigation → decided → closed
    Customer Support → Product Investigator → Quality decision-maker

What the software ENFORCES rather than displays:
- **The 30-day MDR clock** runs from complaint awareness; the board shows every
  complaint's position and days remaining. First run against the corpus showed
  **51 of 81 complaints overdue** — the process was not being run, which is
  exactly what a process tool exposes.
- **No undocumented decisions**: a reportability decision requires a named
  decision-maker and a substantive rationale (a thin one is refused with 422);
  a decision after the deadline is stored `late=true` forever, never absorbed.
- **The investigation file is assembled, not hunted**: chronology, what the
  correction changed, device context — including whether that release was later
  confirmed regressed on that scanner make, the cross-reference a manual
  investigation misses — sibling scan (isolated vs systemic decided by a
  two-proportion test, not a vibe), hazard linkage, and an MDR rule trace
  labelled as decision support, with the human decision authoritative.
- **Closing seals a record**: hash-manifested artifact on disk; the sealed
  trail ends at "decided" by construction because the close event records the
  seal's own hash (it cannot be inside what it seals) — the live audit store
  holds the close event referencing the manifest.

## Process 2 — Automation policy decision (shadow simulation)
The program lead's actual question: "adopt policy P and NAME the patients whose
answer changes." A policy is two dials — strata tolerance AND a guard band
routing anything within ±g of the 0.80 threshold to a human regardless.

The computed tradeoff (tolerance 8%):

| ±g | auto cases | hours back | changed answers | would-be FN |
|---|---|---|---|---|
| 0.00 | 1,977 | 716 | 110 | 72 |
| 0.01 | 1,807 | 655 | 54 | 37 |
| 0.03 | 1,483 | 541 | 10 | 8 |
| 0.05 | 1,196 | 439 | 2 | 1 |
| 0.08 | 820 | 300 | 0 | 0 |

A ±0.03 guard keeps 75% of the volume while removing 91% of the harm — the
clinically obvious refinement the frontier alone misses, computed rather than
asserted (and its monotonicity + threshold-concentration are test invariants).
Would-be false negatives (the MAUDE-pattern harm) are never summed with false
positives. The harm ledger names each case with its distance from threshold and
complaint linkage. "Freeze policy" produces a signable evidence pack whose harm
ledger is pinned by hash. Framing carried on every result: retrospective replay,
not prospective non-inferiority.

## Defects found in this iteration
- Guardrail test correctly BLOCKED the new write routes until the validation
  plan amendment consciously extended the writable prefixes (complaint-file
  workflow is the canonical QMS software function).
- Sealed-record chicken-and-egg (close event vs its own hash) — resolved by
  construction, documented in the test.
- The container's read-only rootfs caught a second undeclared write surface
  (investigation records) → INVESTIGATION_DIR on the /state volume.
- Intl.NumberFormat U+00A0 separators bit a test parser again → digits-only.

## Verified
100 fast · 23 in-process · **37 deployed-browser on the local deploy AND on the
container**, including both processes driven end-to-end through the real UI
(thin rationale refused, LATE flagged, record sealed; guard slider moving harm
and volume in opposite directions live).
