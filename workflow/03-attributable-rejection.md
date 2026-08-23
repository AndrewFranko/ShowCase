# Iteration 03 — Attributable rejection and site conformance

## Business analysis

**The gap.** 5–15% of submitted studies are rejected before analysis. Every one is a triple
loss: no revenue, a wasted triage, and a clinician who waited and got nothing. Motion artifact
causes roughly 78% of them, and motion is a function of heart-rate control and
nitroglycerin — **things the imaging site controls**, and which the 2026 SCCT/SCAI consensus
requires.

**Who acts on this.** They have five open Clinical Field Specialist requisitions whose job is
visiting sites to fix acquisition technique. Right now those visits are presumably triaged by
relationship and geography. A ranked worklist would make five people materially more
effective, and it is the cheapest revenue recovery available: a rejected case that becomes an
accepted case is a case that bills.

**The trap, and it is the whole iteration.** Iteration 00's site worklist ranks by raw
rejection rate. That is unfair and, worse, misleading. A site serving heavier patients with
more calcified arteries will reject more no matter how good its technique is. Sending a field
specialist there to "fix" acquisition wastes a visit and damages the relationship — the site
knows its patients are harder, and being told otherwise reads as the vendor not
understanding their practice.

**The question worth answering is not "who rejects most" but "who rejects more than their
case mix predicts".**

## Architecture

**Decision: expected-vs-observed rejection, using the same standardisation machinery as
iteration 01.**

For each site, compute the rejection rate its case mix would predict if it performed like the
network average, then compare to what it actually does. The residual is the part plausibly
attributable to technique.

```
expected_i = Σ_s  network_reject_rate(s) × site_i_case_share(s)
excess_i   = observed_i − expected_i
```

Stratifying on `bmi_band × calcium_band` — patient-intrinsic factors the site cannot change.
Deliberately **not** stratifying on motion score or nitroglycerin: those are the technique
signal, and adjusting for them would subtract the very thing being measured. Same trap as
iteration 01's confidence column, and just as easy to get backwards.

**Decision: site-level guidance only. No per-case pre-upload gate.**

This one is a regulatory judgement and it is worth stating plainly:

| Option | Classification | Verdict |
|---|---|---|
| Per-case score returned to the scanner before upload, gating submission | Decides whether a patient's study is analysed → **device software function** | Rejected. New 510(k) territory, and the failure mode is a study wrongly withheld. |
| Per-case score shown to Heartflow ops for triage | Still influences case handling | Rejected for now. Defensible, but it is a decision surface and this project is deliberately not one. |
| **Site-level retrospective conformance, reported to field service** | Observational reporting on process → **production/QMS software** | **Chosen.** Stays under Computer Software Assurance, ships in weeks, and delivers most of the value. |

The per-case version is the better product and the wrong first move. Build the measurement,
prove the signal is real, then let Regulatory decide whether a gate is worth a submission.

**Third decision: report a confidence interval on the excess, and suppress low-volume sites.**
A site with 9 cases and 2 rejections has a 22% rate and no information. Suppressing below 25
cases; reporting Wilson bounds on the rest so a field manager can see which gaps are solid.

## Implementation

New model `060_fct_site_conformance.sql`, plus `metrics.site_conformance()`, an endpoint, and
an MCP tool.

## Result

See `03-results.md`.

## Iterate → next

Once the frontier, the disparity monitor and the conformance model all exist as live queries,
the obvious next problem is that a regulator cannot cite a live query. A submission needs a
frozen, versioned, reproducible artifact. That is iteration 04.
