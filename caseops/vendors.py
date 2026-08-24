"""Manufacturer web-page monitoring for device alerts.

Vendor advisory pages have no API, unstable URLs, and JS-heavy layouts - so the
honest mechanism is: fetch the configured page per manufacturer, strip it to
text, keep (a) a content hash so ANY change since the last check is flagged,
and (b) every line mentioning one of our model keywords or an alert keyword
(recall / safety / advisory / correction / urgent). Results are cached in
Postgres; the UI reads the cache. URLs are configuration, not code truth -
point them at the exact advisory page for each vendor when known.
"""
from __future__ import annotations

import hashlib
import html
import re
import urllib.error
import urllib.request

TIMEOUT_S = 20
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CaseOps-monitor/0.1"

# make -> page to watch (safe defaults; replace with exact advisory pages)
VENDOR_PAGES = {
    "Siemens": "https://www.siemens-healthineers.com/",
    "GE": "https://www.gehealthcare.com/",
    "Philips": "https://www.philips.com/healthcare",
    "Canon": "https://global.medical.canon/",
}

MODEL_KEYWORDS = ["somatom", "naeotom", "revolution apex", "spectral ct", "aquilion"]
ALERT_KEYWORDS = ["recall", "safety notice", "field safety", "advisory",
                  "urgent", "correction", "hazard"]

DDL = """
CREATE TABLE IF NOT EXISTS vendor_alert (
    make        text PRIMARY KEY,
    url         text NOT NULL,
    fetched_at  timestamptz NOT NULL DEFAULT now(),
    content_sha text,
    changed     boolean NOT NULL DEFAULT false,
    reachable   boolean NOT NULL DEFAULT false,
    matches     jsonb NOT NULL DEFAULT '[]'
);
"""

_TAG = re.compile(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>|<[^>]+>")


def page_text(raw: str) -> str:
    return html.unescape(_TAG.sub(" ", raw))


def extract_matches(text: str, limit: int = 12) -> list[dict]:
    """Lines that mention one of OUR models or an alert keyword - the part of
    the page worth a human's attention."""
    out, seen = [], set()
    for line in (ln.strip() for ln in re.split(r"[\r\n]+", text)):
        if not 15 <= len(line) <= 300:
            continue
        low = line.lower()
        model = next((k for k in MODEL_KEYWORDS if k in low), None)
        alert = next((k for k in ALERT_KEYWORDS if k in low), None)
        if not (model or alert):
            continue
        key = low[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append({"line": line[:300], "model": model, "alert": alert})
        if len(out) >= limit:
            break
    return out


def fetch_vendor(url: str) -> dict:
    try:
        req = urllib.request.Request(url, headers={"user-agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            raw = r.read(1_500_000).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"reachable": False, "error": str(exc)[:200]}
    text = page_text(raw)
    return {
        "reachable": True,
        "content_sha": hashlib.sha256(text.encode()).hexdigest(),
        "matches": extract_matches(text),
    }


def refresh(cur) -> dict:
    updated, changed, unreachable = 0, 0, 0
    for make, url in VENDOR_PAGES.items():
        got = fetch_vendor(url)
        if not got["reachable"]:
            unreachable += 1
            cur.execute(
                """INSERT INTO vendor_alert (make, url, reachable, changed, fetched_at)
                   VALUES (%s, %s, false, false, now())
                   ON CONFLICT (make) DO UPDATE
                   SET reachable = false, changed = false, fetched_at = now(), url = EXCLUDED.url""",
                (make, url))
            continue
        cur.execute("SELECT content_sha FROM vendor_alert WHERE make = %s", (make,))
        prev = cur.fetchone()
        did_change = bool(prev and prev["content_sha"]
                          and prev["content_sha"] != got["content_sha"])
        changed += did_change
        import json as _json
        cur.execute(
            """INSERT INTO vendor_alert (make, url, reachable, changed, content_sha, matches, fetched_at)
               VALUES (%s, %s, true, %s, %s, %s, now())
               ON CONFLICT (make) DO UPDATE
               SET reachable = true, changed = EXCLUDED.changed,
                   content_sha = EXCLUDED.content_sha,
                   matches = EXCLUDED.matches, fetched_at = now(), url = EXCLUDED.url""",
            (make, url, did_change, got["content_sha"], _json.dumps(got["matches"])))
        updated += 1
    return {"vendors": len(VENDOR_PAGES), "updated": updated,
            "changed_since_last_check": changed, "unreachable": unreachable}
