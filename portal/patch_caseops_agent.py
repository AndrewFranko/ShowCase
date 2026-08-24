"""CaseOps: per-model FDA check, device drill-down with its cases, vendor-page
monitor endpoints, Gemini catch-up briefing, and the ingest `vendors` command."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------- app.py
a = ROOT / "caseops" / "app.py"
s = a.read_text(encoding="utf-8")

anchor = "# ---------------------------------------------------------------- client"
assert s.count(anchor) == 1
s = s.replace(anchor, '''@app.post("/api/fda/refresh/{make}/{model}")
def fda_refresh_one(make: str, model: str, con: Con):
    """The per-model 'check FDA now' button: one live openFDA query, cache
    updated, fresh payload returned."""
    from caseops import fda as fda_mod
    con.execute(fda_mod.DDL)
    rows_ = q(con, "SELECT 1 FROM device WHERE make = %s AND model = %s LIMIT 1",
              [make, model])
    if not rows_:
        raise HTTPException(404, "no such device model in the fleet")
    term = fda_mod.SEARCH_TERMS.get(model, model)
    sig = fda_mod.fetch_model_signal(term)
    if sig.get("maude_total") is None and not sig.get("recalls"):
        raise HTTPException(502, "openFDA unreachable - cached signal kept")
    import json as _json
    q(con, """INSERT INTO fda_signal (make, model, payload, fetched_at)
              VALUES (%s, %s, %s, now())
              ON CONFLICT (make, model)
              DO UPDATE SET payload = EXCLUDED.payload, fetched_at = now()
              RETURNING make""", [make, model, _json.dumps(sig)])
    return {"make": make, "model": model, "payload": sig, "checked": "live"}


@app.get("/api/devices/{device_id}")
def device_detail(device_id: int, con: Con):
    """One physical device: its hospital, its CASES, its site events, and the
    FDA signal for its model line - the case<->device association, resolved."""
    ds = q(con, """SELECT d.*, h.name AS hospital, h.region, h.site_class
                   FROM device d JOIN hospital h USING (hospital_id)
                   WHERE d.device_id = %s""", [device_id])
    if not ds:
        raise HTTPException(404, "no such device")
    d = ds[0]
    d["tickets"] = q(con, """
        SELECT t.ticket_id, t.status, t.priority, t.est_min, t.actual_min,
               t.created_at, a.name AS analyst
        FROM ticket t LEFT JOIN analyst a USING (analyst_id)
        WHERE t.device_id = %s ORDER BY t.status <> 'resolved' DESC, t.created_at DESC
        LIMIT 30""", [device_id])
    d["open_count"] = sum(1 for t in d["tickets"] if t["status"] != "resolved")
    d["changes"] = q(con, """SELECT * FROM hospital_change
                             WHERE device_id = %s OR (hospital_id = %s AND device_id IS NULL)
                             ORDER BY occurred_at DESC LIMIT 8""",
                     [device_id, d["hospital_id"]])
    d["incidents"] = q(con, """SELECT * FROM incident
                               WHERE device_id = %s OR (hospital_id = %s AND device_id IS NULL)
                               ORDER BY reported_at DESC LIMIT 8""",
                       [device_id, d["hospital_id"]])
    fda_rows = q(con, "SELECT payload, fetched_at FROM fda_signal WHERE make = %s AND model = %s",
                 [d["make"], d["model"]])
    d["fda_signal"] = fda_rows[0]["payload"] if fda_rows else None
    d["fda_fetched_at"] = fda_rows[0]["fetched_at"] if fda_rows else None
    va = q(con, "SELECT * FROM vendor_alert WHERE make = %s", [d["make"]])
    d["vendor_page"] = va[0] if va else None
    return d


# ---------------------------------------------------------------- vendor pages
@app.get("/api/vendors/alerts")
def vendor_alerts(con: Con):
    from caseops import vendors as v
    con.execute(v.DDL)
    return {"alerts": q(con, "SELECT * FROM vendor_alert ORDER BY make"),
            "note": ("page-change monitor: any change since the last check is "
                     "flagged; matched lines mention our models or alert keywords. "
                     "URLs are configuration - point them at each vendor's exact "
                     "advisory page.")}


@app.post("/api/vendors/refresh")
def vendor_refresh(con: Con):
    from caseops import vendors as v
    con.execute(v.DDL)
    with con.cursor() as cur:
        return v.refresh(cur)


# ---------------------------------------------------------------- catch-up agent
@app.get("/api/analysts/{analyst_id}/device-briefing")
def device_briefing(analyst_id: int, con: Con):
    """The catch-up agent: everything worth knowing about the devices under
    this analyst's ACTIVE tickets - written by Gemini when GEMINI_API_KEY is
    set, by a deterministic composer otherwise. Provenance always says which."""
    from caseops import llm as llm_mod
    from caseops import vendors as v
    con.execute(v.DDL)
    devs = q(con, """
        SELECT DISTINCT d.device_id FROM ticket t JOIN device d USING (device_id)
        WHERE t.analyst_id = %s AND t.status = ANY(%s)""",
        [analyst_id, list(ACTIVE_STATUSES)])
    context = {"analyst_ref": f"analyst #{analyst_id}", "devices": []}
    for row in devs:
        d = device_detail(row["device_id"], con)
        context["devices"].append({
            "device": {k: d[k] for k in ("device_id", "make", "model", "detector", "sw_version")},
            "hospital": {"name": d["hospital"], "region": d["region"],
                         "site_class": d["site_class"]},
            "tickets": [t for t in d["tickets"] if t["status"] != "resolved"],
            "recent_changes": [{"kind": c["kind"], "details": c["details"],
                                "occurred_at": c["occurred_at"]} for c in d["changes"][:5]],
            "recent_incidents": [{"kind": i["kind"], "severity": i["severity"],
                                  "status": i["status"]} for i in d["incidents"][:5]
                                 if i["status"] == "open"],
            "fda_signal": ({k: d["fda_signal"].get(k) for k in
                            ("maude_total", "recall_total", "top_problems")}
                           if d["fda_signal"] else None),
            "vendor_page": ({"changed": d["vendor_page"]["changed"],
                             "matches": d["vendor_page"]["matches"][:5]}
                            if d["vendor_page"] else None),
        })
    out = llm_mod.device_briefing(context)
    out["devices_covered"] = len(context["devices"])
    return out


# ---------------------------------------------------------------- client''')
a.write_text(s, encoding="utf-8")

# ---------------------------------------------------------------- ingest.py
i = ROOT / "caseops" / "ingest.py"
s = i.read_text(encoding="utf-8")
old = '''if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tick"
    {"bootstrap": bootstrap, "tick": tick, "meshes": meshes, "fda": fda_refresh}[cmd]()'''
new = '''def vendors_refresh() -> dict:
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
     "fda": fda_refresh, "vendors": vendors_refresh}[cmd]()'''
assert s.count(old) == 1
i.write_text(s.replace(old, new), encoding="utf-8")
print("app.py + ingest.py patched")
