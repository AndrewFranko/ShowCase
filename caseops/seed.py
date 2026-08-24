"""Deterministic seed for CaseOps: 22 hospitals, ~50 devices, 10 analysts,
120 days of ticket history with a real weekday pattern and per-analyst trends
(so the workload model has something honest to learn), plus incidents, changes,
and the notifications those events fanned out at the time.

Run:  python -m caseops.seed        (drops and recreates everything)
"""
from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from caseops.db import connect, fan_out

rng = random.Random(41)

TODAY = date(2026, 8, 24)
DAYS = 120

REGIONS = ["Northeast", "Southeast", "Midwest", "Southwest", "West", "Great Lakes"]
H_STEMS = ["Riverbend", "Harborview", "Cedar Ridge", "Summit", "Lakeview", "Stonegate",
           "Fairmount", "Baypoint", "Ironwood", "Northshore", "Granite Bay", "Pinecrest",
           "Eastvale", "Westgate", "Foxglove", "Brookhaven", "Ashford", "Dunmore",
           "Inglewood", "Clearwater", "Highland Park", "Silver Creek"]
H_KINDS = ["Medical Center", "Heart & Vascular", "Cardiology Associates", "Imaging Partners"]
SCANNERS = [("Siemens", "SOMATOM Force", "EID"), ("Siemens", "NAEOTOM Alpha", "PCD"),
            ("GE", "Revolution Apex", "EID"), ("Philips", "Spectral CT 7500", "EID"),
            ("Canon", "Aquilion ONE", "EID")]
SW = ["7.2.1", "7.3.0", "7.3.2", "8.0.1"]
ANALYSTS = [("Rivera", "lead", 420), ("Chen", "senior", 390), ("Okafor", "senior", 390),
            ("Novak", "senior", 360), ("Ito", "junior", 330), ("Haddad", "junior", 330),
            ("Lindqvist", "senior", 390), ("Moreau", "junior", 300), ("Adeyemi", "senior", 360),
            ("Kowalski", "junior", 330)]
INCIDENT_KINDS = ["image quality degradation", "transfer failure", "protocol deviation",
                  "contrast timing issue", "gantry fault"]
CHANGE_KINDS = ["sw_update", "protocol_change", "detector_upgrade", "device_swap"]

# weekday volume shape (Mon..Sun): scanning is a weekday business
DOW_W = [1.15, 1.1, 1.0, 1.05, 0.95, 0.25, 0.1]


def ts(d: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(d, time(hour, minute), tzinfo=timezone.utc)


def main() -> None:
    con = connect()
    cur = con.cursor()
    cur.execute((Path(__file__).parent / "schema.sql").read_text())

    hospitals = []
    for i, stem in enumerate(H_STEMS):
        name = f"{stem} {H_KINDS[i % len(H_KINDS)]}"
        cur.execute(
            "INSERT INTO hospital (name, region, site_class) VALUES (%s,%s,%s) RETURNING hospital_id",
            (name, REGIONS[i % len(REGIONS)], "hospital" if i % 3 else "office"))
        hospitals.append(cur.fetchone()["hospital_id"])

    devices, dev_of = [], {}
    for h in hospitals:
        for _ in range(rng.choice([1, 2, 2, 3])):
            make, model, det = rng.choice(SCANNERS)
            cur.execute(
                """INSERT INTO device (hospital_id, make, model, detector, sw_version, installed_on)
                   VALUES (%s,%s,%s,%s,%s,%s) RETURNING device_id""",
                (h, make, model, det, rng.choice(SW),
                 TODAY - timedelta(days=rng.randint(200, 1500))))
            d = cur.fetchone()["device_id"]
            devices.append(d)
            dev_of.setdefault(h, []).append(d)

    analysts = []
    for name, level, cap in ANALYSTS:
        cur.execute(
            "INSERT INTO analyst (name, level, capacity_min_day) VALUES (%s,%s,%s) RETURNING analyst_id",
            (name, level, cap))
        analysts.append(cur.fetchone()["analyst_id"])

    # hospital weights: some sites are simply busier
    hw = {h: rng.uniform(0.4, 2.2) for h in hospitals}
    # per-analyst trend for the model to find: some ramping up, one winding down
    trend = {a: rng.choice([0.0, 0.0, 0.15, 0.25, -0.2]) for a in analysts}

    for back in range(DAYS, -1, -1):
        d = TODAY - timedelta(days=back)
        n_day = max(0, round(rng.gauss(46 * DOW_W[d.weekday()], 6)))
        for _ in range(n_day):
            h = rng.choices(hospitals, weights=[hw[x] for x in hospitals])[0]
            dev = rng.choice(dev_of[h])
            est = max(12, round(rng.gauss(34, 14)))
            created = ts(d, rng.randint(6, 17), rng.randint(0, 59))
            if back <= 2 and rng.random() < 0.55:          # recent tail stays open
                cur.execute(
                    """INSERT INTO ticket (hospital_id, device_id, status, priority, est_min, created_at)
                       VALUES (%s,%s,'open',%s,%s,%s)""",
                    (h, dev, rng.choices([2, 3, 4], weights=[2, 5, 2])[0], est, created))
                continue
            a = rng.choice(analysts)
            speed = 1.0 + trend[a] * (DAYS - back) / DAYS   # trend in DAILY LOAD
            actual = max(8, round(rng.gauss(est * rng.uniform(0.8, 1.3) * max(0.5, speed), 6)))
            if back <= 5 and rng.random() < 0.30:           # in-flight work
                st = rng.choice(["assigned", "in_review", "blocked"])
                cur.execute(
                    """INSERT INTO ticket (hospital_id, device_id, analyst_id, status, priority,
                                           est_min, created_at, assigned_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (h, dev, a, st, rng.choices([1, 2, 3, 4], weights=[1, 3, 5, 2])[0],
                     est, created, created + timedelta(minutes=rng.randint(10, 240))))
            else:
                assigned = created + timedelta(minutes=rng.randint(10, 300))
                resolved = assigned + timedelta(minutes=actual + rng.randint(5, 180))
                cur.execute(
                    """INSERT INTO ticket (hospital_id, device_id, analyst_id, status, priority,
                                           est_min, actual_min, created_at, assigned_at, resolved_at)
                       VALUES (%s,%s,%s,'resolved',%s,%s,%s,%s,%s,%s)""",
                    (h, dev, a, rng.choices([2, 3, 4], weights=[3, 5, 2])[0],
                     est, actual, created, assigned, resolved))

    # incidents and changes across the window; recent ones fan out warnings
    # against today's active tickets, exactly as the live endpoint would.
    for back in sorted(rng.sample(range(0, DAYS), 42), reverse=True):
        d = TODAY - timedelta(days=back)
        h = rng.choice(hospitals)
        dev = rng.choice(dev_of[h] + [None])
        kind = rng.choice(INCIDENT_KINDS)
        sev = rng.choices([1, 2, 3, 4], weights=[3, 4, 2, 1])[0]
        cur.execute(
            """INSERT INTO incident (hospital_id, device_id, kind, severity, status, reported_at, description)
               VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING incident_id""",
            (h, dev, kind, sev, "open" if back < 7 else rng.choice(["ack", "closed"]),
             ts(d, rng.randint(7, 18)),
             f"Hospital reported: {kind}" + (f" on device {dev}" if dev else " (site-wide)")))
        iid = cur.fetchone()["incident_id"]
        if back < 7:
            fan_out(cur, "incident", iid, h, dev,
                    f"Incident (severity {sev}) at hospital {h}: {kind}")

    for back in sorted(rng.sample(range(0, DAYS), 26), reverse=True):
        d = TODAY - timedelta(days=back)
        h = rng.choice(hospitals)
        kind = rng.choice(CHANGE_KINDS)
        dev = rng.choice(dev_of[h]) if kind != "protocol_change" else None
        details = {"sw_update": "Scanner software updated",
                   "protocol_change": "Acquisition protocol revised (site-wide)",
                   "detector_upgrade": "Detector upgraded EID -> PCD",
                   "device_swap": "Scanner replaced"}[kind]
        cur.execute(
            """INSERT INTO hospital_change (hospital_id, device_id, kind, occurred_at, details)
               VALUES (%s,%s,%s,%s,%s) RETURNING change_id""",
            (h, dev, kind, ts(d, rng.randint(6, 20)), details))
        cid = cur.fetchone()["change_id"]
        if kind == "detector_upgrade" and dev:
            cur.execute("UPDATE device SET detector = 'PCD' WHERE device_id = %s", (dev,))
        if back < 7:
            fan_out(cur, "change", cid, h, dev, f"{details} at hospital {h}")

    con.commit()
    for t in ["hospital", "device", "analyst", "ticket", "incident",
              "hospital_change", "notification"]:
        cur.execute(f"SELECT count(*) AS n FROM {t}")
        print(f"  {t:16s} {cur.fetchone()['n']:>6}")
    con.close()


if __name__ == "__main__":
    main()
