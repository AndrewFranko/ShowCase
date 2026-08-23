"""
Shadow simulation: replay history under a proposed automation policy.

THE use case behind the whole spine. The program lead's actual Tuesday question is
not "what is the actionable-correction rate" - it is:

    "If we adopt policy P next quarter, what happens? How many analyst-hours come
    back, and - name them - which patients would have received a DIFFERENT answer?"

A policy here is two dials, not one:

  tolerance   which strata qualify (residual actionable-correction rate ceiling) -
              the frontier from the Operations lens.
  guard band  cases whose PRE-correction FFR falls within +/- g of the 0.80
              decision threshold are routed to a human REGARDLESS of stratum.
              This is the clinically obvious refinement the frontier alone misses:
              harm concentrates next to the threshold, so a small guard band buys a
              large harm reduction for a small volume cost. The simulator computes
              that tradeoff curve instead of asserting it.

The output that matters most is the HARM LEDGER: the specific historical cases the
policy would have auto-released with a different classification than the human
delivered - each with its direction. A would-be FALSE NEGATIVE (auto says >0.80,
human said ischemic) is the MAUDE-pattern harm: a patient not referred. A would-be
false positive sends someone toward an unnecessary cath. They are not the same
severity and are never summed into one number here.

Honest framing, carried on every result: this is retrospective replay against
human-corrected ground truth. It estimates what WOULD have shipped differently; it
does not establish prospective non-inferiority. That is what the pack's
limitations say, verbatim.
"""
from __future__ import annotations

from spine import evidence, metrics

THRESHOLD = 0.80
# FTE arithmetic assumptions - stated, not hidden
WINDOW_WEEKS = 26           # the corpus spans ~182 days
PRODUCTIVE_H_PER_WK = 32.5  # 5 days x 6.5 productive hours


def simulate(con, tolerance: float = 0.08, guard: float = 0.0) -> dict:
    """Replay every accepted case under (tolerance, guard).

    Auto-released cases deliver their PRE-correction classification. Harm = the
    auto set's cases whose pre/post classifications differ.
    """
    strata = metrics.frontier(con)
    eligible = [s.stratum for s in strata
                if s.actionable_correction_rate <= tolerance]

    if not eligible:
        auto_rows = []
    else:
        ph = ",".join("?" * len(eligible))
        auto_rows = con.execute(f"""
            SELECT case_id, stratum, site_id, model_version,
                   ffr_pre, ffr_post, crossed_threshold,
                   analyst_min, turnaround_min, grey_zone
            FROM fct_case_spine
            WHERE accepted = 1 AND stratum IN ({ph})
              AND abs(ffr_pre - {THRESHOLD}) > ?
            ORDER BY case_id""", [*eligible, guard]).fetchall()

    total_accepted, total_minutes = con.execute(
        "SELECT count(*), sum(analyst_min) FROM fct_case_spine WHERE accepted = 1"
    ).fetchone()

    n_auto = len(auto_rows)
    minutes_saved = sum(r[7] for r in auto_rows)
    hours_saved = minutes_saved / 60.0

    harm = [r for r in auto_rows if r[6] == 1]
    # Direction is judged against what the HUMAN delivered (ground truth here).
    # post <= threshold: human said ischemic; auto (pre > threshold) says not.
    would_be_fn = [r for r in harm if r[5] <= THRESHOLD < r[4]]
    would_be_fp = [r for r in harm if r[4] <= THRESHOLD < r[5]]

    complaint_cases = {r[0] for r in con.execute(
        "SELECT case_id FROM fct_complaint").fetchall()}

    def ledger_row(r):
        return {
            "case_id": r[0], "stratum": r[1], "site_id": r[2],
            "model_version": r[3], "ffr_pre": r[4], "ffr_post": r[5],
            "direction": ("would_be_false_negative" if r[5] <= THRESHOLD < r[4]
                          else "would_be_false_positive"),
            "distance_from_threshold": round(abs(r[4] - THRESHOLD), 4),
            "has_complaint": r[0] in complaint_cases,
        }

    lo, hi = metrics.wilson_interval(len(harm), n_auto) if n_auto else (0.0, 1.0)

    # SLA effect: an auto case skips the human step entirely
    new_tats = con.execute(f"""
        SELECT median(CASE WHEN accepted = 1
                             AND stratum IN ({",".join("?" * len(eligible)) or "''"})
                             AND abs(ffr_pre - {THRESHOLD}) > ?
                           THEN turnaround_min - analyst_min
                           ELSE turnaround_min END)
        FROM fct_case_spine WHERE accepted = 1""",
        ([*eligible, guard] if eligible else [guard])).fetchone()[0] \
        if eligible else con.execute(
            "SELECT median(turnaround_min) FROM fct_case_spine WHERE accepted = 1"
        ).fetchone()[0]
    old_tat = con.execute(
        "SELECT median(turnaround_min) FROM fct_case_spine WHERE accepted = 1"
    ).fetchone()[0]

    return {
        "policy": {"tolerance": tolerance, "guard_band": guard,
                   "threshold": THRESHOLD, "eligible_strata": eligible},
        "volume": {
            "auto_released": n_auto,
            "human_reviewed": total_accepted - n_auto,
            "auto_share": n_auto / total_accepted if total_accepted else 0.0,
        },
        "capacity": {
            "analyst_hours_returned": round(hours_saved, 1),
            "share_of_all_analyst_time": (minutes_saved / total_minutes
                                          if total_minutes else 0.0),
            "fte_equivalent": round(
                hours_saved / (WINDOW_WEEKS * PRODUCTIVE_H_PER_WK), 2),
            "assumptions": (f"{WINDOW_WEEKS} weeks x "
                            f"{PRODUCTIVE_H_PER_WK} productive h/week"),
        },
        "sla": {
            "median_turnaround_before_min": round(old_tat, 1),
            "median_turnaround_after_min": round(new_tats, 1),
        },
        "harm": {
            "changed_answers": len(harm),
            "rate_in_auto_set": len(harm) / n_auto if n_auto else 0.0,
            "rate_ci95": [round(lo, 5), round(hi, 5)],
            "would_be_false_negatives": len(would_be_fn),
            "would_be_false_positives": len(would_be_fp),
            "note": ("Directions are deliberately never summed: a would-be false "
                     "negative is the MAUDE-pattern harm (ischemia not referred); "
                     "a false positive is an unnecessary referral."),
            "ledger": sorted((ledger_row(r) for r in harm),
                             key=lambda x: (x["direction"] != "would_be_false_negative",
                                            x["distance_from_threshold"])),
        },
        "framing": ("Retrospective replay against human-corrected ground truth. "
                    "Estimates what would have shipped differently; does not "
                    "establish prospective non-inferiority."),
    }


def guard_tradeoff(con, tolerance: float = 0.08,
                   guards: list[float] | None = None) -> list[dict]:
    """The curve that justifies the guard band: harm vs volume as g grows.

    Computed, not asserted - if the fixture's harm did NOT concentrate near the
    threshold this curve would be flat and the guard band would be theatre. The
    monotonicity is also a test invariant.
    """
    out = []
    for g in (guards or [0.0, 0.01, 0.02, 0.03, 0.05, 0.08]):
        r = simulate(con, tolerance=tolerance, guard=g)
        out.append({
            "guard_band": g,
            "auto_released": r["volume"]["auto_released"],
            "auto_share": r["volume"]["auto_share"],
            "hours_returned": r["capacity"]["analyst_hours_returned"],
            "changed_answers": r["harm"]["changed_answers"],
            "would_be_false_negatives": r["harm"]["would_be_false_negatives"],
        })
    return out


def build_policy_pack(con, tolerance: float, guard: float) -> dict:
    """Freeze a simulated policy as a signable evidence pack."""
    r = simulate(con, tolerance=tolerance, guard=guard)
    content = {
        "schema_version": evidence.SCHEMA_VERSION,
        "claim_type": "shadow_policy",
        "claim": (
            f"Policy(tolerance={tolerance:.2%}, guard_band=±{guard:.3f}) would have "
            f"auto-released {r['volume']['auto_released']:,} of "
            f"{r['volume']['auto_released'] + r['volume']['human_reviewed']:,} "
            f"accepted cases ({r['volume']['auto_share']:.1%}), returning "
            f"{r['capacity']['analyst_hours_returned']:,} analyst-hours "
            f"(~{r['capacity']['fte_equivalent']} FTE), with "
            f"{r['harm']['changed_answers']} changed answers "
            f"({r['harm']['would_be_false_negatives']} would-be false negatives)."),
        "result": {k: v for k, v in r.items() if k != "harm"} | {
            "harm": {k: v for k, v in r["harm"].items() if k != "ledger"},
            # the ledger itself is pinned by hash so the pack stays small but the
            # exact patient set remains checkable
            "harm_ledger_case_ids_sha256": evidence.hashlib.sha256(
                ",".join(str(x["case_id"]) for x in r["harm"]["ledger"])
                .encode()).hexdigest(),
        },
        "population": evidence.population(con, metrics.ACCEPTED),
        "policy": r["policy"],
        "method": {
            "replay": "auto-released cases deliver the pre-correction classification",
            "ground_truth": "human-corrected delivered result",
            "interval": "Wilson score, 95%",
        },
        "code_version": evidence.code_version(),
        "spine_fingerprint": evidence.spine_fingerprint(con),
        "limitations": [
            "Retrospective replay; does not establish prospective non-inferiority.",
            "Ground truth is the human-corrected result, which carries its own "
            "error rate.",
            "Capacity arithmetic assumes " + (
                f"{WINDOW_WEEKS} weeks x {PRODUCTIVE_H_PER_WK} productive h/week."),
            "Queueing effects of removing the human step are approximated by "
            "subtracting analyst minutes from turnaround.",
        ],
    }
    return evidence.finalise(content)
