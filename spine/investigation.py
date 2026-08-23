"""
The complaint-investigation business process, modelled end to end.

This is one concrete business process, implemented as a process rather than a
report. Per 21 CFR 820.198 (complaint files) and 21 CFR 803 (Medical Device
Reporting), the flow at a device company is:

  ┌────────────┐   ┌──────────────────┐   ┌─────────────────────┐   ┌────────┐
  │ Customer   │──▶│ Product          │──▶│ Reportability        │──▶│ Closed │
  │ Support:   │   │ Investigator:    │   │ decision (Quality):  │   │ (file  │
  │ complaint  │   │ assemble the     │   │ MDR within 30 days,  │   │ kept)  │
  │ received   │   │ investigation    │   │ or documented        │   │        │
  └────────────┘   │ file             │   │ rationale            │   └────────┘
                   └──────────────────┘   └─────────────────────┘
       states:   received ──▶ under_investigation ──▶ decided ──▶ closed

Hard constraints the code enforces, because the process is only real if the
software refuses to let you skip it:

  * The 30-DAY CLOCK runs from complaint awareness. Every investigation carries
    its deadline; overdue ones are flagged, and a decision recorded after the
    deadline is stored with `late=true` - visible forever, not silently absorbed.
  * A reportability DECISION requires a decision-maker, a rationale, and the
    rule trace that supported it. "Not reportable" without a documented rationale
    is refused - that is the 820.198 requirement in executable form.
  * The INVESTIGATION FILE is assembled from the spine automatically: chronology,
    what the correction changed, device context (and whether that release was
    later confirmed regressed on that scanner make - the cross-reference a
    manual investigation usually misses), sibling scan (isolated vs systemic,
    with a significance test, not a vibe), hazard linkage, and the MDR rule
    trace. The investigator reviews and decides; the assembly is not their job.
  * Every step lands in the same append-only audit trail as the action layer,
    and closing writes a frozen INVESTIGATION RECORD artifact to disk.

The MDR rule set here is a demonstration of decision-support structure on
synthetic data, not regulatory advice - and the record says so.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from spine import actions, evidence, metrics

ROOT = Path(__file__).resolve().parent.parent
RECORDS_DIR = Path(os.environ.get("INVESTIGATION_DIR",
                                  ROOT / "data" / "investigations"))

STATES = ["received", "under_investigation", "decided", "closed"]
FLOW = {"received": "under_investigation",
        "under_investigation": "decided",
        "decided": "closed"}
MDR_DEADLINE_DAYS = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_tables(con) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS investigations (
            complaint_id  INTEGER PRIMARY KEY,
            state         VARCHAR NOT NULL,
            deadline_day  INTEGER NOT NULL,
            decision      VARCHAR,            -- mdr_reportable | not_reportable
            decision_late BOOLEAN,
            rationale     VARCHAR,
            decided_by    VARCHAR,
            record_path   VARCHAR,
            created_at    VARCHAR NOT NULL,
            updated_at    VARCHAR NOT NULL
        )""")


def today(spine_con) -> int:
    """The fixture's 'now': the day after the last observed case."""
    return spine_con.execute(
        "SELECT max(case_day) + 1 FROM fct_case_spine").fetchone()[0]


# ------------------------------------------------------------------ the file
def assemble_file(spine_con, complaint_id: int) -> dict:
    """Everything the investigator needs, assembled - their job is judgement,
    not archaeology across four systems."""
    c = spine_con.execute("""
        SELECT c.*, d.site_name, d.scanner_make, d.scanner_model
        FROM fct_complaint c JOIN dim_site d USING (site_id)
        WHERE c.complaint_id = ?""", [complaint_id]).fetchone()
    if not c:
        raise KeyError(f"complaint {complaint_id} not found")
    cols = [x[0] for x in spine_con.description]
    comp = dict(zip(cols, c))

    case = spine_con.execute(
        "SELECT * FROM fct_case_spine WHERE case_id = ?",
        [comp["case_id"]]).fetchone()
    ccols = [x[0] for x in spine_con.description]
    case = dict(zip(ccols, case))

    # -- chronology ---------------------------------------------------------
    chronology = [
        {"day": case["case_day"], "event": "study received and accepted"},
        {"day": case["case_day"],
         "event": (f"analyst correction: {case['edit_count']} edits, "
                   f"{case['analyst_min']:.0f} min, segments "
                   f"{', '.join(case['segments_touched'] or [])}")},
        {"day": case["case_day"],
         "event": (f"result delivered: FFR {case['ffr_post']:.3f} "
                   f"(pre-correction {case['ffr_pre']:.3f})")},
        {"day": comp["complaint_day"],
         "event": f"complaint received: {comp['complaint_type']}"},
    ]

    # -- what the correction changed ---------------------------------------
    correction = {
        "delta_ffr": round(case["delta_ffr"], 4),
        "crossed_threshold": bool(case["crossed_threshold"]),
        "meaning": ("the human changed the diagnostic classification"
                    if case["crossed_threshold"] else
                    "the human confirmed the machine's classification"),
        "grey_zone_delivery": bool(case["grey_zone"]),
    }

    # -- device context, with the cross-reference a manual job misses -------
    reg = spine_con.execute("""
        SELECT count(*), sum(crossed_threshold), avg(crossed_threshold)
        FROM fct_case_spine s JOIN dim_site d USING (site_id)
        WHERE s.accepted = 1 AND s.model_version = ? AND d.scanner_make = ?""",
        [case["model_version"], comp["scanner_make"]]).fetchone()
    base = spine_con.execute("""
        SELECT count(*), sum(crossed_threshold)
        FROM fct_case_spine s JOIN dim_site d USING (site_id)
        WHERE s.accepted = 1 AND s.model_version <> ? AND d.scanner_make = ?""",
        [case["model_version"], comp["scanner_make"]]).fetchone()
    reg_p = metrics.two_proportion_p(int(reg[1] or 0), reg[0] or 1,
                                     int(base[1] or 0), base[0] or 1)
    device = {
        "model_version": case["model_version"],
        "scanner": f"{comp['scanner_make']} {comp['scanner_model']}",
        "detector_at_scan": case["detector_at_scan"],
        "release_flag": {
            "cohort_actionable_rate": reg[2],
            "p_vs_other_releases_same_make": round(reg_p, 5),
            "elevated": bool(reg_p < 0.05 and reg[2] and base[0]
                             and reg[2] > (base[1] or 0) / base[0]),
        },
    }

    # -- isolated or systemic? A significance test, not a vibe --------------
    def _sibling(where, params, label):
        n, k = spine_con.execute(f"""
            SELECT count(*),
                   sum(CASE WHEN case_id IN
                       (SELECT case_id FROM fct_complaint) THEN 1 ELSE 0 END)
            FROM fct_case_spine WHERE accepted = 1 AND {where}""",
            params).fetchone()
        rn, rk = spine_con.execute(f"""
            SELECT count(*),
                   sum(CASE WHEN case_id IN
                       (SELECT case_id FROM fct_complaint) THEN 1 ELSE 0 END)
            FROM fct_case_spine WHERE accepted = 1 AND NOT ({where})""",
            params).fetchone()
        p = metrics.two_proportion_p(int(k or 0), n or 1, int(rk or 0), rn or 1)
        return {"scope": label, "cases": n, "complaints": int(k or 0),
                "complaint_rate": (k or 0) / n if n else 0.0,
                "p_vs_rest": round(p, 5),
                "elevated": bool(p < 0.05 and n and (k or 0) / n >
                                 ((rk or 0) / rn if rn else 0))}

    siblings = [
        _sibling("site_id = ?", [comp["site_id"]], "same site"),
        _sibling("stratum = ?", [comp["stratum"]], "same stratum"),
        _sibling("model_version = ?", [case["model_version"]], "same release"),
    ]
    systemic = [s for s in siblings if s["elevated"]]

    # -- MDR reportability rule trace ---------------------------------------
    trace, reportable = [], False
    if comp["complaint_type"] in ("false_negative", "contraindication_missed"):
        trace.append("complaint alleges a missed/incorrect diagnostic result "
                     "-> malfunction with potential to contribute to serious "
                     "injury if it recurs (803.3)")
        reportable = True
    else:
        trace.append(f"complaint type '{comp['complaint_type']}' does not on its "
                     "face allege injury or a safety-relevant malfunction")
    if comp.get("hazard_id"):
        trace.append(f"case realises risk-file hazard {comp['hazard_id']} - "
                     "supports the malfunction determination")
    if case["ffr_post"] <= 0.80 < case["ffr_pre"]:
        trace.append("pre-correction result would have missed ischemia the "
                     "delivered result reported - MAUDE-pattern mechanism present")
    if systemic:
        trace.append("sibling scan shows a statistically elevated complaint rate "
                     f"({', '.join(s['scope'] for s in systemic)}) - not isolated")

    return {
        "complaint": comp,
        "chronology": chronology,
        "correction": correction,
        "device": device,
        "siblings": siblings,
        "systemic": bool(systemic),
        "mdr_assessment": {
            "suggested": "mdr_reportable" if reportable else "not_reportable",
            "rule_trace": trace,
            "disclaimer": ("Decision-support structure on synthetic data; the "
                           "human decision-maker and their rationale are "
                           "authoritative, not this suggestion."),
        },
        "assembled_at": _now(),
        "warehouse_grain": evidence.spine_fingerprint(spine_con)
                           ["grain_sha256"][:16],
    }


# ------------------------------------------------------------------ the process
def board(spine_con) -> dict:
    """Every complaint's position in the process, with its clock."""
    now = today(spine_con)
    con = actions.connect()
    try:
        _ensure_tables(con)
        inv = {r[0]: dict(zip([c[0] for c in con.description], r))
               for r in con.execute("SELECT * FROM investigations").fetchall()}
    finally:
        con.close()

    rows = []
    for cid, day, ctype, mdr in spine_con.execute(
            "SELECT complaint_id, complaint_day, complaint_type, mdr_reportable "
            "FROM fct_complaint ORDER BY complaint_day").fetchall():
        rec = inv.get(cid)
        deadline = day + MDR_DEADLINE_DAYS
        rows.append({
            "complaint_id": cid, "complaint_day": day,
            "complaint_type": ctype,
            "state": rec["state"] if rec else "received",
            "deadline_day": deadline,
            "days_remaining": deadline - now,
            "overdue": (deadline - now) < 0 and
                       (rec is None or rec["state"] not in ("decided", "closed")),
            "decision": rec["decision"] if rec else None,
            "decision_late": rec["decision_late"] if rec else None,
        })
    return {
        "today": now,
        "deadline_days": MDR_DEADLINE_DAYS,
        "items": rows,
        "summary": {
            "received": sum(1 for r in rows if r["state"] == "received"),
            "under_investigation": sum(1 for r in rows
                                       if r["state"] == "under_investigation"),
            "decided": sum(1 for r in rows if r["state"] == "decided"),
            "closed": sum(1 for r in rows if r["state"] == "closed"),
            "overdue": sum(1 for r in rows if r["overdue"]),
        },
    }


def open_investigation(spine_con, complaint_id: int, actor: str) -> dict:
    if not actor.strip():
        raise ValueError("an investigation must name its investigator")
    file = assemble_file(spine_con, complaint_id)   # raises on unknown complaint
    now = today(spine_con)
    con = actions.connect()
    try:
        _ensure_tables(con)
        if con.execute("SELECT state FROM investigations WHERE complaint_id = ?",
                       [complaint_id]).fetchone():
            raise ValueError(f"investigation for complaint {complaint_id} "
                             "already exists")
        deadline = file["complaint"]["complaint_day"] + MDR_DEADLINE_DAYS
        ts = _now()
        con.execute("INSERT INTO investigations VALUES (?,?,?,?,?,?,?,?,?,?)",
                    [complaint_id, "under_investigation", deadline,
                     None, None, None, None, None, ts, ts])
        con.execute("INSERT INTO action_events VALUES (?,?,?,?,?,?,?)",
                    [uuid.uuid4().hex[:12], f"inv:{complaint_id}", ts,
                     actor.strip(), "received", "under_investigation",
                     f"investigation opened; deadline day {deadline} "
                     f"(today is day {now})"])
    finally:
        con.close()
    return {"complaint_id": complaint_id, "state": "under_investigation",
            "file": file}


def decide(spine_con, complaint_id: int, decision: str, actor: str,
           rationale: str) -> dict:
    """The regulated step. Refuses an undocumented decision, records lateness."""
    if decision not in ("mdr_reportable", "not_reportable"):
        raise ValueError("decision must be mdr_reportable or not_reportable")
    if not actor.strip():
        raise ValueError("a reportability decision must name its decision-maker")
    if len(rationale.strip()) < 20:
        raise ValueError(
            "a reportability decision requires a substantive documented "
            "rationale (>= 20 characters) - 21 CFR 820.198 in executable form")
    now = today(spine_con)
    con = actions.connect()
    try:
        _ensure_tables(con)
        row = con.execute(
            "SELECT state, deadline_day FROM investigations "
            "WHERE complaint_id = ?", [complaint_id]).fetchone()
        if not row:
            raise KeyError(f"no open investigation for complaint {complaint_id}")
        state, deadline = row
        if state != "under_investigation":
            raise ValueError(f"cannot decide from state {state!r}")
        late = now > deadline
        ts = _now()
        con.execute("""UPDATE investigations
                       SET state='decided', decision=?, decision_late=?,
                           rationale=?, decided_by=?, updated_at=?
                       WHERE complaint_id=?""",
                    [decision, late, rationale.strip(), actor.strip(), ts,
                     complaint_id])
        con.execute("INSERT INTO action_events VALUES (?,?,?,?,?,?,?)",
                    [uuid.uuid4().hex[:12], f"inv:{complaint_id}", ts,
                     actor.strip(), "under_investigation", "decided",
                     f"{decision}{' (LATE - after the 30-day deadline)' if late else ''}"
                     f": {rationale.strip()}"])
    finally:
        con.close()
    return {"complaint_id": complaint_id, "decision": decision, "late": late}


def close(spine_con, complaint_id: int, actor: str) -> dict:
    """Closing writes the frozen investigation record - the process artifact."""
    if not actor.strip():
        raise ValueError("closing an investigation names its actor")
    con = actions.connect()
    try:
        _ensure_tables(con)
        row = con.execute(
            "SELECT state, decision, decision_late, rationale, decided_by "
            "FROM investigations WHERE complaint_id = ?",
            [complaint_id]).fetchone()
        if not row:
            raise KeyError(f"no investigation for complaint {complaint_id}")
        if row[0] != "decided":
            raise ValueError("an investigation closes only after a documented "
                             f"reportability decision (state is {row[0]!r})")

        record = {
            "record_type": "complaint_investigation",
            "complaint_id": complaint_id,
            "file": assemble_file(spine_con, complaint_id),
            "decision": {"outcome": row[1], "late": bool(row[2]),
                         "rationale": row[3], "decided_by": row[4]},
            "audit_trail": [dict(zip(("occurred_at", "actor", "from_state",
                                      "to_state", "note"), e))
                            for e in con.execute(
                                "SELECT occurred_at, actor, from_state, to_state, "
                                "note FROM action_events WHERE action_id = ? "
                                "ORDER BY occurred_at",
                                [f"inv:{complaint_id}"]).fetchall()],
            "closed_by": actor.strip(),
        }
        sealed = evidence.finalise(record)
        RECORDS_DIR.mkdir(parents=True, exist_ok=True)
        path = RECORDS_DIR / (f"investigation-{complaint_id:04d}-"
                              f"{sealed['manifest_sha256'][:12]}.json")
        path.write_text(json.dumps(sealed, indent=2, default=str),
                        encoding="utf-8")
        ts = _now()
        con.execute("""UPDATE investigations SET state='closed',
                       record_path=?, updated_at=? WHERE complaint_id=?""",
                    [str(path), ts, complaint_id])
        con.execute("INSERT INTO action_events VALUES (?,?,?,?,?,?,?)",
                    [uuid.uuid4().hex[:12], f"inv:{complaint_id}", ts,
                     actor.strip(), "decided", "closed",
                     f"record sealed {sealed['manifest_sha256'][:16]}"])
    finally:
        con.close()
    return {"complaint_id": complaint_id, "state": "closed",
            "record_path": str(path),
            "manifest_sha256": sealed["manifest_sha256"]}
