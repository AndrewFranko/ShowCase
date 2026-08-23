# Development workflow — the iteration log

Each iteration ran the same loop: **business analysis → architecture → development → test →
iterate**. Each one questioned the previous one rather than extending it.

| # | Question asked | Outcome |
|---|---|---|
| [01](01-case-mix-confounding.md) | Is the release comparison we shipped trustworthy? | **No.** Case mix shifts between releases. Added direct standardisation. |
| [02](02-subgroup-disparity.md) · [results](02-results.md) | Does the average hide a subgroup? | **Yes.** Added FDR-controlled disparity monitoring with conjunctive escalation. |
| [03](03-attributable-rejection.md) · [results](03-results.md) | Is the same confounding present in rejection? | **No.** Hypothesis falsified — case mix explains 1.4% of variance. |
| [04](04-evidence-pack.md) | Can a regulator cite any of this? | **No.** Added content-addressed, verifiable evidence packs. |
| [05](05-agent-evaluation.md) · [results](05-results.md) | Does an agent reading it reach the right conclusion? | **Not necessarily.** Added a ground-truth-anchored eval harness. |
| [06](06-local-deploy.md) | Does it survive a real deployment boundary? | **No.** An orphaned server silently served stale code behind green tests; `up` now refuses to adopt a stranger's process. |
| [07](07-dagster-execution.md) | Does the Dagster path actually execute? | See file — written by the execution run itself. |
| [08](08-docker-execution.md) | Does the container path actually build? | See file — honest record either way. |

## What each iteration changed

**01 — Case-mix confounding.** Releases are separated in time and case mix moves with time,
so a crude comparison measures "did the cases get harder" alongside "did the model get worse".
Direct standardisation against a fixed reference mix. Chose it over logistic regression and
propensity matching on explainability grounds: Quality needs a rate they can put beside
another rate, not a coefficient. The Canon regression survived and strengthened
(lift 1.71 → 1.83); v4.1.3's fix turned out better than crude showed (0.63 → 0.54).

**02 — Subgroup disparity.** The averaging that iteration 01 fixed is also what hides a
subgroup. Six axes, ~11 comparisons, Benjamini–Hochberg FDR at q = 0.10, Wilson intervals,
and a **conjunctive** escalation rule — significant AND ≥1.5× AND ≥30 cases. Chose BH over
Bonferroni because this is a screening tool: family-wise error control would make real
disparities on small arms undetectable. Null controls (`detector`, `site_class`) came back
null, which is the evidence the monitor isn't manufacturing findings.

**03 — Attributable rejection.** *The hypothesis was wrong, and that was the finding.*
Premise: ranking sites by raw rejection is unfair to sites with harder patients. Measured:
case mix explains **1.4%** of between-site variance, and the top-10 worklist is identical
either way. Rejection is technique-dominated — motion artifact, which matches the published
~78% figure. So the adjustment is a **confirmatory control, not a corrective one**: its value
is proving the raw worklist is fair, which matters the first time a site says "our patients
are sicker". The endpoint now returns `case_mix_variance_explained` so a reader knows how
much to trust the ranking.

**04 — Evidence packs.** A number in a dashboard is not evidence. Content-addressed JSON
carrying the claim, the exact population (hashed case IDs), the method, the code version, a
warehouse fingerprint, the stated limitations, and a manifest hash. The hash covers inputs and
result but not the timestamp, so identical warehouse state produces an identical hash — which
makes reproducibility testable rather than asserted. Recording the population also closes the
gap their own 510(k) leaves: a validation library that *"aims to prevent"* contamination is a
procedure; a recorded population hash is checkable.

**05 — Agent evaluation.** Governance constrains what an agent *can reach*; nothing measured
what it *concludes*. Ground truth recomputed from the warehouse at eval time (never frozen
strings), scored arithmetically (never LLM-as-judge), across three independent dimensions —
tool selection, numeric fidelity, interpretation. Ships with a deterministic reference agent
(positive control) and a naive agent that makes exactly the documented mistakes (negative
control). Reference 6/6, naive 0/6.

## Three findings worth keeping

**Adjusting reflexively is as wrong as never adjusting.** Case mix materially confounded
actionable-correction rate (iteration 01) and barely touched rejection (iteration 03).
Different outcomes have different confounding structures. Each has to be checked — and the
check is cheap once the spine exists, which is an argument for the spine.

**A detection threshold designed without a power analysis is a monitor that is correctly
calibrated and permanently silent.** Iteration 05 found the fixture ran 3,600 cases where
Heartflow processes 84,491 per quarter; the planted regression sat at p = 0.0588 until the
fixture was rescaled to representative volume. The significance gate was built in iteration 00
and nobody asked whether the data could support it until iteration 05.

**Ties break reproducibility.** `ORDER BY rate` with no tiebreaker returned tied strata in
arbitrary order, so an "immutable" evidence pack hashed differently across runs of identical
data. Caught by the reproducibility test one iteration after the packs were built. An
evidence artifact that fails its own verification discredits every pack filed beside it.

## Running it

```bash
make all                          # seed, build, data tests, fast suite
make e2e                          # in-process browser suite
make deploy && make e2e-deployed  # production-shaped deploy + browser suite against it
python -m spine.agent_eval        # agent evaluation
```

Tests: 11 data · 77 fast · in-process browser · 26 deployed-browser · agent eval (6 cases × 2 agents).
