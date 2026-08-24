"""Gemini-backed catch-up agent for device updates - env-keyed, honest fallback.

The analyst's question: "anything I should know about the devices under my
active tickets?" The agent gathers the governed context - the device, its
hospital's recent changes and incidents, the cached FDA signal for its model,
the vendor-page monitor - and asks Gemini to write the catch-up briefing.

Key: GEMINI_API_KEY in the environment. No key (or any failure) degrades to a
deterministic composer over the same context, and every response carries
provenance saying which path produced it - an LLM answer must never pass as a
deterministic one, and vice versa.

Same data boundary as everywhere in this project: the context contains no
patient data and no analyst identity - only device, site, ticket and public
FDA/vendor facts.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT_S = 30

SYSTEM = (
    "You are a catch-up assistant for medical-image analysts. Using ONLY the "
    "JSON context, write a brief device update: what changed, what the FDA "
    "signal says about this model line, and what deserves attention before "
    "resuming the listed tickets. Numbered points, max 6, plain language, no "
    "invented facts; if a section has no data, say 'nothing new'. Note that "
    "FDA counts are for the model line (openFDA, unvalidated), not this exact "
    "unit."
)


def api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "")


def _gemini(context: dict) -> str | None:
    key = api_key()
    if not key:
        return None
    body = json.dumps({
        "system_instruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{
            "text": "Context:\n" + json.dumps(context, default=str)}]}],
        "generationConfig": {"maxOutputTokens": 700, "temperature": 0.2},
    }).encode()
    req = urllib.request.Request(
        API.format(model=MODEL) + "?key=" + key, data=body, method="POST",
        headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            payload = json.loads(r.read().decode())
        parts = payload["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
        return text or None
    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError):
        return None


def _deterministic(context: dict) -> str:
    """No key / no network: same context, mechanical prose. Less fluent,
    equally grounded."""
    lines = []
    for dev in context.get("devices", []):
        d = dev["device"]
        lines.append(f"— {d['make']} {d['model']} #{d['device_id']} at {dev['hospital']['name']}:")
        ch = dev.get("recent_changes", [])
        inc = dev.get("recent_incidents", [])
        lines.append(f"   site events: {len(ch)} change(s), {len(inc)} open incident(s)"
                     if (ch or inc) else "   site events: nothing new")
        fda = dev.get("fda_signal")
        if fda:
            top = (fda.get("top_problems") or [{}])[0].get("problem", "n/a")
            lines.append(f"   FDA model line: {fda.get('maude_total', '?')} MAUDE reports, "
                         f"{fda.get('recall_total', '?')} recalls; top problem: {top}")
        else:
            lines.append("   FDA model line: no cached signal (run the FDA refresh)")
        va = dev.get("vendor_page")
        if va:
            lines.append(f"   vendor page: {'CHANGED since last check' if va.get('changed') else 'unchanged'}, "
                         f"{len(va.get('matches') or [])} keyword hit(s)")
        tix = dev.get("tickets", [])
        if tix:
            lines.append("   your tickets here: " + ", ".join(
                f"#{t['ticket_id']} ({t['status']})" for t in tix[:6]))
    return "\n".join(lines) or "No active devices - nothing to catch up on."


def device_briefing(context: dict) -> dict:
    text = _gemini(context)
    if text is not None:
        prov = {"agent": "gemini", "model": MODEL,
                "grounding": "device/site/ticket facts + cached FDA + vendor monitor; "
                             "no patient data, no analyst identity"}
    else:
        prov = {"agent": "deterministic composer",
                "note": ("GEMINI_API_KEY not set or call failed - set the key to "
                         "get the LLM briefing; content is the same governed context")}
        text = _deterministic(context)
    return {"briefing": text, "provenance": prov}
