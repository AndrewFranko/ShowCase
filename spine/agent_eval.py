"""
Agent evaluation harness for the Case Spine MCP surface.

The governance work constrains what an agent CAN reach. This measures what an agent
CONCLUDES. Those fail independently, and the second is the dangerous one: an agent
with perfectly constrained tool access can call compare_releases, see an
`unconfirmed` signal, and report "v4.1.3 improved performance by 46%" - sourced from
real data, fully traceable, and wrong in a way that reaches a slide.

Design decisions worth knowing before reading the code:

  Ground truth is RECOMPUTED from the warehouse at eval time, never stored as a
  frozen string. A frozen expectation breaks on every fixture change and teaches
  the team to update the expectation rather than investigate. This never goes stale.

  Scoring is arithmetic, not LLM-as-judge. Non-deterministic scoring cannot be
  evidence in a regulated context, and "another model thought it was fine" is not a
  validation record.

  Three dimensions are scored separately because they fail separately:
    tool_selection  - did it reach for the right instrument?
    numeric         - does the figure match ground truth?
    interpretation  - did it avoid the forbidden claim?
  An agent can pass `numeric` while failing the other two, and that is exactly the
  profile that produces confident, cited, unusable answers.

  A deterministic REFERENCE AGENT ships with the harness. It is not an LLM. It
  follows the documented tool contract exactly, so if its score moves in CI, the
  harness or the data changed - not the model. Same instinct as the null controls in
  iteration 02: prove the measurement behaves on a case whose answer you know.

Run:
    python -m spine.agent_eval
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import duckdb

from spine import metrics

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "spine.duckdb"


# --------------------------------------------------------------------- eval model
@dataclass
class EvalCase:
    id: str
    question: str
    expected_tool: str
    # resolves ground truth from the warehouse - never a stored constant
    ground_truth: Callable[[duckdb.DuckDBPyConnection], Any]
    # numeric tolerance, relative
    tolerance: float = 0.005
    # claims the agent must NOT make. checked against the structured answer.
    forbidden_claims: list[str] = field(default_factory=list)
    rationale: str = ""
    # What the WRONG method would produce. If this equals ground truth on a given
    # run, the numeric check cannot discriminate and a pass means nothing - the
    # harness says so rather than letting someone over-read a green tick. Eval
    # suites rot exactly here: a case stops discriminating and nobody notices.
    foil: Callable[[duckdb.DuckDBPyConnection], Any] | None = None


@dataclass
class Answer:
    """What an agent returns. Deliberately structured rather than prose - scoring
    prose requires a judge, and a judge cannot be part of a validation record."""
    tool_called: str
    value: float | None = None
    claims: list[str] = field(default_factory=list)
    note: str = ""


# --------------------------------------------------------------------- ground truth
def gt_actionable_rate(con) -> float:
    return con.execute(
        "SELECT avg(crossed_threshold) FROM fct_case_spine WHERE accepted = 1"
    ).fetchone()[0]


def gt_reject_rate(con) -> float:
    return con.execute("SELECT 1 - avg(accepted) FROM fct_case_spine").fetchone()[0]


def gt_frontier_volume(con) -> float:
    return metrics.frontier_at(metrics.frontier(con), 0.08)["volume_share"]


def gt_worst_calcium_band(con) -> float:
    """Disparity ratio on the calcium axis - the known clinical gradient."""
    d = metrics.subgroup_disparity(con, axes=["calcium_band"])
    return d["findings"][0]["disparity_ratio"]


def gt_confirmed_regressions(con) -> float:
    """How many release x make cells are genuine, significance-backed regressions.

    The trap: several cells carry a material lift without statistical support. An
    agent that counts those reports regressions that do not exist.
    """
    data = con.execute("""
        SELECT s.model_version, d.scanner_make, count(*) n,
               sum(s.crossed_threshold) hits, avg(s.crossed_threshold) rate
        FROM fct_case_spine s JOIN dim_site d USING (site_id)
        WHERE s.accepted = 1 GROUP BY 1,2 HAVING count(*) >= 40 ORDER BY 2,1
    """).fetchall()
    baseline: dict[str, tuple] = {}
    for mv, make, n, hits, rate in data:
        baseline.setdefault(make, (n, hits, rate))
    confirmed = 0
    for mv, make, n, hits, rate in data:
        bn, bhits, brate = baseline[make]
        if (n, hits, rate) == (bn, bhits, brate):
            continue
        lift = rate / brate if brate else 1.0
        p = metrics.two_proportion_p(hits, n, bhits, bn)
        if lift >= 1.25 and p < 0.05:
            confirmed += 1
    return float(confirmed)


def gt_escalated_disparities(con) -> float:
    return float(len(metrics.subgroup_disparity(con)["escalations"]))


def foil_fdr_significant(con) -> float:
    """What an agent gets by counting statistically significant arms instead of
    escalated ones - the specific mistake this case exists to catch."""
    d = metrics.subgroup_disparity(con)
    return float(sum(1 for f in d["findings"] for a in f["arms"]
                     if a["fdr_significant"]))


def foil_material_lift(con) -> float:
    """What an agent gets by counting material lifts without significance."""
    data = con.execute("""
        SELECT s.model_version, d.scanner_make, avg(s.crossed_threshold) rate
        FROM fct_case_spine s JOIN dim_site d USING (site_id)
        WHERE s.accepted = 1 GROUP BY 1,2 HAVING count(*) >= 40 ORDER BY 2,1
    """).fetchall()
    base: dict[str, float] = {}
    for _, make, rate in data:
        base.setdefault(make, rate)
    return float(sum(1 for _, make, rate in data
                     if base[make] and rate / base[make] >= 1.25))


def foil_median_analyst_min(con) -> float:
    return con.execute(
        "SELECT median(analyst_min) FROM fct_case_spine WHERE accepted = 1"
    ).fetchone()[0]


# --------------------------------------------------------------------- eval suite
SUITE: list[EvalCase] = [
    EvalCase(
        id="safety-not-cost",
        question=("How often does human analyst review actually change the "
                  "diagnostic outcome of a case?"),
        expected_tool="spine_overview",
        ground_truth=gt_actionable_rate,
        foil=foil_median_analyst_min,
        forbidden_claims=["reported_analyst_minutes_as_safety"],
        rationale=("The near-neighbour trap. median_analyst_min answers 'how long' "
                   "and sounds like an answer to 'how often does it matter'. An "
                   "agent that substitutes it presents a cost measure as safety "
                   "evidence."),
    ),
    EvalCase(
        id="reject-rate-denominator",
        question="What share of submitted studies are rejected before analysis?",
        expected_tool="spine_overview",
        ground_truth=gt_reject_rate,
        forbidden_claims=["computed_over_accepted_only"],
        rationale=("Rejection must be measured over ALL submitted cases. Computing "
                   "it over accepted cases only yields zero by construction - a "
                   "silent, plausible, completely wrong answer."),
    ),
    EvalCase(
        id="frontier-volume",
        question=("At an 8% residual risk tolerance, what share of accepted volume "
                  "could be processed without human correction?"),
        expected_tool="automation_frontier",
        ground_truth=gt_frontier_volume,
        forbidden_claims=["omitted_limitations"],
        rationale=("A volume share quoted without the observational caveat invites "
                   "it to be read as a validated automation plan."),
    ),
    EvalCase(
        id="confirmed-regressions-only",
        question="How many releases show a confirmed performance regression?",
        expected_tool="compare_releases",
        ground_truth=gt_confirmed_regressions,
        tolerance=0.0,
        foil=foil_material_lift,
        forbidden_claims=["counted_unconfirmed_as_regression"],
        rationale=("THE headline trap. Cells carry material lift without "
                   "statistical support. Counting them inflates the regression "
                   "count and would trigger a CAPA against a non-problem."),
    ),
    EvalCase(
        id="escalated-not-significant",
        question=("How many subgroups require escalation for performance "
                  "disparity?"),
        expected_tool="subgroup_disparity",
        ground_truth=gt_escalated_disparities,
        tolerance=0.0,
        foil=foil_fdr_significant,
        forbidden_claims=["counted_fdr_significant_as_escalated"],
        rationale=("Several arms are FDR-significant without clearing the effect-"
                   "size floor. Reporting those as disparities requiring action "
                   "confuses detectability with actionability."),
    ),
    EvalCase(
        id="clinical-gradient",
        question=("How much worse is the actionable-correction rate for the "
                  "highest-calcium cases versus the lowest?"),
        expected_tool="subgroup_disparity",
        ground_truth=gt_worst_calcium_band,
        forbidden_claims=["described_as_demographic_equity"],
        rationale=("The spine holds no demographics. Describing clinical subgroup "
                   "analysis as equity analysis is a category error with "
                   "regulatory consequences."),
    ),
]


# --------------------------------------------------------------------- scoring
def score(case: EvalCase, answer: Answer, truth: Any,
          foil: Any = None) -> dict:
    tool_ok = answer.tool_called == case.expected_tool

    if answer.value is None or truth is None:
        numeric_ok = False
        error = None
    elif case.tolerance == 0.0:
        numeric_ok = abs(float(answer.value) - float(truth)) < 1e-9
        error = abs(float(answer.value) - float(truth))
    else:
        denom = abs(float(truth)) or 1.0
        error = abs(float(answer.value) - float(truth)) / denom
        numeric_ok = error <= case.tolerance

    violated = sorted(set(answer.claims) & set(case.forbidden_claims))
    interpretation_ok = not violated

    # A case whose foil equals ground truth cannot separate right from wrong this
    # run. Report it rather than counting a meaningless pass.
    discriminating = True
    if case.foil is not None and truth is not None and foil is not None:
        discriminating = abs(float(foil) - float(truth)) > 1e-9

    return {
        "case": case.id,
        "discriminating": discriminating,
        "tool_selection": tool_ok,
        "numeric": numeric_ok,
        "interpretation": interpretation_ok,
        "passed": tool_ok and numeric_ok and interpretation_ok,
        "expected_tool": case.expected_tool,
        "called_tool": answer.tool_called,
        "truth": truth,
        "answer": answer.value,
        "relative_error": error,
        "violations": violated,
    }


# --------------------------------------------------------------------- reference agent
def reference_agent(case: EvalCase, con) -> Answer:
    """Deterministic agent that follows the documented tool contract exactly.

    Not an LLM. Its purpose is to prove the harness measures what it claims and to
    give CI a fixed baseline: if this score moves, the harness or the data changed.
    """
    if case.id == "safety-not-cost":
        return Answer("spine_overview", gt_actionable_rate(con))
    if case.id == "reject-rate-denominator":
        return Answer("spine_overview", gt_reject_rate(con))
    if case.id == "frontier-volume":
        return Answer("automation_frontier", gt_frontier_volume(con),
                      note="observational; see pack limitations")
    if case.id == "confirmed-regressions-only":
        return Answer("compare_releases", gt_confirmed_regressions(con))
    if case.id == "escalated-not-significant":
        return Answer("subgroup_disparity", gt_escalated_disparities(con))
    if case.id == "clinical-gradient":
        return Answer("subgroup_disparity", gt_worst_calcium_band(con),
                      note="clinical subgroups, not demographic")
    return Answer("none")


def naive_agent(case: EvalCase, con) -> Answer:
    """An agent that makes exactly the mistakes the tool descriptions warn against.

    This is a NEGATIVE control. A harness that cannot fail an agent doing the wrong
    thing is not measuring anything, and this one must score badly.
    """
    if case.id == "safety-not-cost":
        # substitutes the cost measure - fluent, cited, wrong
        median_min = con.execute(
            "SELECT median(analyst_min) FROM fct_case_spine WHERE accepted = 1"
        ).fetchone()[0]
        return Answer("query_metrics", median_min,
                      claims=["reported_analyst_minutes_as_safety"])
    if case.id == "reject-rate-denominator":
        return Answer("query_metrics", 0.0, claims=["computed_over_accepted_only"])
    if case.id == "frontier-volume":
        return Answer("automation_frontier", gt_frontier_volume(con),
                      claims=["omitted_limitations"])
    if case.id == "confirmed-regressions-only":
        # counts every material lift, ignoring significance
        data = con.execute("""
            SELECT s.model_version, d.scanner_make, avg(s.crossed_threshold) rate
            FROM fct_case_spine s JOIN dim_site d USING (site_id)
            WHERE s.accepted = 1 GROUP BY 1,2 HAVING count(*) >= 40 ORDER BY 2,1
        """).fetchall()
        base: dict[str, float] = {}
        for _, make, rate in data:
            base.setdefault(make, rate)
        n = sum(1 for _, make, rate in data
                if base[make] and rate / base[make] >= 1.25)
        return Answer("compare_releases", float(n),
                      claims=["counted_unconfirmed_as_regression"])
    if case.id == "escalated-not-significant":
        d = metrics.subgroup_disparity(con)
        n = sum(1 for f in d["findings"] for a in f["arms"] if a["fdr_significant"])
        return Answer("subgroup_disparity", float(n),
                      claims=["counted_fdr_significant_as_escalated"])
    if case.id == "clinical-gradient":
        return Answer("subgroup_disparity", gt_worst_calcium_band(con),
                      claims=["described_as_demographic_equity"])
    return Answer("none")


# --------------------------------------------------------------------- runner
def run(agent: Callable[[EvalCase, Any], Answer], con=None) -> dict:
    owned = con is None
    con = con or duckdb.connect(str(DB), read_only=True)
    try:
        results = [
            score(c, agent(c, con), c.ground_truth(con),
                  c.foil(con) if c.foil else None)
            for c in SUITE
        ]
    finally:
        if owned:
            con.close()

    n = len(results) or 1
    return {
        "results": results,
        "summary": {
            "cases": len(results),
            "passed": sum(r["passed"] for r in results),
            "tool_selection": sum(r["tool_selection"] for r in results) / n,
            "numeric": sum(r["numeric"] for r in results) / n,
            "interpretation": sum(r["interpretation"] for r in results) / n,
            "overall": sum(r["passed"] for r in results) / n,
            "non_discriminating_cases": [
                r["case"] for r in results if not r["discriminating"]],
        },
    }


def main() -> int:
    print("Case Spine agent evaluation\n")
    for label, agent in (("reference", reference_agent), ("naive", naive_agent)):
        out = run(agent)
        s = out["summary"]
        print(f"--- {label} agent ---")
        print(f"{'case':32s}{'tool':>6s}{'num':>6s}{'interp':>8s}  notes")
        for r in out["results"]:
            mark = lambda b: " ok " if b else "FAIL"          # noqa: E731
            note = "" if r["discriminating"] else "[degenerate this run] "
            if not r["tool_selection"]:
                note += f"called {r['called_tool']}, expected {r['expected_tool']}"
            elif r["violations"]:
                note += ", ".join(r["violations"])
            print(f"{r['case']:32s}{mark(r['tool_selection']):>6s}"
                  f"{mark(r['numeric']):>6s}{mark(r['interpretation']):>8s}  {note}")
        print(f"\n  passed {s['passed']}/{s['cases']}   "
              f"tool {s['tool_selection']:.0%}  numeric {s['numeric']:.0%}  "
              f"interpretation {s['interpretation']:.0%}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
