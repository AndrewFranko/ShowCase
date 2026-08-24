"""FDA database monitoring for the device fleet - REAL data, not synthetic.

The fleet's scanner models are real commercial devices, so openFDA answers real
questions about them:

    device/event.json   MAUDE adverse-event reports (totals, top reported
                        product problems, recent narratives)
    device/recall.json  recalls: what was pulled and why - the 'news' of
                        reported problems for a model line

Results are cached in Postgres (fda_signal) by `python -m caseops.ingest fda`
or POST /api/fda/refresh; the UI reads only the cache, so the portal works
offline and never hammers the API. openFDA's own disclaimer applies and is
surfaced in the UI: unvalidated data, not for care decisions.

No key required at this volume (240 req/min/IP unauthenticated).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.fda.gov/device"
TIMEOUT_S = 20

# fleet model -> the search term MAUDE/recall records actually use.
# Deliberately the MODEL LINE (not exact SKU): FDA free text is messy, and a
# narrow term silently under-reports - worse than over-matching for monitoring.
SEARCH_TERMS = {
    "SOMATOM Force": "SOMATOM",
    "NAEOTOM Alpha": "NAEOTOM",
    "Revolution Apex": "REVOLUTION APEX",
    "Spectral CT 7500": "SPECTRAL CT",
    "Aquilion ONE": "AQUILION",
}

DDL = """
CREATE TABLE IF NOT EXISTS fda_signal (
    make       text NOT NULL,
    model      text NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    payload    jsonb NOT NULL,
    PRIMARY KEY (make, model)
);
"""


def _get(path: str, params: dict) -> dict:
    url = f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return json.loads(r.read().decode())


def _quote(term: str) -> str:
    return '"' + term + '"'


def fetch_model_signal(term: str) -> dict:
    """Everything the monitor tracks for one model line. Each section fails
    soft: a partial signal beats no signal."""
    out: dict = {"term": term}
    try:
        d = _get("event.json", {"search": f"device.brand_name:{_quote(term)}", "limit": 1})
        out["maude_total"] = d.get("meta", {}).get("results", {}).get("total", 0)
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        out["maude_total"] = None

    try:
        d = _get("event.json", {"search": f"device.brand_name:{_quote(term)}",
                                "count": "product_problems.exact", "limit": 10})
        out["top_problems"] = [{"problem": r["term"], "count": r["count"]}
                               for r in d.get("results", [])][:10]
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        out["top_problems"] = []

    try:
        d = _get("event.json", {"search": f"device.brand_name:{_quote(term)}",
                                "sort": "date_received:desc", "limit": 5})
        out["recent_events"] = [{
            "date": r.get("date_received", ""),
            "event_type": r.get("event_type", ""),
            "problems": (r.get("product_problems") or [])[:3],
            "text": ((r.get("mdr_text") or [{}])[0].get("text") or "")[:300],
        } for r in d.get("results", [])]
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        out["recent_events"] = []

    try:
        d = _get("recall.json", {"search": f"product_description:{_quote(term)}",
                                 "sort": "event_date_initiated:desc", "limit": 5})
        out["recall_total"] = d.get("meta", {}).get("results", {}).get("total", 0)
        out["recalls"] = [{
            "date": r.get("event_date_initiated", ""),
            "status": r.get("recall_status", ""),
            "product": (r.get("product_description") or "")[:160],
            "reason": (r.get("reason_for_recall")
                       or r.get("root_cause_description") or "")[:300],
        } for r in d.get("results", [])]
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        out["recall_total"] = None
        out["recalls"] = []
    return out


def refresh(cur) -> dict:
    """Fetch fresh signals for every model in the fleet and upsert the cache."""
    cur.execute("SELECT DISTINCT make, model FROM device ORDER BY make, model")
    fleet = cur.fetchall()
    updated, errors = 0, 0
    for row in fleet:
        term = SEARCH_TERMS.get(row["model"], row["model"])
        sig = fetch_model_signal(term)
        if sig.get("maude_total") is None and not sig.get("recalls"):
            errors += 1
            continue
        cur.execute(
            """INSERT INTO fda_signal (make, model, payload, fetched_at)
               VALUES (%s, %s, %s, now())
               ON CONFLICT (make, model)
               DO UPDATE SET payload = EXCLUDED.payload, fetched_at = now()""",
            (row["make"], row["model"], json.dumps(sig)))
        updated += 1
    return {"models": len(fleet), "updated": updated, "errors": errors}
