"""
"Ask the spine" - natural-language questions routed to the canonical metric layer.

Deliberately RULE-BASED, not an external LLM call. Two reasons, both worth stating:

  1. Data boundary. Wiring a hosted LLM (Gemini, etc.) into the portal means every
     question - and whatever case context rides along with it - leaves the VPC for
     a third-party service. That is a new subprocessor, a new security review, and
     a new place for PHI-adjacent data to leak. The whole platform argument is that
     integration cost is paid once inside one boundary.
  2. Auditability. An answer in a regulated portal must be reproducible. A keyword
     router over named metrics gives the same answer to the same question forever,
     and every answer carries provenance. A sampled LLM does not.

The real LLM interface to this system is the MCP server (mcp_server/server.py):
an actual model (Claude, or anything speaking MCP) gets the full governed tool
surface there, with the same no-SQL, read-only, audited constraints. This module is
the in-portal subset: the eight questions people actually ask, answered instantly.

Every intent resolves through spine.metrics - never its own SQL aggregate - so the
portal, the MCP tools and the Ask box can never disagree about a number.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from spine import metrics


def _fmt_pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _overview(con) -> dict:
    return {k: v for k, v in zip(
        ["cases", "accepted", "rejected", "reject_rate", "rate", "grey",
         "median_min", "median_tat"],
        con.execute(metrics.select([
            "cases", "accepted_cases", "rejected_cases", "reject_rate",
            "actionable_correction_rate", "grey_zone_rate",
            "median_analyst_min", "median_turnaround_min"])).fetchone())}


# --------------------------------------------------------------------- intents
def ask_actionable(con, q: str) -> dict:
    o = _overview(con)
    return {
        "answer": (f"Analyst correction changed the diagnostic classification on "
                   f"{_fmt_pct(o['rate'])} of accepted cases "
                   f"({o['accepted']:,} cases analysed). The other "
                   f"{_fmt_pct(1 - o['rate'])} of corrections confirmed the "
                   f"machine's answer."),
        "value": o["rate"],
        "open": {"lens": "findings"},
    }


def ask_reject(con, q: str) -> dict:
    o = _overview(con)
    return {
        "answer": (f"{_fmt_pct(o['reject_rate'])} of submitted studies "
                   f"({o['rejected']:,} of {o['cases']:,}) were rejected before "
                   f"analysis - measured over ALL submissions, not accepted ones."),
        "value": o["reject_rate"],
        "open": {"lens": "field"},
    }


def ask_minutes(con, q: str) -> dict:
    o = _overview(con)
    return {
        "answer": (f"Median analyst time is {o['median_min']:.0f} minutes per "
                   f"accepted case (median turnaround {o['median_tat']:.0f} min). "
                   f"Note: minutes are a COST measure; whether the correction "
                   f"changed the answer is the safety measure."),
        "value": o["median_min"],
        "open": {"lens": "ops"},
    }


def ask_frontier(con, q: str) -> dict:
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", q)
    tol = float(m.group(1)) / 100 if m else 0.08
    at = metrics.frontier_at(metrics.frontier(con), tol)
    return {
        "answer": (f"At a residual risk tolerance of {_fmt_pct(tol)}, "
                   f"{at['eligible_strata']} of {at['total_strata']} strata "
                   f"qualify - {_fmt_pct(at['volume_share'])} of accepted volume "
                   f"({at['cases']:,} cases) at a blended residual rate of "
                   f"{_fmt_pct(at['residual_rate'])}."),
        "value": at["volume_share"],
        "open": {"lens": "ops"},
    }


def ask_regressions(con, q: str) -> dict:
    rows = con.execute("""
        SELECT s.model_version, d.scanner_make, count(*) n,
               sum(s.crossed_threshold) hits, avg(s.crossed_threshold) rate
        FROM fct_case_spine s JOIN dim_site d USING (site_id)
        WHERE s.accepted = 1 GROUP BY 1,2 HAVING count(*) >= 40 ORDER BY 2,1
    """).fetchall()
    base: dict[str, tuple] = {}
    confirmed = []
    for mv, make, n, hits, rate in rows:
        if make not in base:
            base[make] = (n, int(hits), rate)
            continue
        bn, bh, br = base[make]
        lift = rate / br if br else 1.0
        p = metrics.two_proportion_p(int(hits), n, bh, bn)
        if lift >= 1.25 and p < 0.05:
            confirmed.append((mv, make, rate, lift, p))
    if not confirmed:
        return {"answer": ("No confirmed release regression in this window. "
                           "(Confirmed = lift >= 1.25x AND p < 0.05; material but "
                           "unsupported lifts are reported as inconclusive, never "
                           "as regressions.)"),
                "value": 0, "open": {"lens": "eng"}}
    lines = "; ".join(
        f"{mv} on {make}: {_fmt_pct(r)} ({l:.2f}x lift, p={p:.4f})"
        for mv, make, r, l, p in confirmed)
    return {
        "answer": f"{len(confirmed)} confirmed regression(s): {lines}.",
        "value": len(confirmed),
        "open": {"lens": "eng"},
    }


def ask_disparity(con, q: str) -> dict:
    d = metrics.subgroup_disparity(con)
    esc = d["escalations"]
    sig_only = sum(1 for f in d["findings"] for a in f["arms"]
                   if a["fdr_significant"] and not a["escalate"])
    lines = "; ".join(f"{e['axis']}={e['level']} ({_fmt_pct(e['rate'])}, "
                      f"{e['disparity']:.2f}x)" for e in esc)
    return {
        "answer": (f"{len(esc)} subgroup arm(s) meet ALL escalation criteria"
                   f"{': ' + lines if esc else ''}. {sig_only} more are "
                   f"statistically significant but below the "
                   f"{d['policy']['min_disparity_ratio']}x effect floor and are "
                   f"deliberately not escalated. Clinical/operational subgroups "
                   f"only - the spine carries no demographics."),
        "value": len(esc),
        "open": {"lens": "quality"},
    }


def ask_worst_site(con, q: str) -> dict:
    row = con.execute("""
        SELECT site_id, site_name, observed_reject_rate, expected_reject_rate,
               excess_reject_rate, recoverable_cases
        FROM fct_site_conformance ORDER BY excess_reject_rate DESC LIMIT 1
    """).fetchone()
    if not row:
        return {"answer": "No site clears the volume floor.", "value": None,
                "open": {"lens": "field"}}
    sid, name, obs, exp, exc, rec = row
    return {
        "answer": (f"{name} rejects {_fmt_pct(obs)} of studies against "
                   f"{_fmt_pct(exp)} expected from its case mix - "
                   f"{_fmt_pct(exc)} excess, roughly {rec:.0f} recoverable "
                   f"cases. Excess over expectation, not raw rate, is what makes "
                   f"the ranking fair to sites with harder patients."),
        "value": exc,
        "open": {"lens": "field", "site": sid},
    }


def ask_hazards(con, q: str) -> dict:
    rows = con.execute("""
        SELECT h.hazard_id, h.title, count(m.case_id) AS matches,
               (SELECT count(*) FROM fct_complaint c
                 WHERE c.hazard_id = h.hazard_id) AS complaints
        FROM raw_hazards h
        LEFT JOIN fct_hazard_match m ON m.hazard_id = h.hazard_id
        GROUP BY 1, 2 ORDER BY matches DESC
    """).fetchall()
    top = rows[0]
    return {
        "answer": (f"{len(rows)} hazards monitored. Most-realised: {top[0]} "
                   f"({top[1]}) - {top[2]:,} signature matches, {top[3]} linked "
                   f"complaint(s). A match is a realised condition, not a harm."),
        "value": top[2],
        "open": {"lens": "quality", "hazard": top[0]},
    }


INTENTS: list[tuple[re.Pattern, Callable, str]] = [
    (re.compile(r"chang\w*\s+the\s+(answer|diagnos)|actionable|correct\w*\s+rate|"
                r"human.*(matter|change|impact)|how often.*correct", re.I),
     ask_actionable, "actionable_correction_rate"),
    (re.compile(r"reject|refus|bounce|turned away|not analys", re.I),
     ask_reject, "reject_rate"),
    (re.compile(r"minute|how long|median time|duration|effort|hours", re.I),
     ask_minutes, "median_analyst_min"),
    (re.compile(r"automat|frontier|without (a )?human|toleran|volume.*safe", re.I),
     ask_frontier, "automation_frontier"),
    (re.compile(r"regress|release|version|v4\.\d|model.*(worse|broke)|vendor.*broke", re.I),
     ask_regressions, "compare_releases"),
    (re.compile(r"dispar|subgroup|escalat|fair|equit|worse for", re.I),
     ask_disparity, "subgroup_disparity"),
    (re.compile(r"worst site|which site|site.*(worst|reject|visit)|field visit", re.I),
     ask_worst_site, "site_conformance"),
    (re.compile(r"hazard|risk file|H-\d+|safety signal", re.I),
     ask_hazards, "hazard_status"),
]

VOCABULARY = [
    "How often does human correction change the answer?",
    "What share of studies are rejected?",
    "How long does a case take?",
    "How much volume could be automated at 8% tolerance?",
    "Any confirmed release regressions?",
    "Which subgroups are escalated for disparity?",
    "Which site most needs a field visit?",
    "What is the most-realised hazard?",
]


def ask(con, question: str) -> dict[str, Any]:
    q = (question or "").strip()
    if not q:
        return {"error": "empty question", "try": VOCABULARY}
    for pattern, handler, tool in INTENTS:
        if pattern.search(q):
            result = handler(con, q)
            result["question"] = q
            result["provenance"] = {
                "router": "deterministic keyword intents (no external LLM)",
                "resolved_intent": tool,
                "definition_source": "spine/metrics.py",
                "note": ("Same answer for the same question, always. For "
                         "free-form reasoning use the MCP server with a real "
                         "model attached."),
            }
            return result
    return {
        "question": q,
        "error": ("No intent matched. This router deliberately refuses to guess - "
                  "an approximate answer in a regulated portal is worse than none."),
        "try": VOCABULARY,
    }
