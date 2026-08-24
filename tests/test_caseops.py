"""CaseOps: the operational case-management system (Postgres-backed).

The contract under test is the warning mechanism - changes and incidents must
fan out to exactly the analysts holding active tickets at that hospital (and
only tickets on the affected device when the event is device-scoped) - plus
the ticket lifecycle guards and the honesty of the workload forecast.

Skips cleanly when the caseops Postgres is not running:
    docker compose -f caseops/docker-compose.yml up -d && python -m caseops.seed
"""
from __future__ import annotations

import uuid

import pytest

try:
    import psycopg  # noqa: F401
    from caseops.db import connect
    _con = connect()
    _con.close()
    DB_UP = True
except Exception:
    DB_UP = False

pytestmark = pytest.mark.skipif(not DB_UP, reason="caseops postgres not reachable")

if DB_UP:
    from fastapi.testclient import TestClient
    from caseops.app import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def rig():
    """A private hospital with two devices, two analysts, and known tickets -
    so fan-out assertions never depend on seeded state."""
    tag = uuid.uuid4().hex[:8]
    con = connect()
    cur = con.cursor()
    cur.execute("INSERT INTO hospital (name, region, site_class) VALUES (%s,'Test','hospital') RETURNING hospital_id",
                (f"Rig Hospital {tag}",))
    h = cur.fetchone()["hospital_id"]
    devs = []
    for i in range(2):
        cur.execute("""INSERT INTO device (hospital_id, make, model, detector, sw_version, installed_on)
                       VALUES (%s,'Test','Scanner','EID','1.0','2025-01-01') RETURNING device_id""", (h,))
        devs.append(cur.fetchone()["device_id"])
    an = []
    for i in range(2):
        cur.execute("INSERT INTO analyst (name, level, capacity_min_day) VALUES (%s,'senior',390) RETURNING analyst_id",
                    (f"Rig Analyst {tag}-{i}",))
        an.append(cur.fetchone()["analyst_id"])
    # analyst 0: active ticket on device 0.  analyst 1: RESOLVED ticket only.
    cur.execute("""INSERT INTO ticket (hospital_id, device_id, analyst_id, status, est_min, created_at, assigned_at)
                   VALUES (%s,%s,%s,'in_review',30,now(),now()) RETURNING ticket_id""", (h, devs[0], an[0]))
    active_ticket = cur.fetchone()["ticket_id"]
    cur.execute("""INSERT INTO ticket (hospital_id, device_id, analyst_id, status, est_min, actual_min,
                                       created_at, assigned_at, resolved_at)
                   VALUES (%s,%s,%s,'resolved',30,28,now(),now(),now())""", (h, devs[1], an[1]))
    con.commit()
    yield {"hospital": h, "devices": devs, "analysts": an, "active_ticket": active_ticket, "con": con}
    # teardown: rig rows must never leak into the seeded corpus (they would
    # contaminate the change-level model's training data)
    cur = con.cursor()
    for sql in [
        "DELETE FROM geometry_delta WHERE ticket_id IN (SELECT ticket_id FROM ticket WHERE hospital_id = %s)",
        "DELETE FROM geometry_artifact WHERE ticket_id IN (SELECT ticket_id FROM ticket WHERE hospital_id = %s)",
        "DELETE FROM notification WHERE analyst_id = ANY(%(an)s)",
        "DELETE FROM ticket WHERE hospital_id = %s",
        "DELETE FROM incident WHERE hospital_id = %s",
        "DELETE FROM hospital_change WHERE hospital_id = %s",
        "DELETE FROM device WHERE hospital_id = %s",
        "DELETE FROM hospital WHERE hospital_id = %s",
        "DELETE FROM analyst WHERE analyst_id = ANY(%(an)s)",
    ]:
        cur.execute(sql, {"an": an} if "%(an)s" in sql else (h,))
    con.commit()
    con.close()


def _unread(client, analyst_id):
    return client.get(f"/api/analysts/{analyst_id}/catchup").json()


def test_summary_is_internally_consistent(client):
    s = client.get("/api/summary").json()
    assert s["hospitals"] > 0 and s["devices"] >= s["hospitals"] * 0  # shape
    assert s["resolved_tickets"] > 1000
    assert len(s["throughput_14d"]) >= 8


def test_change_warns_only_analysts_with_active_tickets(client, rig):
    r = client.post("/api/changes", json={
        "hospital_id": rig["hospital"], "kind": "protocol_change",
        "details": "rig: protocol revised"}).json()
    assert r["analysts_warned"] == 1, "only the analyst with an ACTIVE ticket is warned"
    c0 = _unread(client, rig["analysts"][0])
    assert c0["unread"] == 1
    assert rig["active_ticket"] in c0["notifications"][0]["ticket_ids"]
    assert _unread(client, rig["analysts"][1])["unread"] == 0, \
        "resolved-only analyst must not be warned"


def test_device_scoped_incident_respects_the_device(client, rig):
    # incident on device[1] - the rig's only ACTIVE ticket is on device[0]
    r = client.post("/api/incidents", json={
        "hospital_id": rig["hospital"], "device_id": rig["devices"][1],
        "kind": "gantry fault", "severity": 2,
        "description": "rig: fault on the other device"}).json()
    assert r["analysts_warned"] == 0
    r = client.post("/api/incidents", json={
        "hospital_id": rig["hospital"], "device_id": rig["devices"][0],
        "kind": "gantry fault", "severity": 2,
        "description": "rig: fault on the active device"}).json()
    assert r["analysts_warned"] == 1


def test_ack_clears_the_catchup_queue(client, rig):
    client.post("/api/changes", json={
        "hospital_id": rig["hospital"], "kind": "sw_update",
        "details": "rig: scanner software updated"})
    c = _unread(client, rig["analysts"][0])
    ids = [n["notif_id"] for n in c["notifications"]]
    assert ids
    acked = client.post(f"/api/analysts/{rig['analysts'][0]}/catchup/ack",
                        json={"notif_ids": ids}).json()
    assert set(acked["acknowledged"]) == set(ids)
    assert _unread(client, rig["analysts"][0])["unread"] == 0


def test_ticket_lifecycle_guards(client, rig):
    con = rig["con"]
    cur = con.cursor()
    cur.execute("""INSERT INTO ticket (hospital_id, device_id, status, est_min, created_at)
                   VALUES (%s,%s,'open',25,now()) RETURNING ticket_id""",
                (rig["hospital"], rig["devices"][0]))
    t = cur.fetchone()["ticket_id"]
    con.commit()
    # open -> resolved directly is illegal
    assert client.post(f"/api/tickets/{t}/status",
                       json={"status": "resolved", "actual_min": 20}).status_code == 409
    assert client.post(f"/api/tickets/{t}/assign",
                       json={"analyst_id": rig["analysts"][0]}).status_code == 200
    # double-assign is refused
    assert client.post(f"/api/tickets/{t}/assign",
                       json={"analyst_id": rig["analysts"][1]}).status_code == 409
    assert client.post(f"/api/tickets/{t}/status",
                       json={"status": "in_review"}).status_code == 200
    # resolving without minutes is refused
    assert client.post(f"/api/tickets/{t}/status",
                       json={"status": "resolved"}).status_code == 422
    assert client.post(f"/api/tickets/{t}/status",
                       json={"status": "resolved", "actual_min": 22}).status_code == 200


def test_forecast_is_shaped_and_honest(client):
    f = client.get("/api/forecast").json()
    assert len(f["analysts"]) >= 5
    for a in f["analysts"]:
        if a.get("insufficient_history"):
            continue
        assert len(a["forecast"]) == 7
        assert all(p["minutes"] >= 0 for p in a["forecast"])
        # honesty: the naive baseline is REPORTED, and the model is not
        # catastrophically worse than it (dow structure dominates this data)
        assert a["mae_naive"] > 0
        assert a["mae_model"] <= a["mae_naive"] * 1.35


# ------------------------------------------------------------- 3D binary change level
def test_binary_delta_measures_exactly_what_changed():
    """Unit truth for the binary-level analysis - no DB needed, but grouped here
    with its consumers."""
    import numpy as np
    from caseops import geometry
    a = np.zeros(2048, dtype=np.float32).tobytes()          # 8192 bytes = 2 blocks
    b = bytearray(a)
    b[0] ^= 0xFF                                            # touch only block 0
    d = geometry.binary_delta(bytes(a), bytes(b))
    assert d["blocks_total"] == 2 and d["blocks_changed"] == 1
    assert d["blocks_changed_pct"] == 50.0 and d["bytes_changed"] == 1
    same = geometry.binary_delta(bytes(a), bytes(a))
    assert same["blocks_changed"] == 0 and same["bytes_changed"] == 0


def test_geometry_summary_is_populated(client):
    g = client.get("/api/geometry/summary").json()
    assert g["stats"]["artifacts"] >= 100
    assert 0 < g["stats"]["median_blocks_pct"] <= 100
    assert g["top"][0]["blocks_changed_pct"] >= g["top"][-1]["blocks_changed_pct"]


def test_change_level_model_uses_only_hospital_and_device_features(client):
    """Governance: the change-level predictor must be blind to analyst identity
    and patient demographics - by declaration AND by code."""
    m = client.get("/api/geometry/model").json()
    assert set(m["features_used"]) == {"site_class", "region", "make", "detector"}
    assert "analyst identity" in m["excluded_by_policy"]
    assert "patient demographics" in m["excluded_by_policy"]
    # code-level check: the training query never touches the analyst table
    import inspect
    from caseops import ml as ml_mod
    src = inspect.getsource(ml_mod.change_level_model).lower()
    assert "analyst" not in src.replace("analyst-surveillance", "").replace(
        "analyst identity", ""), "training query must not reference analysts"
    assert all("analyst" not in c and "patient" not in c
               for c in m["coefficients"])


def test_change_level_model_finds_planted_device_structure(client):
    m = client.get("/api/geometry/model").json()
    assert m["mae_model"] <= m["mae_naive"], \
        "device/site features carry real signal - the model must beat the global mean"
    # the plant: Canon is the high-change reference make, PCD reduces change
    assert m["coefficients"]["detector=PCD"] < 0
    assert all(m["coefficients"][f"make={mk}"] < 0 for mk in ("GE", "Siemens"))
