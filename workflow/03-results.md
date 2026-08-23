# Iteration 03 — Results

## The hypothesis was wrong, and that is the finding

The iteration was premised on: *ranking sites by raw rejection rate is unfair, because sites
with harder patients reject more regardless of technique.*

Measured, it is not true — at least not for rejection.

| | mean | sd across sites | range |
|---|---|---|---|
| observed reject rate | 8.24% | **5.16 pp** | 0.0 – 22.6% |
| expected from case mix | 8.17% | **0.45 pp** | 7.4 – 9.7% |
| excess | 0.07% | 5.07 pp | — |

**Case mix explains 0.7% of between-site variance in rejection.**

Top-10 by raw rejection and top-10 by excess rejection: **10/10 overlap**. The adjustment
reorders nothing.

## Why, and why it is not a bug

Rejection is dominated by motion artifact, and motion is technique:

| factor | reject rate |
|---|---|
| motion ≥ 1.4 | 13.00% |
| motion < 0.6 | 6.24% |
| no nitroglycerin | 9.28% |
| nitroglycerin given | 7.95% |
| BMI ≥ 35 | 8.70% |
| BMI < 25 | 6.60% |
| Agatston > 967 | 9.36% |
| Agatston < 100 | 8.66% |

The technique factors span 6.8 points. The patient-intrinsic factors span 2.1. This matches
the published picture — motion artifact causes ~78% of rejections — so the fixture is
behaving like reality, not hiding a modelling error.

## What the iteration actually delivers

**A confirmatory control, not a corrective one.** The value is not that it reorders the
worklist. The value is that it *proves the worklist is fair* — which nobody could assert
before, and which matters the first time a site pushes back with "our patients are sicker
than average". Now that claim is checkable in one query, per site, with a number.

So the endpoint returns `case_mix_variance_explained` alongside the worklist, with an
interpretation string. If it is near zero, rank on raw rejection. If it rises — and it will,
if the network's mix diverges — the same endpoint says so without anyone rebuilding anything.

Total recoverable volume across the network: **56 cases** over two quarters, from sites
performing worse than their own case mix predicts.

## Correction to the fixture, made mid-iteration

The first run showed 10/10 overlap for a different and less interesting reason: the generator
drew BMI and calcium independently of site, so every site had identical case mix and there
was nothing to adjust. That is unrealistic — a tertiary centre genuinely sees heavier, more
calcified patients than a suburban clinic.

Added a latent per-site referral severity that scales calcium and BMI. Mean Agatston per site
now spans **100 to 1,402** (sd 237). Re-ran: still 10/10 overlap, now for the *real* reason.
The fix was necessary to make the negative result trustworthy rather than an artifact.

## Contrast with iteration 01, which is the transferable lesson

| | confounding by case mix |
|---|---|
| actionable-correction rate (iter 01) | **material** — shifted lift 1.71 → 1.83, and 0.63 → 0.54 |
| rejection rate (iter 03) | **negligible** — 0.7% of variance |

Different outcomes have different confounding structures. Adjusting reflexively is as wrong
as never adjusting. Each metric has to be checked, and the check is cheap once the spine
exists — which is an argument for the spine, not against the adjustment.

## Regulatory note

Built as **site-level retrospective reporting**, deliberately not a per-case pre-upload gate.
A per-case score that decides whether a study is analysed is a device software function; this
stays observational and therefore under Computer Software Assurance. The per-case version is
the better product and the wrong first move — build the measurement, prove the signal, then
let Regulatory decide whether a gate justifies a submission.
