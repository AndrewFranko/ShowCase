# Iteration 05 — Results

## Harness scores

| Agent | Passed | Tool selection | Numeric | Interpretation |
|---|---|---|---|---|
| reference (deterministic) | **6/6** | 100% | 100% | 100% |
| naive (makes the documented mistakes) | **0/6** | 67% | 50% | **0%** |

The negative control is the important row. A harness that cannot fail an agent doing the
wrong thing measures nothing.

## The row that justifies three-dimensional scoring

```
clinical-gradient    tool: ok    numeric: ok    interpretation: FAIL
                     -> described_as_demographic_equity
```

Right tool. Right number. Wrong claim. Collapsed to a single pass/fail this reads as a
success, and the agent has just described clinical subgroup analysis as demographic equity
analysis — a category error with regulatory consequences, delivered fluently and with a
correct figure attached.

The naive agent scores **50% on numeric while scoring 0% on interpretation**. That is the
dangerous profile, and it is invisible to any harness that only checks the number.

## Degeneracy detection earned its place immediately

Eval suites rot when a case quietly stops separating right from wrong and nobody notices.
Each case can carry a **foil** — the value the *wrong* method produces. If foil equals ground
truth on a given run, the numeric check proves nothing and the harness says so.

It fired on the first run: `escalated-not-significant` was degenerate, because every
FDR-significant arm happened to also clear the effect-size floor. Only the interpretation
check caught the naive agent there.

After rescaling the fixture the flag **moved** — `escalated-not-significant` now
discriminates, and `confirmed-regressions-only` is degenerate instead. That movement is the
feature working: degeneracy is a property of the data on the day, not of the case, so it has
to be recomputed rather than annotated once.

## Two real bugs found by this iteration

**1. Non-deterministic evidence packs.** `test_evidence_pack_is_reproducible` failed. Cause:
two strata tied at exactly 0.16666666667, and `ORDER BY actionable_correction_rate` with no
tiebreaker returns tied rows in arbitrary order. The frontier ordering shifted between runs,
which changed the cumulative volume share, which changed the manifest hash.

An immutable evidence artifact that hashes differently on two runs of identical data is worse
than no artifact — it fails its own verification and discredits every pack filed beside it.
Fixed with a total ordering (`, stratum ASC`). Verified stable over 12 consecutive builds.

This is exactly what iteration 04 was built to catch, and it caught it one iteration later.

**2. The fixture was under-powered.** After iteration 03 added between-site case-mix variance,
the planted Canon regression fell to lift 1.59 at **p = 0.0588** — the effect was real, the
direction was right, and the significance gate correctly refused to confirm it.

Power analysis:

| n per arm | p for a 14.8% → 23.4% effect |
|---|---|
| 168 (as built) | 0.0518 |
| 250 | 0.0167 |
| 400 | 0.0017 |
| 560 | 0.0003 |

The fixture ran 3,600 cases over two quarters. Heartflow processed **84,491 revenue cases in
Q2 2026 alone** — roughly 47× the volume, per quarter. The fixture was not representative of
the statistical power a production deployment would actually have.

Rescaled to 12,000 cases. The regression now reads **lift 1.48, p = 0.0026, confirmed**, with
every other manufacturer stable.

**The transferable lesson: the significance gate was designed before anyone asked whether the
data could support it.** Designing a detection threshold without a power analysis is how you
build a monitor that is correctly calibrated and permanently silent.

## Final state

| Measure | Value |
|---|---|
| cases on the spine | 12,000 |
| actionable-correction rate | 12.21% |
| automation frontier @ 8% tolerance | 1 of 23 strata, 18% of volume, residual 5.61% |
| escalated subgroup disparities | 3 |
| case-mix variance explained (rejection) | 1.4% |
| confirmed release regressions | 1 (Canon v4.1.0) |

Tests: **11 data + 77 fast + 17 browser = 105**, plus the agent eval.
