"""
Case Spine API.

Six role-scoped lenses over one table. Each endpoint is a projection; none of them
reimplement a metric, they all name measures from spine.metrics.

Auth: in production every route is behind OIDC against the existing identity
provider, and `lens` maps to an IdP group - Operations sees difficulty, Quality
sees hazards and complaints, Engineering sees release effects, Field sees sites.
Nobody receives the union by default. The dependency below is the seam where that
check goes; locally it is a no-op so the thing runs without an IdP.

Regulatory posture: this service is READ ONLY. It has no write path to the case
pipeline and no endpoint that routes, prioritises, or dispositions a case. That is
what keeps it production/quality-system software under FDA Computer Software
Assurance rather than device software. Adding a route that decides which cases skip
human review would change the regime - see validation/csa-validation-plan.md.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import duckdb
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from datetime import datetime, timezone

from spine import evidence, metrics

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "spine.duckdb"
STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Case Spine",
    version="0.1.0",
    description="One case ledger, six lenses. Read-only by design.",
)


def db() -> duckdb.DuckDBPyConnection:
    if not DB.exists():
        raise HTTPException(503, "spine not built - run `python -m spine.build`")
    # read_only so the process cannot mutate the warehouse even by accident
    con = duckdb.connect(str(DB), read_only=True)
    try:
        yield con
    finally:
        con.close()


Con = Annotated[duckdb.DuckDBPyConnection, Depends(db)]


def rows(con, sql: str, params: list | None = None) -> list[dict]:
    cur = con.execute(sql, params or [])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def one(con, sql: str, params: list | None = None) -> dict:
    r = rows(con, sql, params)
    return r[0] if r else {}


# ---------------------------------------------------------------- platform lens
@app.get("/api/overview", tags=["platform"])
def overview(con: Con):
    m = one(con, metrics.select([
        "cases", "accepted_cases", "rejected_cases", "reject_rate",
        "actionable_correction_rate", "grey_zone_rate",
        "median_analyst_min", "median_turnaround_min",
    ]))
    m["sites"] = con.execute("SELECT count(*) FROM dim_site").fetchone()[0]
    m["model_versions"] = con.execute("SELECT count(*) FROM dim_model_version").fetchone()[0]
    m["complaints"] = con.execute("SELECT count(*) FROM fct_complaint").fetchone()[0]
    m["mdr_reportable"] = con.execute(
        "SELECT count(*) FROM fct_complaint WHERE mdr_reportable = 1").fetchone()[0]
    m["hazards"] = con.execute("SELECT count(*) FROM raw_hazards").fetchone()[0]
    m["hazard_matches"] = con.execute("SELECT count(*) FROM fct_hazard_match").fetchone()[0]
    return m


@app.get("/api/case/{case_id}", tags=["platform"])
def case(case_id: int, con: Con):
    """Every fact the spine carries about one case, across all source systems."""
    c = one(con, """
        SELECT s.*, d.site_name, d.region, d.scanner_make, d.scanner_model, d.site_class
        FROM fct_case_spine s JOIN dim_site d USING (site_id)
        WHERE s.case_id = ?""", [case_id])
    if not c:
        raise HTTPException(404, f"case {case_id} not found")
    c["hazards"] = [r["hazard_id"] for r in rows(
        con, "SELECT hazard_id FROM fct_hazard_match WHERE case_id = ? ORDER BY 1", [case_id])]
    c["complaint"] = one(
        con, "SELECT * FROM fct_complaint WHERE case_id = ?", [case_id]) or None
    return c


# ---------------------------------------------------------------- operations lens
@app.get("/api/ops/frontier", tags=["operations"])
def ops_frontier(con: Con, tolerance: float = Query(0.08, ge=0.0, le=1.0)):
    strata = metrics.frontier(con)
    return {
        "at_tolerance": metrics.frontier_at(strata, tolerance),
        "strata": [s.__dict__ for s in strata],
    }


@app.get("/api/ops/telemetry", tags=["operations"])
def telemetry(con: Con):
    """Analyst workflow telemetry — where the effort actually goes.

    This is the original proposal and the foundation everything else sits on: cost
    of revenue is analyst minutes, so the first question is where those minutes go
    and whether the expensive ones are the ones that matter.

    The join that makes it worth building: effort and impact on the same row.
    Throughput dashboards have effort. Nobody has both.
    """
    effort = one(con, """
        SELECT median(analyst_min) AS median_min,
               median(active_min)  AS median_active,
               median(idle_min)    AS median_idle,
               sum(analyst_min) / 60.0 AS total_hours,
               median(edit_count)  AS median_edits,
               avg(analyst_min)    AS mean_min,
               max(analyst_min)    AS max_min,
               quantile_cont(analyst_min, 0.90) AS p90_min,
               quantile_cont(analyst_min, 0.99) AS p99_min
        FROM fct_case_spine WHERE accepted = 1""")

    # minutes bucketed, split by whether the correction changed the answer.
    # The shape of this is the argument: expensive cases are not the ones where
    # the human earns their keep.
    buckets = rows(con, """
        SELECT least(11, (analyst_min / 10)::INT) * 10 AS min_bucket,
               count(*)                                 AS cases,
               sum(crossed_threshold)                   AS actionable,
               avg(crossed_threshold)                   AS actionable_rate,
               sum(analyst_min) / 60.0                  AS hours
        FROM fct_case_spine WHERE accepted = 1
        GROUP BY 1 ORDER BY 1""")

    # cost of the cases where the human confirmed rather than corrected
    wasted = one(con, """
        SELECT sum(analyst_min) / 60.0 AS hours,
               count(*)                AS cases
        FROM fct_case_spine
        WHERE accepted = 1 AND crossed_threshold = 0""")

    confidence = rows(con, """
        SELECT round(autoseg_confidence, 1) AS confidence,
               count(*)                     AS cases,
               median(analyst_min)          AS median_min,
               avg(crossed_threshold)       AS actionable_rate
        FROM fct_case_spine WHERE accepted = 1
        GROUP BY 1 HAVING count(*) >= 20 ORDER BY 1""")

    return {"effort": effort, "by_minutes": buckets,
            "confirmation_cost": wasted, "by_confidence": confidence}


@app.get("/api/ops/segments", tags=["operations"])
def segments(con: Con):
    """Which coronary segments absorb correction effort, and which of those
    corrections actually move a diagnostic value.

    Proximal segments carry the diagnostic weight — a correction to the left main
    or proximal LAD can move an FFR across threshold; one to a distal branch almost
    never does. If effort is concentrated where impact is not, that gap is the
    automation target.
    """
    return rows(con, """
        SELECT seg AS segment,
               count(*)                 AS corrections,
               sum(crossed_threshold)   AS actionable,
               avg(crossed_threshold)   AS actionable_rate,
               median(analyst_min)      AS median_min,
               median(abs_delta_ffr)    AS median_abs_delta
        FROM (SELECT unnest(segments_touched) AS seg, crossed_threshold,
                     analyst_min, abs_delta_ffr
              FROM fct_case_spine WHERE accepted = 1)
        GROUP BY 1 HAVING count(*) >= 30
        ORDER BY corrections DESC""")


@app.get("/api/ops/delta-histogram", tags=["operations"])
def ops_histogram(con: Con, bins: int = 26, max_delta: float = 0.13):
    return rows(con, f"""
        SELECT least({bins - 1}, floor(abs_delta_ffr / ? * {bins}))::INT AS bin,
               count(*) FILTER (crossed_threshold = 0) AS unchanged,
               count(*) FILTER (crossed_threshold = 1) AS crossed
        FROM fct_case_spine WHERE accepted = 1
        GROUP BY bin ORDER BY bin""", [max_delta])


# ---------------------------------------------------------------- quality lens
@app.get("/api/quality/hazards", tags=["quality"])
def hazards(con: Con):
    return rows(con, """
        SELECT h.hazard_id, h.title, h.controls,
               count(m.case_id)                                   AS matches,
               count(m.case_id) * 1.0 /
                 (SELECT count(*) FROM fct_case_spine)            AS match_rate,
               (SELECT count(*) FROM fct_complaint c
                 WHERE c.hazard_id = h.hazard_id)                 AS complaints
        FROM raw_hazards h
        LEFT JOIN fct_hazard_match m ON m.hazard_id = h.hazard_id
        GROUP BY h.hazard_id, h.title, h.controls
        ORDER BY h.hazard_id""")


@app.get("/api/quality/hazards/{hazard_id}/trend", tags=["quality"])
def hazard_trend(hazard_id: str, con: Con):
    """Residual risk per release. This is the number ISO 14971 wants and that most
    risk files can only assert."""
    return rows(con, """
        SELECT v.model_version, v.release_seq,
               count(DISTINCT s.case_id)                          AS cases,
               count(DISTINCT m.case_id)                          AS matches,
               count(DISTINCT m.case_id) * 1.0 /
                 nullif(count(DISTINCT s.case_id), 0)             AS match_rate
        FROM dim_model_version v
        LEFT JOIN fct_case_spine s ON s.model_version = v.model_version AND s.accepted = 1
        LEFT JOIN fct_hazard_match m
               ON m.model_version = v.model_version AND m.hazard_id = ?
        GROUP BY v.model_version, v.release_seq
        ORDER BY v.release_seq""", [hazard_id])


@app.get("/api/quality/disparity", tags=["quality"])
def disparity(con: Con, model_version: str | None = None):
    """Subgroup performance disparity with FDR-controlled flagging.

    Satisfies the "subgroup performance ... performance disparity ... predetermined
    thresholds ... defined escalation path" requirement. Escalation is conjunctive:
    FDR-significant AND disparity >= 1.5x AND the arm carries >= 30 cases. A
    p-value alone on thousands of cases flags gaps nobody should act on.

    Clinical and operational subgroups only - the spine holds no demographics, so
    this is not demographic equity analysis and must not be reported as such.
    """
    where, params = metrics.ACCEPTED, []
    if model_version:
        where += " AND model_version = ?"
        params = [model_version]
    return metrics.subgroup_disparity(con, where=where, params=params)


@app.get("/api/quality/complaints", tags=["quality"])
def complaints(con: Con, hazard_id: str | None = None,
               model_version: str | None = None, site_id: int | None = None):
    """Complaint list, filterable by the joins the spine makes possible.

    The filters are the interconnection: a hazard row links here scoped to its
    complaints, an engineering regression links here scoped to its release, a site
    card links here scoped to its site. Same table, three doors in.
    """
    where, params = [], []
    if hazard_id:
        where.append("hazard_id = ?"); params.append(hazard_id)
    if model_version:
        where.append("model_version = ?"); params.append(model_version)
    if site_id is not None:
        where.append("site_id = ?"); params.append(site_id)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    return rows(con, f"""
        SELECT complaint_id, case_id, complaint_day, complaint_type,
               mdr_reportable, status, hazard_id, reporting_lag_days,
               model_version, site_id, stratum
        FROM fct_complaint {clause} ORDER BY complaint_day""", params)


@app.get("/api/quality/complaints/{complaint_id}/trace", tags=["quality"])
def complaint_trace(complaint_id: int, con: Con):
    """THE cross-reference.

    Resolves complaint -> case -> site -> hazard -> stratum -> trend by release,
    so the question "anecdote or signal?" is answered on arrival. Today this
    traversal spans Smarteeva, the case store, the label store and Ketryx.
    """
    c = one(con, """
        SELECT c.*, d.site_name, d.scanner_make, d.scanner_model
        FROM fct_complaint c JOIN dim_site d USING (site_id)
        WHERE c.complaint_id = ?""", [complaint_id])
    if not c:
        raise HTTPException(404, f"complaint {complaint_id} not found")

    peers = one(con, metrics.select(
        ["accepted_cases", "actionable_corrections", "actionable_correction_rate"],
        where=f"{metrics.ACCEPTED} AND stratum = ?"), [c["stratum"]])
    by_release = rows(con, metrics.select(
        ["accepted_cases", "actionable_correction_rate"],
        by=["model_version"],
        where=f"{metrics.ACCEPTED} AND stratum = ?",
        having="count(*) > 8",
        order="model_version"), [c["stratum"]])
    return {"complaint": c, "stratum_cohort": peers, "by_release": by_release}


# ---------------------------------------------------------------- engineering lens
@app.get("/api/engineering/releases", tags=["engineering"])
def releases(con: Con, min_cases: int = 40):
    """Actionable-correction rate by release and scanner make.

    A regression confined to one manufacturer's reconstructions is invisible in an
    aggregate metric and invisible in throughput metrics. It is visible here only
    because release identity and clinical outcome sit on the same row.
    """
    data = rows(con, f"""
        SELECT s.model_version, d.scanner_make,
               count(*)                                     AS accepted_cases,
               sum(s.crossed_threshold)                     AS actionable_corrections,
               avg(s.crossed_threshold)                     AS actionable_correction_rate,
               median(s.analyst_min)                        AS median_analyst_min
        FROM fct_case_spine s JOIN dim_site d USING (site_id)
        WHERE s.accepted = 1
        GROUP BY 1, 2 HAVING count(*) >= {int(min_cases)}
        ORDER BY 2, 1""")
    # Case mix moves between releases, so a crude comparison measures "did the cases
    # get harder" alongside "did the model get worse". Standardise each cell to the
    # overall accepted case mix before comparing. See workflow/01.
    for r in data:
        std = metrics.standardised_rate(
            con,
            where=("accepted = 1 AND model_version = ? AND site_id IN "
                   "(SELECT site_id FROM dim_site WHERE scanner_make = ?)"),
            params=[r["model_version"], r["scanner_make"]],
        )
        r["standardised_rate"] = std["standardised_rate"]
        r["reference_coverage"] = std["reference_coverage"]

    # baseline is each manufacturer's first release in the window
    baseline: dict[str, dict] = {}
    for r in data:
        baseline.setdefault(r["scanner_make"], r)

    for r in data:
        b = baseline[r["scanner_make"]]
        # Lift is computed on the standardised rate where available - that is the
        # comparison that means something. Crude is retained for transparency so a
        # reviewer can see both.
        rate = r["standardised_rate"] or r["actionable_correction_rate"]
        b_rate = b["standardised_rate"] or b["actionable_correction_rate"]
        r["crude_lift"] = (r["actionable_correction_rate"]
                           / b["actionable_correction_rate"]
                           if b["actionable_correction_rate"] else 1.0)
        r["lift_vs_first_release"] = rate / b_rate if b_rate else 1.0
        r["p_value"] = (
            1.0 if r is b else metrics.two_proportion_p(
                r["actionable_corrections"], r["accepted_cases"],
                b["actionable_corrections"], b["accepted_cases"]))
        # A release is flagged only when the effect is both material AND supported.
        # Ratio alone produces false alarms on small cells, and a monitor that cries
        # wolf gets muted - which is the same as not having one.
        material_up = r["lift_vs_first_release"] >= 1.25
        material_down = r["lift_vs_first_release"] <= 0.80
        significant = r["p_value"] < 0.05
        r["signal"] = ("regression" if material_up and significant else
                       "improved" if material_down and significant else
                       "unconfirmed" if (material_up or material_down) else "stable")
    return data


# ---------------------------------------------------------------- field lens
@app.get("/api/field/sites", tags=["field"])
def sites(con: Con, limit: int = 25, min_cases: int = 8):
    return rows(con, f"""
        SELECT d.site_id, d.site_name, d.region, d.site_class,
               d.scanner_make, d.scanner_model, d.detector_default,
               d.first_field_visit_day,
               count(*)                                     AS cases,
               1 - avg(s.accepted)                          AS reject_rate,
               median(s.heart_rate)                         AS median_heart_rate,
               avg(s.nitro_given)                           AS nitro_rate,
               avg(s.accepted) FILTER (
                   d.first_field_visit_day IS NOT NULL
                   AND s.case_day < d.first_field_visit_day) AS accept_before_visit,
               avg(s.accepted) FILTER (
                   d.first_field_visit_day IS NOT NULL
                   AND s.case_day >= d.first_field_visit_day) AS accept_after_visit
        FROM fct_case_spine s JOIN dim_site d USING (site_id)
        GROUP BY ALL HAVING count(*) >= {int(min_cases)}
        ORDER BY reject_rate DESC LIMIT {int(limit)}""")


@app.get("/api/field/conformance", tags=["field"])
def site_conformance(con: Con, limit: int = 25):
    """Site worklist ranked by rejection in EXCESS of what case mix predicts.

    Also returns `case_mix_variance_explained`: the share of between-site variance
    in rejection attributable to case mix rather than technique. That number tells
    a field manager how much the adjustment matters. If it is near zero, the raw
    ranking is safe to use - and knowing that requires computing the adjustment,
    which is why it is worth having even when it changes nothing.
    """
    sites = rows(con, f"""
        SELECT * FROM fct_site_conformance
        ORDER BY excess_reject_rate DESC LIMIT {int(limit)}""")

    spread = one(con, """
        SELECT var_pop(observed_reject_rate) AS obs_var,
               var_pop(expected_reject_rate) AS exp_var,
               stddev_pop(observed_reject_rate) AS obs_sd,
               stddev_pop(expected_reject_rate) AS exp_sd,
               count(*) AS n_sites,
               sum(recoverable_cases) AS recoverable_cases
        FROM fct_site_conformance""")
    explained = ((spread["exp_var"] / spread["obs_var"])
                 if spread.get("obs_var") else None)
    return {
        "sites": sites,
        "network": {
            **spread,
            "case_mix_variance_explained": explained,
            "interpretation": (
                "rejection is technique-driven, so ranking on raw rejection is "
                "defensible"
                if explained is not None and explained < 0.05 else
                "a material share of the variation is case mix; rank on excess, "
                "not on raw rejection"),
        },
    }


@app.get("/api/field/detector-timeseries", tags=["field"])
def detector_timeseries(con: Con, window: int = 7):
    """Plaque volume per site over time, for sites that migrated detector.

    The summary endpoint returns two medians. That understates the finding: the
    interesting thing is not that the numbers differ, it is that they step on a
    single day, with no error raised, no rejection, and no complaint. Seeing the
    step is the whole point, so this returns the series.
    """
    sites = rows(con, """
        SELECT site_id, site_name, detector_switch_day, scanner_make, scanner_model
        FROM dim_site WHERE detector_switch_day IS NOT NULL ORDER BY site_id""")
    for s in sites:
        s["series"] = rows(con, f"""
            SELECT (case_day / {int(window)})::INT * {int(window)} AS day_bucket,
                   median(total_plaque_volume_mm3) AS median_tpv,
                   count(*)                        AS n,
                   any_value(detector_at_scan)     AS detector
            FROM fct_case_spine
            WHERE accepted = 1 AND site_id = ?
            GROUP BY 1 HAVING count(*) >= 2 ORDER BY 1""", [s["site_id"]])
    # a control site that never migrated, so the reader can see what "no step" looks like
    control = one(con, """
        SELECT d.site_id, d.site_name FROM dim_site d
        JOIN fct_case_spine s USING (site_id)
        WHERE d.detector_switch_day IS NULL AND s.accepted = 1
        GROUP BY 1, 2 ORDER BY count(*) DESC LIMIT 1""")
    if control:
        control["series"] = rows(con, f"""
            SELECT (case_day / {int(window)})::INT * {int(window)} AS day_bucket,
                   median(total_plaque_volume_mm3) AS median_tpv, count(*) AS n
            FROM fct_case_spine WHERE accepted = 1 AND site_id = ?
            GROUP BY 1 HAVING count(*) >= 2 ORDER BY 1""", [control["site_id"]])
    return {"migrated": sites, "control": control, "window_days": window}


@app.get("/api/field/detector-transitions", tags=["field"])
def detector_transitions(con: Con):
    """The silent failure.

    Photon-counting CT measures roughly a third less total plaque volume than
    energy-integrating detectors, and EID-derived thresholds do not transfer. When
    a site migrates, its numbers move for reasons unrelated to its patients, with
    no error raised anywhere.
    """
    return rows(con, """
        SELECT d.site_id, d.site_name, d.detector_switch_day,
               d.scanner_make, d.scanner_model,
               count(*) FILTER (s.case_day <  d.detector_switch_day) AS cases_before,
               count(*) FILTER (s.case_day >= d.detector_switch_day) AS cases_after,
               median(s.total_plaque_volume_mm3) FILTER (
                   s.case_day <  d.detector_switch_day)              AS median_tpv_before,
               median(s.total_plaque_volume_mm3) FILTER (
                   s.case_day >= d.detector_switch_day)              AS median_tpv_after
        FROM fct_case_spine s JOIN dim_site d USING (site_id)
        WHERE d.detector_switch_day IS NOT NULL AND s.accepted = 1
        GROUP BY ALL ORDER BY d.site_id""")


# ---------------------------------------------------------------- interconnect
@app.get("/api/site/{site_id}", tags=["field"])
def site_card(site_id: int, con: Con):
    """Everything the spine knows about one site, from every lens at once.

    This is the payoff of one grain: conformance, hazard realisations, release
    exposure and complaints for a site are four different systems today. Here they
    are one card, linked from anywhere a site name appears.
    """
    site = one(con, """
        SELECT d.*,
               (SELECT count(*) FROM fct_case_spine s
                 WHERE s.site_id = d.site_id)                    AS cases,
               (SELECT 1 - avg(s.accepted) FROM fct_case_spine s
                 WHERE s.site_id = d.site_id)                    AS reject_rate,
               (SELECT median(s.heart_rate) FROM fct_case_spine s
                 WHERE s.site_id = d.site_id)                    AS median_heart_rate,
               (SELECT avg(s.nitro_given) FROM fct_case_spine s
                 WHERE s.site_id = d.site_id)                    AS nitro_rate
        FROM dim_site d WHERE d.site_id = ?""", [site_id])
    if not site:
        raise HTTPException(404, f"site {site_id} not found")
    site["conformance"] = one(con,
        "SELECT * FROM fct_site_conformance WHERE site_id = ?", [site_id]) or None
    site["hazards"] = rows(con, """
        SELECT hazard_id, count(*) AS matches
        FROM fct_hazard_match WHERE site_id = ?
        GROUP BY 1 ORDER BY matches DESC""", [site_id])
    site["by_release"] = rows(con, """
        SELECT model_version, count(*) AS accepted_cases,
               avg(crossed_threshold) AS actionable_correction_rate
        FROM fct_case_spine WHERE site_id = ? AND accepted = 1
        GROUP BY 1 HAVING count(*) >= 8 ORDER BY 1""", [site_id])
    site["complaints"] = rows(con, """
        SELECT complaint_id, complaint_day, complaint_type, mdr_reportable, hazard_id
        FROM fct_complaint WHERE site_id = ? ORDER BY complaint_day""", [site_id])
    return site


@app.get("/api/ask", tags=["platform"])
def ask_endpoint(con: Con, q: str = Query(..., min_length=1, max_length=300)):
    """Ask the spine a question in plain language.

    Deterministic keyword routing over the canonical metric layer answers first -
    same question, same answer, forever, with provenance. Questions the router
    refuses fall back to a grounded LLM (spine/llm.py) ONLY when an API key is
    present in the environment; the model sees a digest of the same governed
    aggregates this API serves, never raw rows or SQL, and its answers carry
    provenance naming the model. No key configured = pure deterministic router.
    """
    from spine.ask import ask
    return ask(con, q)


# ---------------------------------------------------------------- actions
# The write path. Its boundary is deliberate: writes go to a SEPARATE store
# (data/actions.duckdb); the spine connection stays read-only and no endpoint here
# touches a case, a result, or the warehouse. Routing or dispositioning a CASE
# remains forbidden - acknowledging and resolving a FINDING is QMS workflow, the
# same software class as a complaint-handling system. The validation plan records
# this re-assessment; the guardrail tests enforce the narrowed rule.
from pydantic import BaseModel

from spine import actions as actions_store


class TransitionBody(BaseModel):
    to_state: str
    actor: str
    note: str


class SignBody(BaseModel):
    actor: str
    role: str
    note: str = ""
    tolerance: float = 0.08
    guard: float = 0.0


@app.get("/api/actions", tags=["actions"])
def actions_list(state: str | None = None):
    return {"items": actions_store.list_actions(state),
            "states": actions_store.STATES,
            "transitions": {k: sorted(v) for k, v in
                            actions_store.TRANSITIONS.items()}}


@app.post("/api/actions/sync", tags=["actions"])
def actions_sync(con: Con):
    """Derive work items from the current warehouse. Idempotent; never resurrects
    an item a human already moved."""
    return actions_store.sync_findings(con)


@app.post("/api/actions/{action_id}/transition", tags=["actions"])
def actions_transition(action_id: str, body: TransitionBody):
    try:
        result = actions_store.transition(
            action_id, body.to_state, body.actor, body.note)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return result


@app.get("/api/actions/{action_id}/audit", tags=["actions"])
def actions_audit(action_id: str):
    trail = actions_store.audit_trail(action_id)
    if not trail:
        raise HTTPException(404, f"action {action_id} not found")
    return {"action_id": action_id, "events": trail}


@app.post("/api/evidence/{claim}/sign", tags=["actions"])
def evidence_sign(claim: str, body: SignBody, con: Con):
    """Freeze the CURRENT pack for a claim to disk and record who stood behind it.
    Verification precedes signature; an unverifiable pack cannot be signed."""
    if claim == "frontier":
        pack = evidence.build_frontier_pack(con, tolerance=body.tolerance)
    elif claim == "disparity":
        pack = evidence.build_disparity_pack(con)
    elif claim == "policy":
        from spine import shadow as _shadow
        pack = _shadow.build_policy_pack(con, body.tolerance, body.guard)
    else:
        raise HTTPException(404, f"unknown claim {claim!r}")
    try:
        return actions_store.sign_pack(pack, body.actor, body.role, body.note)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/evidence/signed", tags=["actions"])
def evidence_signed():
    """Signed packs, re-verified on every read."""
    return actions_store.list_signed()


# ------------------------------------------------------------ business processes
from spine import investigation as inv_process
from spine import shadow


class OpenInvBody(BaseModel):
    actor: str


class DecideBody(BaseModel):
    decision: str
    actor: str
    rationale: str


@app.get("/api/shadow", tags=["process"])
def shadow_simulate(con: Con,
                    tolerance: float = Query(0.08, ge=0.0, le=1.0),
                    guard: float = Query(0.0, ge=0.0, le=0.2)):
    """Replay history under a proposed automation policy: capacity returned, SLA
    effect, and the named harm ledger - the program lead's actual decision."""
    return shadow.simulate(con, tolerance=tolerance, guard=guard)


@app.get("/api/shadow/tradeoff", tags=["process"])
def shadow_tradeoff(con: Con, tolerance: float = Query(0.08, ge=0.0, le=1.0)):
    return {"tolerance": tolerance,
            "curve": shadow.guard_tradeoff(con, tolerance=tolerance)}


@app.get("/api/investigations", tags=["process"])
def investigations_board(con: Con):
    """Every complaint's position in the 21 CFR 803 process, with its 30-day clock."""
    return inv_process.board(con)


@app.post("/api/investigations/{complaint_id}/open", tags=["process"])
def investigation_open(complaint_id: int, body: OpenInvBody, con: Con):
    try:
        return inv_process.open_investigation(con, complaint_id, body.actor)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/investigations/{complaint_id}/file", tags=["process"])
def investigation_file(complaint_id: int, con: Con):
    try:
        return inv_process.assemble_file(con, complaint_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc))


@app.post("/api/investigations/{complaint_id}/decide", tags=["process"])
def investigation_decide(complaint_id: int, body: DecideBody, con: Con):
    try:
        return inv_process.decide(con, complaint_id, body.decision,
                                  body.actor, body.rationale)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/investigations/{complaint_id}/record", tags=["process"])
def investigation_record(complaint_id: int, con: Con):
    """The sealed record, re-verified on read - closes UX finding F2: the
    process artifact must remain reachable from the product after sealing."""
    import json as _json
    from spine import actions as _actions
    acon = _actions.connect()
    try:
        row = acon.execute(
            "SELECT record_path, decision, decision_late, decided_by "
            "FROM investigations WHERE complaint_id = ? AND state = 'closed'",
            [complaint_id]).fetchone()
    finally:
        acon.close()
    if not row:
        raise HTTPException(404, f"no sealed record for complaint {complaint_id}")
    path = Path(row[0])
    if not path.exists():
        return {"complaint_id": complaint_id, "verification":
                "MISSING - record file deleted after sealing",
                "record_path": row[0]}
    sealed = _json.loads(path.read_text(encoding="utf-8"))
    ok, msg = evidence.verify(sealed)
    return {
        "complaint_id": complaint_id,
        "manifest_sha256": sealed.get("manifest_sha256"),
        "verification": "verified" if ok else f"BROKEN - {msg}",
        "decision": {"outcome": row[1], "late": bool(row[2]), "decided_by": row[3]},
        "sealed_at": sealed.get("generated_at"),
        "record_path": str(path),
        "audit_trail": sealed["content"].get("audit_trail", []),
    }


class ManualItemBody(BaseModel):
    kind: str
    subject: str
    title: str
    evidence: dict = {}
    actor: str


@app.post("/api/actions/manual", tags=["actions"])
def actions_manual(body: ManualItemBody):
    """Raise a work item by hand - the UX loop dogfoods its findings here."""
    try:
        return actions_store.create_manual(
            body.kind, body.subject, body.title, body.evidence, body.actor)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post("/api/investigations/{complaint_id}/close", tags=["process"])
def investigation_close(complaint_id: int, body: OpenInvBody, con: Con):
    try:
        return inv_process.close(con, complaint_id, body.actor)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/briefing", tags=["actions"], response_class=HTMLResponse)
def briefing(con: Con, download: bool = False):
    """A self-contained HTML briefing: the headline numbers, open work, signed
    evidence. The portal's output artifact - something you attach to an email or
    walk into a review with, not a login you hope the audience follows."""

    o = one(con, metrics.select([
        "cases", "accepted_cases", "reject_rate", "actionable_correction_rate",
        "median_analyst_min"]))
    at = metrics.frontier_at(metrics.frontier(con), 0.08)
    d = metrics.subgroup_disparity(con)
    items = actions_store.list_actions()
    signed = actions_store.list_signed()
    fp = evidence.spine_fingerprint(con)
    open_items = [i for i in items if i["state"] in
                  ("open", "acknowledged", "investigating")]
    rows_html = "".join(
        f"<tr><td>{i['kind']}</td><td>{i['title']}</td>"
        f"<td>{i['state']}</td><td>{i['updated_at'][:16]}</td></tr>"
        for i in items) or "<tr><td colspan=4>none</td></tr>"
    signed_html = "".join(
        f"<tr><td>{s['claim_type']}</td><td style='font-family:monospace'>"
        f"{s['manifest_sha'][:16]}…</td><td>{s['actor']} ({s['role']})</td>"
        f"<td>{s['verification']}</td></tr>"
        for s in signed) or "<tr><td colspan=4>none signed yet</td></tr>"
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Case Spine briefing</title><style>
body{{font:14px/1.5 -apple-system,'Segoe UI',sans-serif;max-width:800px;margin:40px auto;
padding:0 20px;color:#111}}h1{{font-size:22px}}h2{{font-size:16px;margin-top:26px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
td,th{{border-bottom:1px solid #ddd;padding:6px 8px;text-align:left}}
.k{{color:#666;font-size:12px}}.warn{{background:#fff6e0;padding:8px 12px;border-left:3px solid #c90}}
</style></head><body>
<h1>Case Spine briefing</h1>
<p class="k">Generated {datetime.now(timezone.utc).isoformat()[:16]}Z ·
warehouse grain {fp['grain_sha256'][:16]} · synthetic data</p>
<div class="warn">Human correction changed the diagnostic classification on
<b>{o['actionable_correction_rate']:.1%}</b> of {o['accepted_cases']:,} accepted cases.
At 8% residual-risk tolerance, <b>{at['volume_share']:.0%}</b> of volume
({at['cases']:,} cases) qualifies for automated handling at a blended residual rate of
{at['residual_rate']:.1%}.</div>
<h2>Findings requiring action ({len(open_items)} open of {len(items)})</h2>
<table><tr><th>Kind</th><th>Finding</th><th>State</th><th>Updated</th></tr>{rows_html}</table>
<h2>Signed evidence ({len(signed)})</h2>
<table><tr><th>Claim</th><th>Manifest</th><th>Signed by</th><th>Verification</th></tr>{signed_html}</table>
<h2>Subgroup escalations ({len(d['escalations'])})</h2>
<p>{('; '.join(f"{e['axis']}={e['level']} ({e['rate']:.1%}, {e['disparity']:.2f}x)"
     for e in d['escalations'])) or 'none'}</p>
<p class="k">Reject rate {o['reject_rate']:.1%} · median analyst time
{o['median_analyst_min']:.0f} min · all numbers reproducible from the stated grain.</p>
</body></html>"""
    headers = {"Content-Disposition": 'attachment; filename="case-spine-briefing.html"'} \
        if download else {}
    return HTMLResponse(html, headers=headers)


# ---------------------------------------------------------------- evidence
@app.get("/api/evidence/frontier", tags=["evidence"])
def evidence_frontier(con: Con, tolerance: float = Query(0.08, ge=0.0, le=1.0)):
    """Reproducible evidence pack for the automation-frontier claim.

    A number in a dashboard is not evidence. This returns the claim, the exact
    population behind it, the method, the code version, a fingerprint of the
    warehouse state, the stated limitations, and a manifest hash. Regenerating from
    the same warehouse state yields the identical hash.
    """
    return evidence.build_frontier_pack(con, tolerance=tolerance)


@app.get("/api/evidence/disparity", tags=["evidence"])
def evidence_disparity(con: Con):
    """Reproducible evidence pack for the subgroup-disparity monitoring claim."""
    return evidence.build_disparity_pack(con)


# ---------------------------------------------------------------- static client
if STATIC.exists():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        f = STATIC / "index.html"
        if f.exists():
            return FileResponse(f)
        raise HTTPException(404, "no client built")


def dev() -> None:
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1",
                port=int(os.environ.get("PORT", 8000)), reload=True)


if __name__ == "__main__":
    dev()
