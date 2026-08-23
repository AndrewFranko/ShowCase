# Iteration 05 — Agent evaluation harness

## Business analysis

**The gap.** Iterations 01–04 built a governed MCP surface with nine tools and careful
semantics in every description. Nothing verifies that an agent *uses* it correctly.

The governance work so far constrains what an agent **can** reach. It does nothing about what
an agent **concludes**. Those are different failures, and the second is the dangerous one: an
agent with perfectly constrained tool access can still call `compare_releases`, see an
`unconfirmed` signal, and report "v4.1.3 improved performance by 46%" — sourced entirely from
real data, technically traceable, and wrong in a way that would reach a slide.

**Driver, from their open Agentic AI requisition:**

> "Implement advanced guardrails, **evaluation frameworks, and reasoning validation loops** to
> ensure agent behaviors are safe, deterministic, and highly accurate within a medical context."

Guardrails were iterations 00–04. This is the evaluation framework.

**Why this domain punishes plausible-sounding answers.** Every metric here has a near-neighbour
that sounds equivalent and is not:

| Correct | Plausible substitute | Consequence |
|---|---|---|
| actionable-correction rate | median analyst minutes | Cost measure presented as safety evidence |
| standardised rate | crude rate | Confounded comparison presented as causal |
| escalated disparity | FDR-significant disparity | Statistically real gap presented as actionable |
| confirmed regression | unconfirmed signal | Noise presented as a finding |

An agent that picks the wrong one produces an answer that is fluent, cited, and unusable.

## Architecture

**Decision: ground-truth-anchored eval, not LLM-as-judge.**

Every eval case carries an expected answer *computed directly from the warehouse at eval
time*, not a stored string. So the eval never goes stale when the fixture changes, and
scoring is arithmetic rather than opinion.

| Option | Verdict |
|---|---|
| LLM-as-judge | Rejected. Non-deterministic, and in a regulated context "another model thought it was fine" is not evidence. |
| Frozen expected strings | Rejected. Breaks on every fixture change; teams then update expectations instead of investigating. |
| **Ground truth recomputed from the warehouse** | **Chosen.** Deterministic, self-updating, and the scoring logic is auditable. |

**Decision: score three separate things, because they fail independently.**

1. **Tool selection** — did it call the right tool? An agent answering a safety question with
   `median_analyst_min` fails here even if the number is correct.
2. **Numeric fidelity** — does the reported figure match ground truth within tolerance?
3. **Interpretation guardrails** — did it avoid the forbidden claim? This is where
   `unconfirmed` → "regression" is caught, and it is scored by assertion over the returned
   payload, not by reading prose.

An agent can pass 2 and fail 1 and 3, which is precisely the dangerous profile.

**Decision: the harness ships with a deterministic reference agent.**

A scripted agent that follows the documented tool contract exactly. It is not an LLM. Its job
is to prove the harness measures what it claims, and to give CI a fixed baseline — if the
reference agent's score moves, the *harness or the data* changed, not the model. Real LLM
evaluation plugs into the same interface later.

This is the same instinct as the null controls in iteration 02: before trusting a measurement
on the interesting case, prove it behaves on a case whose answer you already know.

## Implementation

`spine/agent_eval.py` — eval cases, ground-truth resolvers, scorer, reference agent.
Runnable as `python -m spine.agent_eval`.

## Result

See `05-results.md`.

## Closing the loop

Five iterations, and the arc is deliberate: measure the thing (00), check the measurement is
not confounded (01), check it does not hide a subgroup (02), check an adjacent metric for the
same flaw and find it clean (03), freeze it so a regulator can cite it (04), then verify the
machine reading it draws the right conclusion (05).

Each iteration questioned the previous one rather than extending it. Iteration 03 falsified
its own hypothesis; that was the most useful one.
