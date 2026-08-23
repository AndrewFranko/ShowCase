# Iteration 02 — Results

11 comparisons across 6 axes. **3 escalations.**

| Axis | Best | Worst | Disparity | Escalated |
|---|---|---|---|---|
| calcium_band | CAC<100 (9.02%) | CAC>1k (22.44%) | **2.49×** | CAC>1k, CAC 400-1k |
| motion_band | motion lo (9.61%) | motion hi (21.64%) | **2.25×** | motion hi |
| stent_present | no (12.06%) | yes (17.32%) | 1.44× | no |
| bmi_band | BMI<25 (10.80%) | BMI≥35 (15.38%) | 1.43× | no |
| detector_at_scan | EID (12.42%) | PCD (12.65%) | 1.02× | no |
| site_class | hospital (12.31%) | office (12.70%) | 1.03× | no |

## The rows that justify the design

**`stent_present` is FDR-significant (p = 0.0146) and is NOT escalated.** Disparity 1.44×
falls below the 1.5× floor. This is the conjunctive rule doing exactly the job it was built
for: on 3,323 cases a 5-point gap is easily detectable, and detectability is not the same as
actionability. A monitor that escalated this would be technically correct and operationally
useless.

Same story for `bmi_band` at 1.43×.

**`detector_at_scan` and `site_class` are null controls, and they came back null.** 1.02× and
1.03×, neither significant. A disparity monitor that manufactures findings on axes where none
exist cannot be trusted on the axes where they do. These two are the evidence that it isn't
doing that.

**The two escalations that matter are the clinically expected ones.** Calcium burden and
motion artifact are the documented drivers of segmentation difficulty — high calcium
scatters, motion blurs the vessel wall. Recovering that gradient from the data is the
positive control. If the monitor had *not* found it, the monitor would be broken.

## Consequence for iteration 01

The automation frontier now has a second, independent justification. It was built on
composite strata; disparity analysis reaches the same conclusion from single axes. High
calcium and high motion cases are where human correction actually changes the answer, which
is precisely why they sit at the "human required" end of the frontier.

Two methods, different assumptions, same answer. That is worth more in a submission than
either alone.

## Honest limitations

- **No demographics.** The spine carries none, so this cannot speak to demographic equity.
  Presenting it as though it could would be dishonest. Real demographic monitoring needs a
  governed join to a source that holds those attributes, with its own privacy review.
- **q = 0.10 means roughly one in ten flagged findings is a false lead.** That is the stated
  price of not using Bonferroni. It is a screening tool; escalations are triage, not verdicts.
- **Arms are not independent** — a high-calcium case is more likely to also be high-motion.
  BH assumes independence or positive dependence; the latter holds here, so the procedure is
  still valid, but the axes should not be read as six separate experiments.
