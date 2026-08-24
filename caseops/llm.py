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

# The dated aliases retire (gemini-2.0-flash 404s as of Aug 2026);
# "-latest" tracks the current flash model and survives retirements.
MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT_S = 75

SYSTEM = (
    "You are a catch-up assistant for medical-image analysts. Using ONLY the "
    "JSON context, write a brief device update: what changed, what the FDA "
    "signal says about this model line, and what deserves attention before "
    "resuming the listed tickets. Numbered points, max 6, plain language, no "
    "invented facts; if a section has no data, say 'nothing new'. Note that "
    "FDA counts are for the model line (openFDA, unvalidated), not this exact "
    "unit."
)


_ENV_FILE = __import__("pathlib").Path(__file__).resolve().parent.parent / ".env"


def _from_env_file(name: str) -> str:
    """Read ONE variable from the repo-root .env (gitignored). Only the two key
    names are ever read; nothing else in the file is loaded into the process."""
    try:
        raw = _ENV_FILE.read_text(encoding="utf-8-sig")
    except OSError:
        return ""
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip("'\"")
    return ""


def api_key() -> str:
    # GEMINI_API_KEY preferred; GOOGLE_API_KEY is the same credential under
    # Google AI Studio's other conventional name. Shell env wins; the repo-root
    # .env is the fallback so the key survives any process manager.
    return (os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
            or _from_env_file("GEMINI_API_KEY") or _from_env_file("GOOGLE_API_KEY"))


_last_error: str | None = None


def _gemini(context: dict) -> str | None:
    global _last_error
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
    except urllib.error.HTTPError as exc:
        try:
            _last_error = f"HTTP {exc.code}: " + exc.read().decode()[:200]
        except OSError:
            _last_error = f"HTTP {exc.code}"
        return None
    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError) as exc:
        _last_error = f"{type(exc).__name__}: {str(exc)[:150]}"
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
                "note": (f"gemini call failed: {_last_error}" if api_key() and _last_error
                         else "no GEMINI_API_KEY / GOOGLE_API_KEY - set one (env or "
                              "repo-root .env) for the LLM briefing")}
        text = _deterministic(context)
    return {"briefing": text, "provenance": prov}
