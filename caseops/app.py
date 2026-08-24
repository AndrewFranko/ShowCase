"""CaseOps API - the operational case-management system upstream of the spine.

Read-WRITE by design (this IS the system of record), which is exactly why the
Case Spine portal is a separate, read-only service: the regulatory boundary
lives between these two processes, not inside one of them.

Run:  python -m uvicorn caseops.app:app --port 8095
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from caseops import ml
from caseops.db import ACTIVE_STATUSES, connect, fan_out

STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="CaseOps", version="0.1.0",
              description="Hospitals, devices, analysts, tickets, incidents - "
                          "with change warnings fanned out to affected analysts.")


def db():
    try:
        con = connect()
    except psycopg.OperationalError as exc:
        raise HTTPException(503, f"postgres unreachable: {exc}") from exc
    try:
        yield con
        con.commit()
    finally:
        con.close()


Con = Annotated[psycopg.Connection, Depends(db)]


def q(con, sql: str, params=None) -> list[dict]:
    with con.cursor() as cur:
        cur.execute(sql, params or [])
        return cur.fetchall()


# ---------------------------------------------------------------- overview
@app.get("/api/summary")
def summary(con: Con):
    (s,) = q(con, """
        SELECT (SELECT count(*) FROM hospital)                                   AS hospitals,
               (SELECT count(*) FROM device)                                     AS devices,
               (SELECT count(*) FROM analyst)                                    AS analysts,
               (SELECT count(*) FROM ticket WHERE status = 'open')               AS open_tickets,
               (SELECT count(*) FROM ticket WHERE status = ANY(%s))              AS active_tickets,
               (SELECT count(*) FROM ticket WHERE status = 'resolved')           AS resolved_tickets,
               (SELECT count(*) FROM incident WHERE status = 'open')             AS open_incidents,
               (SELECT count(*) FROM notification WHERE read_at IS NULL)         AS unread_warnings
        """, [list(ACTIVE_STATUSES)])
    s["throughput_14d"] = q(con, """
        SELECT resolved_at::date AS day, count(*) AS resolved,
               sum(actual_min)::int AS minutes
        FROM ticket WHERE status = 'resolved'
          AND resolved_at >= (SELECT max(resolved_at) FROM ticket) - interval '14 days'
        GROUP BY 1 ORDER BY 1""")
    return s


# ---------------------------------------------------------------- hospitals & devices
@app.get("/api/hospitals")
def hospitals(con: Con):
    return q(con, """
        SELECT h.*, count(DISTINCT d.device_id) AS devices,
               count(DISTINCT t.ticket_id) FILTER (WHERE t.status <> 'resolved') AS open_tickets,
               count(DISTINCT i.incident_id) FILTER (WHERE i.status = 'open')    AS open_incidents,
               max(c.occurred_at)                                                AS last_change
        FROM hospital h
        LEFT JOIN device d USING (hospital_id)
        LEFT JOIN ticket t USING (hospital_id)
        LEFT JOIN incident i ON i.hospital_id = h.hospital_id
        LEFT JOIN hospital_change c ON c.hospital_id = h.hospital_id
        GROUP BY h.hospital_id ORDER BY open_tickets DESC, h.name""")


@app.get("/api/hospitals/{hospital_id}")
def hospital_detail(hospital_id: int, con: Con):
    hs = q(con, "SELECT * FROM hospital WHERE hospital_id = %s", [hospital_id])
    if not hs:
        raise HTTPException(404, "no such hospital")
    h = hs[0]
    h["devices"] = q(con, "SELECT * FROM device WHERE hospital_id = %s ORDER BY device_id",
                     [hospital_id])
    h["changes"] = q(con, """SELECT * FROM hospital_change WHERE hospital_id = %s
                             ORDER BY occurred_at DESC LIMIT 12""", [hospital_id])
    h["incidents"] = q(con, """SELECT * FROM incident WHERE hospital_id = %s
                               ORDER BY reported_at DESC LIMIT 12""", [hospital_id])
    h["open_tickets"] = q(con, """
        SELECT t.*, a.name AS analyst FROM ticket t
        LEFT JOIN analyst a USING (analyst_id)
        WHERE t.hospital_id = %s AND t.status <> 'resolved'
        ORDER BY t.priority, t.created_at""", [hospital_id])
    return h


# ---------------------------------------------------------------- tickets
@app.get("/api/tickets")
def tickets(con: Con, status: str | None = None, analyst_id: int | None = None,
            limit: int = Query(200, le=500)):
    return q(con, """
        SELECT t.*, h.name AS hospital, h.region, a.name AS analyst,
               d.make || ' ' || d.model AS device, d.detector
        FROM ticket t
        JOIN hospital h USING (hospital_id)
        JOIN device d ON d.device_id = t.device_id
        LEFT JOIN analyst a USING (analyst_id)
        WHERE (%s::text IS NULL OR t.status = %s)
          AND (%s::int IS NULL OR t.analyst_id = %s)
          AND t.status <> 'resolved'
        ORDER BY t.priority, t.created_at LIMIT %s""",
        [status, status, analyst_id, analyst_id, limit])


class Assign(BaseModel):
    analyst_id: int


@app.post("/api/tickets/{ticket_id}/assign")
def assign(ticket_id: int, body: Assign, con: Con):
    r = q(con, """UPDATE ticket SET analyst_id = %s, status = 'assigned', assigned_at = now()
                  WHERE ticket_id = %s AND status = 'open'
                  RETURNING ticket_id""", [body.analyst_id, ticket_id])
    if not r:
        raise HTTPException(409, "ticket is not open (already assigned or resolved)")
    return {"ticket_id": ticket_id, "analyst_id": body.analyst_id, "status": "assigned"}


class Advance(BaseModel):
    status: Literal["in_review", "blocked", "resolved"]
    actual_min: int | None = Field(None, gt=0)


LEGAL = {("assigned", "in_review"), ("assigned", "blocked"), ("in_review", "blocked"),
         ("blocked", "in_review"), ("in_review", "resolved")}


@app.post("/api/tickets/{ticket_id}/status")
def advance(ticket_id: int, body: Advance, con: Con):
    cur = q(con, "SELECT status FROM ticket WHERE ticket_id = %s", [ticket_id])
    if not cur:
        raise HTTPException(404, "no such ticket")
    frm = cur[0]["status"]
    if (frm, body.status) not in LEGAL:
        raise HTTPException(409, f"illegal transition {frm} -> {body.status}")
    if body.status == "resolved" and not body.actual_min:
        raise HTTPException(422, "resolving requires actual_min")
    q(con, """UPDATE ticket SET status = %s,
              actual_min = COALESCE(%s, actual_min),
              resolved_at = CASE WHEN %s = 'resolved' THEN now() ELSE resolved_at END
              WHERE ticket_id = %s RETURNING ticket_id""",
      [body.status, body.actual_min, body.status, ticket_id])
    return {"ticket_id": ticket_id, "status": body.status}


# ---------------------------------------------------------------- analysts & catch-up
@app.get("/api/analysts")
def analysts(con: Con):
    return q(con, """
        SELECT a.*,
               count(t.ticket_id) FILTER (WHERE t.status = ANY(%s))       AS active_tickets,
               COALESCE(sum(t.est_min) FILTER (WHERE t.status = ANY(%s)), 0)::int AS active_min,
               (SELECT count(*) FROM notification n
                WHERE n.analyst_id = a.analyst_id AND n.read_at IS NULL)  AS unread
        FROM analyst a LEFT JOIN ticket t USING (analyst_id)
        GROUP BY a.analyst_id ORDER BY a.analyst_id""",
        [list(ACTIVE_STATUSES), list(ACTIVE_STATUSES)])


@app.get("/api/analysts/{analyst_id}/catchup")
def catchup(analyst_id: int, con: Con):
    """Everything that changed under this analyst's active tickets since they
    last looked - the warnings, each pinned to the tickets it affects."""
    notifs = q(con, """
        SELECT n.*, h.name AS hospital
        FROM notification n
        LEFT JOIN hospital_change c ON n.source = 'change'   AND n.source_id = c.change_id
        LEFT JOIN incident        i ON n.source = 'incident' AND n.source_id = i.incident_id
        LEFT JOIN hospital h ON h.hospital_id = COALESCE(c.hospital_id, i.hospital_id)
        WHERE n.analyst_id = %s AND n.read_at IS NULL
        ORDER BY n.created_at DESC""", [analyst_id])
    for n in notifs:
        n["tickets"] = q(con, """
            SELECT t.ticket_id, t.status, t.priority, t.est_min, h.name AS hospital
            FROM ticket t JOIN hospital h USING (hospital_id)
            WHERE t.ticket_id = ANY(%s)""", [n["ticket_ids"]])
    return {"analyst_id": analyst_id, "unread": len(notifs), "notifications": notifs}


class Ack(BaseModel):
    notif_ids: list[int]


@app.post("/api/analysts/{analyst_id}/catchup/ack")
def ack(analyst_id: int, body: Ack, con: Con):
    r = q(con, """UPDATE notification SET read_at = now()
                  WHERE analyst_id = %s AND notif_id = ANY(%s) AND read_at IS NULL
                  RETURNING notif_id""", [analyst_id, body.notif_ids])
    return {"acknowledged": [x["notif_id"] for x in r]}


# ---------------------------------------------------------------- events (the warning triggers)
class IncidentIn(BaseModel):
    hospital_id: int
    device_id: int | None = None
    kind: str
    severity: int = Field(ge=1, le=4)
    description: str = Field(min_length=8)


@app.post("/api/incidents")
def report_incident(body: IncidentIn, con: Con):
    with con.cursor() as cur:
        cur.execute("""INSERT INTO incident (hospital_id, device_id, kind, severity, description)
                       VALUES (%s,%s,%s,%s,%s) RETURNING incident_id""",
                    (body.hospital_id, body.device_id, body.kind, body.severity, body.description))
        iid = cur.fetchone()["incident_id"]
        warned = fan_out(cur, "incident", iid, body.hospital_id, body.device_id,
                         f"Incident (severity {body.severity}): {body.kind}")
    return {"incident_id": iid, "analysts_warned": warned}


@app.get("/api/incidents")
def incidents(con: Con, status: str | None = None):
    return q(con, """
        SELECT i.*, h.name AS hospital, d.make || ' ' || d.model AS device
        FROM incident i JOIN hospital h USING (hospital_id)
        LEFT JOIN device d ON d.device_id = i.device_id
        WHERE (%s::text IS NULL OR i.status = %s)
        ORDER BY i.reported_at DESC LIMIT 100""", [status, status])


class ChangeIn(BaseModel):
    hospital_id: int
    device_id: int | None = None
    kind: Literal["device_swap", "sw_update", "detector_upgrade", "protocol_change"]
    details: str = Field(min_length=8)


@app.post("/api/changes")
def record_change(body: ChangeIn, con: Con):
    with con.cursor() as cur:
        cur.execute("""INSERT INTO hospital_change (hospital_id, device_id, kind, details)
                       VALUES (%s,%s,%s,%s) RETURNING change_id""",
                    (body.hospital_id, body.device_id, body.kind, body.details))
        cid = cur.fetchone()["change_id"]
        warned = fan_out(cur, "change", cid, body.hospital_id, body.device_id, body.details)
    return {"change_id": cid, "analysts_warned": warned}


@app.get("/api/changes")
def changes(con: Con):
    return q(con, """
        SELECT c.*, h.name AS hospital, d.make || ' ' || d.model AS device
        FROM hospital_change c JOIN hospital h USING (hospital_id)
        LEFT JOIN device d ON d.device_id = c.device_id
        ORDER BY c.occurred_at DESC LIMIT 100""")


# ---------------------------------------------------------------- workload forecast
@app.get("/api/forecast")
def forecast(con: Con):
    with con.cursor() as cur:
        return ml.workload(cur)


# ---------------------------------------------------------------- client
@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


# ---------------------------------------------------------------- 3D change level
@app.get("/api/geometry/summary")
def geometry_summary(con: Con):
    """Binary-level change analysis of the 3D artifacts: how much of each
    corrected mesh actually changed, on disk."""
    stats = q(con, """
        SELECT count(*)                              AS artifacts,
               round(avg(blocks_changed_pct)::numeric, 1)  AS mean_blocks_pct,
               round(percentile_cont(0.5) WITHIN GROUP (ORDER BY blocks_changed_pct)::numeric, 1)
                                                     AS median_blocks_pct,
               round(avg(vertices_moved_pct)::numeric, 1)  AS mean_vertices_pct,
               round(avg(mean_disp_mm)::numeric, 2)  AS mean_disp_mm,
               round((sum(bytes_changed)::numeric / NULLIF(sum(bytes_total),0) * 100), 1)
                                                     AS bytes_changed_pct_overall
        FROM geometry_delta""")
    hist = q(con, """
        SELECT width_bucket(blocks_changed_pct, 0, 100, 20) AS bin,
               count(*) AS n
        FROM geometry_delta GROUP BY 1 ORDER BY 1""")
    top = q(con, """
        SELECT g.*, h.name AS hospital, d.make || ' ' || d.model AS device, d.detector
        FROM geometry_delta g
        JOIN ticket t USING (ticket_id)
        JOIN hospital h ON h.hospital_id = t.hospital_id
        JOIN device d ON d.device_id = t.device_id
        ORDER BY g.blocks_changed_pct DESC LIMIT 10""")
    return {"stats": stats[0] if stats else {}, "histogram": hist, "top": top}


@app.get("/api/geometry/model")
def geometry_model(con: Con):
    with con.cursor() as cur:
        return ml.change_level_model(cur)


@app.get("/api/geometry/{ticket_id}")
def geometry_ticket(ticket_id: int, con: Con):
    r = q(con, "SELECT * FROM geometry_delta WHERE ticket_id = %s", [ticket_id])
    if not r:
        raise HTTPException(404, "no artifact analysed for this ticket")
    return r[0]
