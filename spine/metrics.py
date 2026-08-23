"""
Canonical metric definitions.

Every metric in this project is defined exactly once, here, and every consumer
reads it from this module. That is the whole point of a semantic layer: Operations,
Quality and Engineering cannot end up quoting three different numbers for the same
thing in the same meeting.

In production these definitions live in Cube (semantic/model/cubes/case_spine.yml)
so that Power BI and Tableau read the identical definition over Cube's SQL API.
This module is the reference implementation the Cube schema is tested against -
see tests/test_metrics.py, which asserts the two agree.

The metric that matters:

    actionable_correction_rate
        Of accepted cases, the share where analyst correction moved an FFR value
        across the 0.80 decision threshold. It answers "did the human change the
        answer?" - a safety question - rather than "how long did the human take?",
        which is a cost question. Automation evidence needs the former.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# Cases that reached an analyst. Rejected cases never do, so including them
# would dilute every rate below.
ACCEPTED = "accepted = 1"

MEASURES: dict[str, str] = {
    "cases":                       "count(*)",
    "accepted_cases":              f"count(*) FILTER ({ACCEPTED})",
    "rejected_cases":              "count(*) FILTER (accepted = 0)",
    "reject_rate":                 "1.0 - avg(accepted)",
    "actionable_corrections":      f"sum(crossed_threshold) FILTER ({ACCEPTED})",
    "actionable_correction_rate":  f"avg(crossed_threshold) FILTER ({ACCEPTED})",
    "grey_zone_rate":              f"avg(grey_zone) FILTER ({ACCEPTED})",
    "median_analyst_min":          f"median(analyst_min) FILTER ({ACCEPTED})",
    "median_turnaround_min":       "median(turnaround_min)",
    "median_abs_delta_ffr":        f"median(abs_delta_ffr) FILTER ({ACCEPTED})",
    "median_autoseg_confidence":   "median(autoseg_confidence)",
    "median_heart_rate":           "median(heart_rate)",
    "nitro_rate":                  "avg(nitro_given)",
    "median_plaque_volume":        f"median(total_plaque_volume_mm3) FILTER ({ACCEPTED})",
}

DIMENSIONS = [
    "stratum", "model_version", "detector_at_scan", "scanner_key",
    "site_id", "reject_reason", "case_day",
    # subgroup axes (iteration 02)
    "calcium_band", "motion_band", "bmi_band", "site_class", "stent_present",
]

# Axes monitored for performance disparity. Clinical and operational only - the
# spine carries no demographics, so this is NOT demographic equity analysis and
# must not be presented as such. Real demographic monitoring would need a governed
# join to a source that holds those attributes, with its own privacy review.
SUBGROUP_AXES = [
    "calcium_band", "motion_band", "bmi_band",
    "detector_at_scan", "site_class", "stent_present",
]

# Escalation thresholds, predetermined rather than chosen after seeing results.
FDR_Q = 0.10          # Benjamini-Hochberg false discovery rate
MIN_DISPARITY = 1.5   # ratio of worst arm to best arm
MIN_ARM_N = 30        # smallest arm must carry this many cases

# Strata thinner than this are suppressed. Two reasons: a rate over eight cases is
# noise, and small cells are a re-identification risk even on pseudonymous data.
MIN_STRATUM_N = 12


def select(measures: list[str], by: list[str] | None = None,
           where: str | None = None, having: str | None = None,
           order: str | None = None, limit: int | None = None) -> str:
    """Compose a query from the canonical definitions.

    Callers never write their own aggregate expressions - they name measures. This
    is what stops `actionable_correction_rate` from being reimplemented slightly
    differently in the fourth dashboard someone builds.
    """
    unknown = [m for m in measures if m not in MEASURES]
    if unknown:
        raise KeyError(f"unknown measure(s): {unknown}. Known: {sorted(MEASURES)}")
    bad_dims = [d for d in (by or []) if d not in DIMENSIONS]
    if bad_dims:
        raise KeyError(f"unknown dimension(s): {bad_dims}. Known: {DIMENSIONS}")

    cols = list(by or []) + [f"{MEASURES[m]} AS {m}" for m in measures]
    sql = f"SELECT {', '.join(cols)} FROM fct_case_spine"
    if where:
        sql += f" WHERE {where}"
    if by:
        sql += f" GROUP BY {', '.join(by)}"
    if having:
        sql += f" HAVING {having}"
    if order:
        sql += f" ORDER BY {order}"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return sql


def two_proportion_p(x1: int, n1: int, x2: int, n2: int) -> float:
    """Two-sided p-value for a difference in two proportions (normal approximation).

    This exists because a drift monitor that fires on a raw ratio is worse than no
    drift monitor. On small per-release, per-manufacturer cells a 1.3x lift arises
    by chance routinely; alerting on it trains everyone to ignore the alerts, which
    is how monitoring dies. A release is only flagged when the effect is both
    material (lift threshold) and supported (p < 0.05).

    Normal approximation is adequate here - cells below ~40 cases are filtered out
    before this is called, so np and n(1-p) are comfortably above 5.
    """
    if n1 == 0 or n2 == 0:
        return 1.0
    p1, p2 = x1 / n1, x2 / n2
    pooled = (x1 + x2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = abs(p1 - p2) / se
    # two-sided tail of the standard normal
    return math.erfc(z / math.sqrt(2))


@dataclass(frozen=True)
class Stratum:
    stratum: str
    accepted_cases: int
    actionable_corrections: int
    actionable_correction_rate: float
    median_analyst_min: float
    share: float = 0.0
    cumulative_share: float = 0.0


def frontier(con) -> list[Stratum]:
    """The automation frontier: strata ordered by residual risk, with cumulative volume.

    This is the artifact a Predetermined Change Control Plan needs - the argument
    that a defined subset of cases can be processed without human correction, with
    a stated and monitored residual rate.
    """
    rows = con.execute(select(
        ["accepted_cases", "actionable_corrections",
         "actionable_correction_rate", "median_analyst_min"],
        by=["stratum"],
        where=ACCEPTED,
        having=f"count(*) >= {MIN_STRATUM_N}",
        # `stratum` is a TOTAL-ordering tiebreaker, and it is load-bearing.
        #
        # Strata tie on rate routinely (small integer counts over small
        # denominators). Without a tiebreaker the database returns tied rows in
        # arbitrary order, so the frontier - and therefore the cumulative volume
        # share, and therefore the evidence pack hash - is non-deterministic.
        # An "immutable" evidence artifact that hashes differently on two runs of
        # identical data is worse than no artifact: it fails its own verification
        # and destroys trust in every pack alongside it.
        #
        # Caught by test_evidence_pack_is_reproducible. See workflow/05.
        order="actionable_correction_rate ASC, stratum ASC",
    )).fetchall()

    total = sum(r[1] for r in rows) or 1
    out, cum = [], 0.0
    for stratum, n, cr, rate, med in rows:
        share = n / total
        cum += share
        out.append(Stratum(stratum, n, cr, rate, med, share, cum))
    return out


def standardised_rate(con, where: str, params: list | None = None,
                      reference_where: str = ACCEPTED) -> dict:
    """Directly standardised actionable-correction rate for a subpopulation.

    Answers: what would this cell's rate have been if it had seen the standard case
    mix? Necessary because releases are separated in time, and case mix moves over
    time - so a crude comparison between releases silently measures "did the cases
    get harder" alongside "did the model get worse".

    Standardisation is on `stratum`, which is built from acquisition facts (calcium,
    motion, stent) that the model version cannot influence. That is deliberate and
    it is easy to get backwards: standardising on `autoseg_confidence` would be
    wrong, because confidence is downstream of the model, so adjusting for it would
    subtract the very effect being measured.

    Returns the standardised rate, the crude rate, and the strata that could not be
    matched - an unmatched-weight share above a few percent means the cell does not
    span the reference population and the comparison should be read with care.
    """
    reference = {r[0]: r[1] for r in con.execute(
        f"SELECT stratum, count(*)::DOUBLE FROM fct_case_spine "
        f"WHERE {reference_where} GROUP BY 1").fetchall()}
    total_weight = sum(reference.values()) or 1.0

    cells = con.execute(
        f"SELECT stratum, avg(crossed_threshold), count(*) FROM fct_case_spine "
        f"WHERE {where} GROUP BY 1", params or []).fetchall()
    if not cells:
        return {"standardised_rate": None, "crude_rate": None, "n": 0,
                "reference_coverage": 0.0}

    matched_weight = sum(reference.get(s, 0.0) for s, _, _ in cells)
    numerator = sum(rate * reference.get(s, 0.0) for s, rate, _ in cells)
    n = sum(c for _, _, c in cells)
    crude = sum(rate * c for _, rate, c in cells) / n

    return {
        "standardised_rate": (numerator / matched_weight) if matched_weight else None,
        "crude_rate": crude,
        "n": n,
        # Share of the reference population this cell actually covers. Low coverage
        # means the standardised figure is extrapolating.
        "reference_coverage": matched_weight / total_weight,
    }


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a proportion.

    Not the normal approximation. Subgroup arms get small, and the normal interval
    produces bounds outside [0,1] and undercovers badly at extreme rates - which is
    exactly where a disparity monitor operates. Wilson behaves at the edges.
    """
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def benjamini_hochberg(p_values: list[float], q: float = FDR_Q) -> list[bool]:
    """Benjamini-Hochberg step-up procedure. Returns a rejection mask.

    Controls the expected PROPORTION of false discoveries among flagged findings,
    which is the right target for a screening monitor whose output is "investigate
    these". Bonferroni controls family-wise error instead and, across ~50 subgroup
    comparisons, sets a per-test threshold so severe that real disparities on small
    arms become undetectable.

    q = 0.10 means roughly one in ten flagged findings is expected to be a false
    lead. That is a deliberate, stated trade - not an accident.
    """
    m = len(p_values)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: p_values[i])
    rejected = [False] * m
    max_k = -1
    for rank, idx in enumerate(order, start=1):
        if p_values[idx] <= q * rank / m:
            max_k = rank
    for rank, idx in enumerate(order, start=1):
        if rank <= max_k:
            rejected[idx] = True
    return rejected


def subgroup_disparity(con, axes: list[str] | None = None,
                       where: str = ACCEPTED, params: list | None = None) -> dict:
    """Actionable-correction rate across subgroup arms, with FDR-controlled flagging.

    Escalation is conjunctive and predetermined: an arm is escalated only when it is
    FDR-significant AND the disparity ratio clears MIN_DISPARITY AND the smaller arm
    carries at least MIN_ARM_N cases. A p-value alone on thousands of cases will
    flag a 0.3 percentage-point gap nobody should act on.
    """
    axes = axes or SUBGROUP_AXES
    bad = [a for a in axes if a not in DIMENSIONS]
    if bad:
        raise KeyError(f"unknown subgroup axis: {bad}")

    findings: list[dict] = []
    for axis in axes:
        rows = con.execute(
            f"SELECT {axis} AS level, count(*) AS n, "
            f"sum(crossed_threshold) AS hits, avg(crossed_threshold) AS rate "
            f"FROM fct_case_spine WHERE {where} GROUP BY 1 HAVING count(*) > 0 "
            f"ORDER BY 1", params or []).fetchall()
        arms = [{"level": str(lv), "n": n, "hits": int(h), "rate": r}
                for lv, n, h, r in rows]
        if len(arms) < 2:
            continue

        best = min(arms, key=lambda a: a["rate"])
        for arm in arms:
            lo, hi = wilson_interval(arm["hits"], arm["n"])
            arm.update(ci_low=lo, ci_high=hi)
            arm["disparity_vs_best"] = (arm["rate"] / best["rate"]
                                        if best["rate"] else 1.0)
            arm["p_value"] = (1.0 if arm is best else two_proportion_p(
                arm["hits"], arm["n"], best["hits"], best["n"]))

        findings.append({
            "axis": axis,
            "best_level": best["level"],
            "worst_level": max(arms, key=lambda a: a["rate"])["level"],
            "disparity_ratio": max(a["disparity_vs_best"] for a in arms),
            "arms": arms,
        })

    # One FDR family across every arm of every axis. Correcting per-axis would leak
    # the multiplicity back in through the number of axes.
    flat = [(f, a) for f in findings for a in f["arms"] if a is not None]
    comparisons = [(f, a) for f, a in flat if a["p_value"] < 1.0]
    rejected = benjamini_hochberg([a["p_value"] for _, a in comparisons])

    for (finding, arm), is_sig in zip(comparisons, rejected):
        arm["fdr_significant"] = bool(is_sig)
        arm["escalate"] = bool(
            is_sig
            and arm["disparity_vs_best"] >= MIN_DISPARITY
            and arm["n"] >= MIN_ARM_N)
    for _, arm in flat:
        arm.setdefault("fdr_significant", False)
        arm.setdefault("escalate", False)

    escalations = [{"axis": f["axis"], "level": a["level"], "n": a["n"],
                    "rate": a["rate"], "disparity": a["disparity_vs_best"],
                    "p_value": a["p_value"]}
                   for f in findings for a in f["arms"] if a["escalate"]]

    return {
        "findings": findings,
        "escalations": escalations,
        "policy": {
            "fdr_q": FDR_Q,
            "min_disparity_ratio": MIN_DISPARITY,
            "min_arm_n": MIN_ARM_N,
            "comparisons": len(comparisons),
            "interval": "Wilson score, 95%",
            "note": ("Clinical and operational subgroups only. The spine carries no "
                     "demographics, so this is not demographic equity analysis."),
        },
    }


def frontier_at(strata: list[Stratum], tolerance: float) -> dict:
    """What automating every stratum at or below `tolerance` would buy."""
    eligible = [s for s in strata if s.actionable_correction_rate <= tolerance]
    cases = sum(s.accepted_cases for s in eligible)
    total = sum(s.accepted_cases for s in strata) or 1
    residual = (sum(s.actionable_corrections for s in eligible) / cases) if cases else 0.0
    return {
        "tolerance": tolerance,
        "eligible_strata": len(eligible),
        "total_strata": len(strata),
        "volume_share": cases / total,
        "cases": cases,
        "residual_rate": residual,
        "strata": [s.stratum for s in eligible],
    }
