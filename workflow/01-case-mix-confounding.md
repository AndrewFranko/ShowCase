# Iteration 01 — Case-mix confounding in release comparison

## Business analysis

**Question from the business:** the Engineering lens says v4.1.0 regressed on Canon
reconstructions. Before anyone acts on that — reverting a release, opening a CAPA, telling a
customer — is the finding trustworthy?

**Why it might not be.** The comparison is a crude rate: actionable corrections divided by
accepted cases, per release, per manufacturer. Releases are separated in *time*, and case mix
moves over time. Sites onboard, scanner fleets change, referral patterns shift seasonally. If
v4.1.0 happened to see harder cases, it will look like a regression even if the model was
byte-identical.

This is Simpson's paradox territory, and it is the single most common way an observational
release comparison misleads.

**Business impact if wrong, in both directions:**
- False positive → a good release gets reverted, engineering burns a cycle, and a CAPA is
  opened against a non-problem.
- False negative → a real regression hides behind a favourable case mix and reaches patients.

**Evidence gathered before writing any code:**

Case mix across releases (accepted cases):

| release | n | hi-calcium (>400) | hi-motion (≥1.4) | stent | mean confidence |
|---|---|---|---|---|---|
| v4.0.2 | 1731 | 23.5% | 13.5% | 7.3% | 0.7217 |
| v4.1.0 | 972 | 25.6% | 13.9% | 6.9% | 0.6910 |
| v4.1.3 | 620 | 26.3% | 11.3% | 9.7% | 0.7212 |

The mix is **not** stable. High-calcium share rises monotonically; stent share jumps 40%
relative in v4.1.3. The comparison is confounded. Confirmed, not assumed.

## Architecture

**Decision: direct standardisation against a fixed reference case mix.**

For each release × manufacturer cell, compute the per-stratum rate, then reweight those rates
to the mix of a single reference population (all accepted cases). The result answers: *what
would this release's rate have been if it had seen the standard case mix?*

Considered and rejected:

| Option | Why not |
|---|---|
| Logistic regression with covariates | Better statistically, but the output is a coefficient, not a rate. Quality and Operations need a number they can put next to another number. Opacity is a real cost in a regulated review. |
| Propensity matching | Discards data; unstable on small per-vendor cells; harder to explain to a reviewer. |
| Restrict to a single stratum | Throws away most of the volume and cannot answer the whole-portfolio question. |
| Indirect standardisation (SMR) | Reference is the study population, so cells are not comparable to each other — which is exactly what we need. |

Direct standardisation wins on **explainability under audit**, which is the binding
constraint here, not statistical elegance.

**Design constraint that matters:** stratum is defined by *acquisition* facts —
calcium, motion, stent — none of which the model version can influence. Standardising on it
adjusts for case mix without adjusting away the effect being measured. Standardising on
`autoseg_confidence` would be wrong: confidence is downstream of the model, so adjusting for
it would subtract the very regression we are trying to detect. This is the whole game and it
is easy to get backwards.

**Where it goes:** `spine/metrics.py`, so the API, the MCP surface and the Cube model all
inherit one definition. Not a one-off query in the endpoint.

## Result

Canon, crude vs standardised:

| release | n | crude | standardised | delta |
|---|---|---|---|---|
| v4.0.2 | 392 | 11.22% | 10.15% | +1.08 pp |
| v4.1.0 | 239 | 19.25% | **18.58%** | +0.66 pp |
| v4.1.3 | 114 | 7.02% | **5.51%** | +1.50 pp |

Siemens control:

| release | n | crude | standardised | delta |
|---|---|---|---|---|
| v4.0.2 | 640 | 11.88% | 12.42% | −0.54 pp |
| v4.1.0 | 361 | 14.68% | 14.40% | +0.28 pp |
| v4.1.3 | 248 | 15.73% | 16.31% | −0.58 pp |

**The regression survives standardisation.** 18.58% against a 10.15% baseline is still a
1.83× lift. The finding was right — but it was right by luck, and it is now defensible.

**The more interesting change is v4.1.3.** Crude 7.02% understates the fix; standardised
5.51% is a 46% reduction against baseline, because v4.1.3 saw the *hardest* mix in the window
(26.3% high-calcium, 9.7% stent) and still produced the lowest rate. The crude number was
hiding how good the fix was.

**Honest limitation:** confounding in this fixture is modest — roughly 1 percentage point —
because cases are assigned to sites and days at random. In production it would be larger:
real sites onboard in waves, fleets migrate, and referral mix is seasonal. The correction
matters more on real data than this demonstration makes it look.

## Iterate → next

Standardisation exposed a second problem it cannot solve. Reweighting to a reference mix
tells you the *average* effect, but a release can be neutral on average while badly hurting
one subgroup — and their own Post-Market Quality requisition asks for "subgroup performance"
and "performance disparity" explicitly. That is iteration 02.
