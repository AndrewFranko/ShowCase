"""CaseOps ingest job.

    python -m caseops.ingest bootstrap    drop + recreate schema, seed 120 days
    python -m caseops.ingest tick         append one live day (new tickets,
                                          resolutions, occasional incident/change
                                          with warning fan-out) - run repeatedly
    python -m caseops.ingest meshes       generate pre/post 3D artifacts for a
                                          sample of resolved tickets and store
                                          their binary-level change analysis

The mesh generator plants real structure for the change-level model to find:
how much of an artifact a correction touches depends on the DEVICE (make,
detector generation) and the SITE (class), plus effort - never on who the
analyst was. That mirrors the governance rule on the model side: prediction
features are hospital+device only.
"""
from __future__ import annotations

import random
import sys
from datetime import timedelta

from caseops import geometry
from caseops.db import connect, fan_out

DDL = """
CREATE TABLE IF NOT EXISTS geometry_artifact (
    ticket_id int PRIMARY KEY REFERENCES ticket,
    pre_blob  bytea NOT NULL,
    post_blob bytea NOT NULL
);
CREATE TABLE IF NOT EXISTS geometry_delta (
    ticket_id          int PRIMARY KEY REFERENCES ticket,
    bytes_total        int  NOT NULL,
    bytes_changed      int  NOT NULL,
    blocks_total       int  NOT NULL,
    blocks_changed     int  NOT NULL,
    blocks_changed_pct real NOT NULL,
    vertices_total     int  NOT NULL,
    vertices_moved     int  NOT NULL,
    vertices_moved_pct real NOT NULL,
    mean_disp_mm       real NOT NULL,
    max_disp_mm        real NOT NULL
);
"""


def bootstrap() -> None:
    from caseops import fda as fda_mod
    from caseops import seed
    from caseops import vendors as vendors_mod
    seed.main()
    con = connect()
    # every auxiliary table exists from day zero - endpoints must never depend
    # on which ingest command happened to run first (a CI-only crash taught this)
    con.execute(DDL)
    con.execute(fda_mod.DDL)
    con.execute(vendors_mod.DDL)
    con.commit()
    con.close()
    print("bootstrap complete")


def tick(rng: random.Random | None = None) -> dict:
    """One simulated live day appended on top of whatever exists."""
    rng = rng or random.Random()
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT max(created_at)::date + 1 AS day FROM ticket")
    day = cur.fetchone()["day"]
    cur.execute("SELECT hospital_id, array_agg(device_id) AS devs FROM device GROUP BY 1")
    hospitals = {r["hospital_id"]: r["devs"] for r in cur.fetchall()}
    cur.execute("SELECT analyst_id FROM analyst")
    analysts = [r["analyst_id"] for r in cur.fetchall()]

    made = {"tickets": 0, "resolved": 0, "incidents": 0, "changes": 0, "warned": 0}
    n_new = max(5, round(rng.gauss(40, 8)))
    for _ in range(n_new):
        h = rng.choice(list(hospitals))
        cur.execute(
            """INSERT INTO ticket (hospital_id, device_id, status, priority, est_min, created_at)
               VALUES (%s,%s,'open',%s,%s,%s::date + (interval '1 minute' * %s))""",
            (h, rng.choice(hospitals[h]), rng.choices([2, 3, 4], weights=[2, 5, 2])[0],
             max(12, round(rng.gauss(34, 14))), day, rng.randint(360, 1050)))
        made["tickets"] += 1

    # analysts work the queue: oldest open tickets get assigned+resolved
    cur.execute("""SELECT ticket_id, est_min FROM ticket WHERE status='open'
                   ORDER BY created_at LIMIT %s""", (round(n_new * 0.8),))
    for t in cur.fetchall():
        actual = max(8, round(rng.gauss(t["est_min"] * 1.05, 8)))
        cur.execute(
            """UPDATE ticket SET analyst_id=%s, status='resolved', actual_min=%s,
               assigned_at=%s::date + interval '8 hours',
               resolved_at=%s::date + interval '8 hours' + interval '1 minute' * %s
               WHERE ticket_id=%s""",
            (rng.choice(analysts), actual, day, day, actual + rng.randint(10, 200),
             t["ticket_id"]))
        made["resolved"] += 1

    if rng.random() < 0.5:
        h = rng.choice(list(hospitals))
        dev = rng.choice(hospitals[h] + [None])
        cur.execute(
            """INSERT INTO incident (hospital_id, device_id, kind, severity, description, reported_at)
               VALUES (%s,%s,%s,%s,%s,%s::date + interval '10 hours') RETURNING incident_id""",
            (h, dev, "image quality degradation", rng.choice([1, 2, 3]),
             "ingest tick: hospital-reported issue", day))
        made["warned"] += fan_out(cur, "incident", cur.fetchone()["incident_id"], h, dev,
                                  "Incident reported at your ticket's hospital")
        made["incidents"] += 1
    if rng.random() < 0.35:
        h = rng.choice(list(hospitals))
        dev = rng.choice(hospitals[h])
        cur.execute(
            """INSERT INTO hospital_change (hospital_id, device_id, kind, details, occurred_at)
               VALUES (%s,%s,'sw_update','Scanner software updated (ingest tick)',
                       %s::date + interval '7 hours') RETURNING change_id""",
            (h, dev, day))
        made["warned"] += fan_out(cur, "change", cur.fetchone()["change_id"], h, dev,
                                  "Scanner software updated under your ticket")
        made["changes"] += 1

    con.commit()
    con.close()
    print(f"tick {day}: {made}")
    return made


def meshes(sample: int = 500, rng: random.Random | None = None) -> int:
    """Generate pre/post artifacts + binary-level analysis for resolved tickets
    that do not have one yet. The planted signal - and the ONLY signal - is
    device/site structure plus effort:
        Canon reconstructions need broader corrections (+),
        PCD detectors need narrower ones (-),
        office sites correct more than hospitals (+),
        longer tickets touch more of the vessel (+)."""
    rng = rng or random.Random(43)
    con = connect()
    con.execute(DDL)
    cur = con.cursor()
    cur.execute("""
        SELECT t.ticket_id, t.actual_min, d.make, d.detector, h.site_class
        FROM ticket t
        JOIN device d ON d.device_id = t.device_id
        JOIN hospital h ON h.hospital_id = t.hospital_id
        LEFT JOIN geometry_artifact g ON g.ticket_id = t.ticket_id
        WHERE t.status = 'resolved' AND g.ticket_id IS NULL
        ORDER BY t.ticket_id DESC LIMIT %s""", (sample,))
    todo = cur.fetchall()
    for t in todo:
        frac = (0.03
                + (0.05 if t["make"] == "Canon" else 0.0)
                + (-0.018 if t["detector"] == "PCD" else 0.0)
                + (0.022 if t["site_class"] == "office" else 0.0)
                + 0.0009 * (t["actual_min"] or 30)
                + rng.gauss(0, 0.012))
        frac = min(0.45, max(0.005, frac))
        pre = geometry.make_mesh(rng)
        post = geometry.displace(pre, frac, 0.4 + 2.5 * frac, rng)
        pb, qb = pre.tobytes(), post.tobytes()
        bd = geometry.binary_delta(pb, qb)
        vd = geometry.vertex_delta(pre, post)
        cur.execute("""INSERT INTO geometry_artifact (ticket_id, pre_blob, post_blob)
                       VALUES (%s,%s,%s)""", (t["ticket_id"], pb, qb))
        cur.execute("""INSERT INTO geometry_delta VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (t["ticket_id"], bd["bytes_total"], bd["bytes_changed"],
                     bd["blocks_total"], bd["blocks_changed"], bd["blocks_changed_pct"],
                     vd["vertices_total"], vd["vertices_moved"], vd["vertices_moved_pct"],
                     vd["mean_disp_mm"], vd["max_disp_mm"]))
    con.commit()
    con.close()
    print(f"meshes: {len(todo)} artifacts generated and analysed")
    return len(todo)


def fda_refresh() -> dict:
    """Pull live MAUDE + recall signals from openFDA for every fleet model."""
    from caseops import fda as fda_mod
    con = connect()
    con.execute(fda_mod.DDL)
    cur = con.cursor()
    out = fda_mod.refresh(cur)
    con.commit()
    con.close()
    print(f"fda: {out}")
    return out


def vendors_refresh() -> dict:
    """Check every manufacturer's configured page for changes and alert lines."""
    from caseops import vendors as v
    con = connect()
    con.execute(v.DDL)
    cur = con.cursor()
    out = v.refresh(cur)
    con.commit()
    con.close()
    print(f"vendors: {out}")
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tick"
    {"bootstrap": bootstrap, "tick": tick, "meshes": meshes,
     "fda": fda_refresh, "vendors": vendors_refresh}[cmd]()
