# Iteration 04 — Reproducible evidence pack

## Business analysis

**The gap.** Everything built so far is a live query. A regulator cannot cite a live query.

The automation frontier is the argument for removing analysts from a defined subset of cases.
That argument goes into a Predetermined Change Control Plan, and a PCCP has to state, in
advance and in writing: which modifications are covered, the methodology used to validate
them, and the acceptance criteria. Six months later a reviewer asks *"how did you arrive at
41% of volume?"* and the answer cannot be "run this endpoint again" — the warehouse has moved,
the model has shipped twice, and the number will not reproduce.

**What K250902 tells us the bar is.** Their existing cleared PCCP covers exactly three
modifications with a stated acceptance criterion (non-inferiority on plaque detection
sensitivity and volume error, DICE ≥ 0.7). That is the shape: enumerated changes, named
method, numeric threshold. An evidence pack has to be that specific and it has to be frozen.

**Second driver.** The 510(k) summary describes a *"restricted library solely used for
validation testing"* that *"aims to prevent"* validation cases being used for training.
*Aims to.* That is a procedural control where a system control belongs, and it is a clean
audit finding waiting to happen. An evidence pack that records exactly which case IDs
supported a claim closes it: contamination becomes checkable rather than promised.

## Architecture

**Decision: content-addressed, immutable snapshots.**

An evidence pack is a JSON document containing the claim, the numbers supporting it, the
exact population, and a manifest hash. Publishing one writes it to `evidence/` under its hash
and never modifies it.

The hash covers the **inputs and the result**, not the timestamp — so regenerating from the
same warehouse state produces the identical hash. That is the property that makes it
reproducible rather than merely archived, and it is testable.

**What goes in the manifest:**

| Field | Why |
|---|---|
| `case_ids` (sorted, hashed) | The exact population. Makes train/validation contamination checkable against the model's training manifest — closes the "aims to prevent" gap. |
| `spine_fingerprint` | Row count + hash of the source extracts, so the warehouse state is pinned. |
| `code_version` | Git SHA if available, else a hash of the metric definitions. A number is meaningless without the code that computed it. |
| `policy` | Thresholds *as they were* — FDR q, disparity floor, tolerance. These are predetermined; recording them after the fact is worthless. |
| `method` | Named: direct standardisation, Wilson intervals, Benjamini–Hochberg. |
| `limitations` | Written down, not omitted. A pack that claims no limitations is not credible. |

**Decision: the pack carries its own verification.** `verify()` recomputes the hash from the
stored content and compares. A pack that has been edited fails verification. This is cheap
and it is the difference between an archive and an audit trail.

**Decision: no PDF, no rendering, no signature block in v1.** Those are presentation. The
regulated substance is the reproducible content. Rendering can be added later without
touching the evidence model; doing it first would invite the pack to be shaped by what looks
good on a page.

## Implementation

`spine/evidence.py` — build, hash, persist, verify. Endpoint + MCP tool. Packs land in
`evidence/`.

## Result

See `04-results.md`.

## Iterate → next

The evidence pack makes a human-facing claim reproducible. Nothing yet checks whether the MCP
surface gives an *agent* the same answer a human would get, or whether an agent reports an
`unconfirmed` signal as a regression. That is iteration 05.
