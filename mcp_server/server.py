"""
Case Spine MCP server.

Exposes the spine as a governed tool surface for AI agents. Two audiences:

  1. Test and evaluation - an agent can be asked a question about the pipeline and
     its answer checked against ground truth computed directly from the warehouse.
  2. Production agent workflows - the surface an internal assistant would call to
     answer "did release v4.1.0 hurt anything?" without a human writing SQL.

THE GOVERNANCE DECISION, and the reason this file exists at all:

    There is no `run_sql` tool. There will not be one.

Every tool is a *named metric query* composed from spine.metrics, so an agent can
select and slice but cannot invent a metric, cannot join arbitrarily, and cannot
reach a column the semantic layer does not expose. A free-text SQL tool over a
clinical warehouse is a governance hole that no amount of prompt engineering
closes: it makes the model's output unauditable, lets it silently compute a metric
three different ways, and gives it a path to columns the PHI boundary is supposed
to keep it away from.

The constraints that follow:

  read-only     Every tool is annotated readOnlyHint=True and runs on a read-only
                connection. Nothing writes, routes, or dispositions a case - the
                same boundary as the HTTP API. See validation/csa-validation-plan.md.
  no PHI        Pseudonymous case surrogates and covariate summaries only. No pixel
                data, no DICOM identifiers, no patient names.
  no identity   Analyst identity is absent from the schema, so no tool can leak it.
  audited       Every call is logged with arguments, size and duration. In a
                regulated setting "what did the agent look at" must be answerable.
  provenance    Results carry the filters applied and the definition source, so an
                agent can cite rather than assert.

Run:
    python -m mcp_server.server

Register with Claude Code:
    claude mcp add case-spine -- python -m mcp_server.server
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Annotated, Any

import duckdb
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from spine import evidence, metrics

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "spine.duckdb"
AUDIT = ROOT / "data" / "mcp-audit.log"

AUDIT.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(AUDIT, encoding="utf-8")],
)
log = logging.getLogger("case-spine-mcp")

mcp = MCPServer(
    name="case-spine",
    version="0.1.0",
    instructions=(
        "Read-only analytics over a coronary CT analysis pipeline.\n\n"
        "Key metric - actionable_correction_rate: of accepted cases, the share "
        "where human analyst correction moved an FFR value across the 0.80 "
        "ischemia threshold, i.e. where the human CHANGED THE ANSWER rather than "
        "confirming it. It is a SAFETY measure. median_analyst_min is a COST "
        "measure. Never substitute one for the other: evidence for removing humans "
        "from the loop requires the former.\n\n"
        "There is deliberately no SQL tool. Query through query_metrics using named "
        "measures and dimensions. If a measure you want does not exist, say so "
        "rather than approximating it with a different one.\n\n"
        "Report 'unconfirmed' release signals as inconclusive, never as regressions."
    ),
)

# Every tool carries these. readOnlyHint is the machine-readable form of the
# regulatory boundary: a client can refuse to run anything that lacks it.
READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)


def connect() -> duckdb.DuckDBPyConnection:
    if not DB.exists():
        raise RuntimeError(
            "spine not built - run `python -m spine.generate && python -m spine.build`")
    # read_only is enforcement, not convention: the connection itself rejects DDL
    # and DML, so a tool bug cannot mutate the warehouse.
    return duckdb.connect(str(DB), read_only=True)


def query(sql: str, params: list | None = None) -> list[dict]:
    con = connect()
    try:
        cur = con.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        con.close()


def audit(tool: str, args: dict, result: Any, started: float) -> Any:
    log.info("tool=%s args=%s ms=%.1f", tool, json.dumps(args, default=str),
             (time.perf_counter() - started) * 1000)
    return result


# --------------------------------------------------------------------- tools
@mcp.tool(annotations=READ_ONLY)
def spine_overview() -> dict:
    """Headline metrics for the whole analysis pipeline.

    Case volume, reject rate, actionable-correction rate, median analyst time,
    complaint and hazard counts. Start here to orient before slicing.
    """
    t = time.perf_counter()
    m = query(metrics.select([
        "cases", "accepted_cases", "rejected_cases", "reject_rate",
        "actionable_correction_rate", "grey_zone_rate",
        "median_analyst_min", "median_turnaround_min"]))[0]
    m["sites"] = query("SELECT count(*) AS n FROM dim_site")[0]["n"]
    m["complaints"] = query("SELECT count(*) AS n FROM fct_complaint")[0]["n"]
    m["hazard_matches"] = query("SELECT count(*) AS n FROM fct_hazard_match")[0]["n"]
    m["_note"] = ("actionable_correction_rate is the share of accepted cases where "
                  "analyst correction changed the diagnostic classification.")
    return audit("spine_overview", {}, m, t)


@mcp.tool(annotations=READ_ONLY)
def query_metrics(
    measures: Annotated[list[str], Field(
        description=f"Measure names. Available: {', '.join(sorted(metrics.MEASURES))}")],
    group_by: Annotated[list[str] | None, Field(
        default=None,
        description=f"Optional dimensions. Available: {', '.join(metrics.DIMENSIONS)}")] = None,
    accepted_only: Annotated[bool, Field(
        default=True,
        description=("Restrict to cases that passed the ingest gate. Usually true - "
                     "rejected cases never reach an analyst, so including them "
                     "dilutes every correction rate."))] = True,
    limit: Annotated[int, Field(default=100, ge=1, le=500)] = 100,
) -> dict:
    """Query named measures grouped by named dimensions.

    This is the only general query surface; arbitrary SQL is deliberately not
    offered, so an agent can select and slice but cannot invent a metric or reach a
    column the semantic layer does not expose.

    An unknown measure or dimension is REJECTED rather than guessed. If the metric
    you need is absent, report that instead of substituting a different one.
    """
    t = time.perf_counter()
    args = {"measures": measures, "group_by": group_by, "accepted_only": accepted_only}
    try:
        sql = metrics.select(
            measures, by=group_by,
            where=metrics.ACCEPTED if accepted_only else None,
            limit=limit)
    except KeyError as exc:
        # This rejection IS the governance boundary working. Return it usefully.
        return audit("query_metrics", args, {"error": str(exc)}, t)

    data = query(sql)
    return audit("query_metrics", args, {
        "rows": data,
        "provenance": {
            "measures": measures,
            "group_by": group_by or [],
            "filter": "accepted only" if accepted_only else "all submitted cases",
            "row_count": len(data),
            "definition_source": "spine/metrics.py (mirrored in Cube semantic model)",
        },
    }, t)


@mcp.tool(annotations=READ_ONLY)
def automation_frontier(
    tolerance: Annotated[float, Field(
        default=0.08, ge=0.0, le=1.0,
        description="Maximum acceptable actionable-correction rate, as a fraction.")] = 0.08,
) -> dict:
    """Case strata ranked by residual risk, with cumulative automatable volume.

    This is the artifact a Predetermined Change Control Plan needs: the argument
    that a defined subset of cases can be processed without human correction at a
    stated and monitored residual rate. Strata below 12 accepted cases are
    suppressed as statistically unreliable and a re-identification risk.
    """
    t = time.perf_counter()
    con = connect()
    try:
        strata = metrics.frontier(con)
    finally:
        con.close()
    return audit("automation_frontier", {"tolerance": tolerance}, {
        "at_tolerance": metrics.frontier_at(strata, tolerance),
        "strata": [s.__dict__ for s in strata],
        "provenance": {"suppressed_below_n": metrics.MIN_STRATUM_N,
                       "threshold": "FFR 0.80"},
    }, t)


@mcp.tool(annotations=READ_ONLY)
def hazard_status(
    hazard_id: Annotated[str | None, Field(
        default=None, description="Optional, e.g. 'H-014'. Omit for all hazards.")] = None,
) -> dict:
    """Risk-file hazards matched against live cases, with per-release trend.

    Each hazard carries a machine-evaluable signature authored by Quality.

    A MATCH IS NOT A HARM - it means the case realised the conditions the hazard
    describes. Use this for ISO 14971 residual-risk reporting. A signature matching
    thousands of cases with zero complaints is probably too loose and should go back
    to Quality rather than being reported as a safety problem.
    """
    t = time.perf_counter()
    where = "WHERE h.hazard_id = ?" if hazard_id else ""
    params = [hazard_id] if hazard_id else []
    hazards = query(f"""
        SELECT h.hazard_id, h.title, h.controls,
               count(m.case_id) AS matches,
               (SELECT count(*) FROM fct_complaint c
                 WHERE c.hazard_id = h.hazard_id) AS complaints
        FROM raw_hazards h
        LEFT JOIN fct_hazard_match m ON m.hazard_id = h.hazard_id
        {where}
        GROUP BY h.hazard_id, h.title, h.controls ORDER BY h.hazard_id""", params)
    for h in hazards:
        h["by_release"] = query("""
            SELECT v.model_version,
                   count(DISTINCT s.case_id) AS accepted_cases,
                   count(DISTINCT m.case_id) AS matches,
                   count(DISTINCT m.case_id) * 1.0
                     / nullif(count(DISTINCT s.case_id), 0) AS match_rate
            FROM dim_model_version v
            LEFT JOIN fct_case_spine s
                   ON s.model_version = v.model_version AND s.accepted = 1
            LEFT JOIN fct_hazard_match m
                   ON m.model_version = v.model_version AND m.hazard_id = ?
            GROUP BY v.model_version, v.release_seq ORDER BY v.release_seq""",
            [h["hazard_id"]])
    return audit("hazard_status", {"hazard_id": hazard_id}, {
        "hazards": hazards,
        "_note": "A signature match is a realised condition, not a harm.",
    }, t)


@mcp.tool(annotations=READ_ONLY)
def trace_complaint(complaint_id: Annotated[int, Field(description="Complaint id.")]) -> dict:
    """Resolve a complaint through the spine.

    complaint -> case -> site -> hazard -> stratum -> trend by model version.

    Answers "is this an anecdote or a signal?" by placing the complaint's case in
    its peer cohort. Without the spine this traversal spans four separate systems.
    """
    t = time.perf_counter()
    c = query("""
        SELECT c.*, d.site_name, d.scanner_make, d.scanner_model
        FROM fct_complaint c JOIN dim_site d USING (site_id)
        WHERE c.complaint_id = ?""", [complaint_id])
    if not c:
        return audit("trace_complaint", {"complaint_id": complaint_id},
                     {"error": f"complaint {complaint_id} not found"}, t)
    c = c[0]
    cohort = query(metrics.select(
        ["accepted_cases", "actionable_corrections", "actionable_correction_rate"],
        where=f"{metrics.ACCEPTED} AND stratum = ?"), [c["stratum"]])[0]
    by_release = query(metrics.select(
        ["accepted_cases", "actionable_correction_rate"],
        by=["model_version"],
        where=f"{metrics.ACCEPTED} AND stratum = ?",
        having="count(*) > 8", order="model_version"), [c["stratum"]])
    return audit("trace_complaint", {"complaint_id": complaint_id},
                 {"complaint": c, "stratum_cohort": cohort, "by_release": by_release}, t)


@mcp.tool(annotations=READ_ONLY)
def compare_releases(
    min_cases: Annotated[int, Field(
        default=40, ge=20,
        description="Minimum cases per cell; smaller cells are noise.")] = 40,
) -> dict:
    """Actionable-correction rate by model version and scanner make, with significance.

    Each cell is tested against that manufacturer's first release in the window
    using a two-proportion test. A release is flagged 'regression' or 'improved'
    only when the effect is BOTH material (lift >= 1.25 or <= 0.80) AND supported
    (p < 0.05). A material but unsupported effect reads 'unconfirmed'.

    Do NOT report an unconfirmed signal as a regression. Small per-vendor cells
    produce 1.3x lifts by chance routinely, and a monitor that cries wolf gets muted.
    """
    t = time.perf_counter()
    data = query(f"""
        SELECT s.model_version, d.scanner_make,
               count(*) AS accepted_cases,
               sum(s.crossed_threshold) AS actionable_corrections,
               avg(s.crossed_threshold) AS actionable_correction_rate,
               median(s.analyst_min) AS median_analyst_min
        FROM fct_case_spine s JOIN dim_site d USING (site_id)
        WHERE s.accepted = 1
        GROUP BY 1, 2 HAVING count(*) >= {int(min_cases)}
        ORDER BY 2, 1""")
    baseline: dict[str, dict] = {}
    for r in data:
        baseline.setdefault(r["scanner_make"], r)
    for r in data:
        b = baseline[r["scanner_make"]]
        rate, b_rate = r["actionable_correction_rate"], b["actionable_correction_rate"]
        r["lift_vs_first_release"] = rate / b_rate if b_rate else 1.0
        r["p_value"] = 1.0 if r is b else metrics.two_proportion_p(
            r["actionable_corrections"], r["accepted_cases"],
            b["actionable_corrections"], b["accepted_cases"])
        up = r["lift_vs_first_release"] >= 1.25
        down = r["lift_vs_first_release"] <= 0.80
        sig = r["p_value"] < 0.05
        r["signal"] = ("regression" if up and sig else "improved" if down and sig
                       else "unconfirmed" if (up or down) else "stable")
    return audit("compare_releases", {"min_cases": min_cases}, {
        "comparisons": data,
        "_note": ("Only 'regression' and 'improved' are supported findings. "
                  "'unconfirmed' means a material effect without statistical "
                  "support - report it as inconclusive, not as a regression."),
    }, t)


@mcp.tool(annotations=READ_ONLY)
def subgroup_disparity(
    model_version: Annotated[str | None, Field(
        default=None, description="Optional release to restrict to, e.g. 'v4.1.0'.")] = None,
) -> dict:
    """Actionable-correction rate across clinical and operational subgroups.

    Escalation is conjunctive and the thresholds are predetermined: an arm is
    escalated only when it is FDR-significant (Benjamini-Hochberg, q=0.10) AND its
    disparity ratio is at least 1.5x the best arm AND it carries at least 30 cases.

    Report the `escalations` list as actionable. An arm marked `fdr_significant`
    but not `escalate` is a statistically detectable difference that does not meet
    the effect-size floor - do NOT report it as a disparity requiring action.

    These are CLINICAL AND OPERATIONAL subgroups (calcium, motion, BMI, detector,
    site class, stent). The spine carries no demographics, so this is not
    demographic equity analysis and must never be described as such.
    """
    t = time.perf_counter()
    where, params = metrics.ACCEPTED, []
    if model_version:
        where += " AND model_version = ?"
        params = [model_version]
    con = connect()
    try:
        result = metrics.subgroup_disparity(con, where=where, params=params)
    finally:
        con.close()
    return audit("subgroup_disparity", {"model_version": model_version}, result, t)


@mcp.tool(annotations=READ_ONLY)
def inspect_case(case_id: Annotated[int, Field(description="Pseudonymous case surrogate.")]) -> dict:
    """Every fact the spine carries about one case, across all source systems.

    Acquisition parameters, ingest disposition, segmentation confidence, analyst
    correction, FFR before and after correction, stratum, matched hazards and any
    complaint.

    Case identifiers are pseudonymous surrogates. Re-identification requires a
    separate access-controlled key store that this server cannot reach.
    """
    t = time.perf_counter()
    c = query("""
        SELECT s.*, d.site_name, d.region, d.scanner_make, d.scanner_model, d.site_class
        FROM fct_case_spine s JOIN dim_site d USING (site_id)
        WHERE s.case_id = ?""", [case_id])
    if not c:
        return audit("inspect_case", {"case_id": case_id},
                     {"error": f"case {case_id} not found"}, t)
    c = c[0]
    c["hazards"] = [r["hazard_id"] for r in query(
        "SELECT hazard_id FROM fct_hazard_match WHERE case_id = ? ORDER BY 1", [case_id])]
    comp = query("SELECT * FROM fct_complaint WHERE case_id = ?", [case_id])
    c["complaint"] = comp[0] if comp else None
    return audit("inspect_case", {"case_id": case_id}, c, t)


@mcp.tool(annotations=READ_ONLY)
def evidence_pack(
    claim: Annotated[str, Field(
        description="Which claim to evidence: 'automation_frontier' or 'subgroup_disparity'.")],
    tolerance: Annotated[float, Field(
        default=0.08, ge=0.0, le=1.0,
        description="Residual risk tolerance, automation_frontier only.")] = 0.08,
) -> dict:
    """Build a reproducible evidence pack for a claim.

    Returns the claim, the exact case population supporting it (as a count and a
    hash of the sorted case IDs), the method, the code version, a fingerprint of the
    warehouse state, the stated limitations, and a manifest hash.

    Use this when asked to SUPPORT or DOCUMENT a finding rather than merely report
    it. Regenerating from the same warehouse state produces an identical
    manifest_sha256; if two packs disagree, the underlying data changed.

    Always surface the `limitations` list alongside the claim. A pack presented
    without its limitations misrepresents what the evidence establishes.
    """
    t = time.perf_counter()
    con = connect()
    try:
        if claim == "automation_frontier":
            pack = evidence.build_frontier_pack(con, tolerance=tolerance)
        elif claim == "subgroup_disparity":
            pack = evidence.build_disparity_pack(con)
        else:
            return audit("evidence_pack", {"claim": claim}, {
                "error": f"unknown claim {claim!r}",
                "available": ["automation_frontier", "subgroup_disparity"]}, t)
    finally:
        con.close()
    return audit("evidence_pack", {"claim": claim, "tolerance": tolerance}, pack, t)


if __name__ == "__main__":
    mcp.run("stdio")
