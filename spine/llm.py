"""Optional LLM fallback for /api/ask - grounded, keyed, and honest about it.

The deterministic router in spine/ask.py stays the first answerer: same question,
same answer, forever. This module only handles what the router refuses - free-form
phrasings that match no intent - and only when an API key is present in the
environment (ANTHROPIC_API_KEY or LLM_API_KEY). No key, no network call, no
behaviour change: the portal degrades to exactly what it was.

Governance, same boundary as the MCP server:
- The model is grounded on a digest built from the canonical metric layer's own
  handlers - the same aggregates /api/ask already serves. No raw case rows, no
  free-text SQL, no analyst identity (none exists in the spine to begin with).
- The digest travels to the model provider; the spine itself never does. That is
  an explicit data-boundary decision the user made by supplying a key.
- Answers carry provenance naming the model and the grounding, so an LLM answer
  can never masquerade as a deterministic one.

No new dependency: one urllib call to the Messages API.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
MODEL = os.environ.get("LLM_MODEL", "claude-haiku-4-5-20251001")
TIMEOUT_S = 25
MAX_TOKENS = 600

SYSTEM = (
    "You answer questions about a medical-imaging case ledger using ONLY the JSON "
    "digest provided. The digest is the complete set of governed aggregates; there "
    "is no other data. Rules: cite numbers exactly as given; if the digest cannot "
    "answer the question, say so plainly and name the closest metric that could; "
    "never invent values, sites, versions, or hazards; two sentences maximum "
    "unless listing rows the digest contains. FFR-CT threshold context: 0.80 is "
    "the ischemia decision boundary; a correction is 'actionable' when it crosses "
    "it."
)


def api_key() -> str:
    return os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("LLM_API_KEY", "")


def available() -> bool:
    return bool(api_key())


def grounding_digest(con) -> dict[str, Any]:
    """Everything the model is allowed to know: the metric layer's own answers.

    Built by calling the deterministic handlers, so LLM answers can never be
    grounded on anything the governed API would not itself serve.
    """
    from spine import ask as router

    digest: dict[str, Any] = {}
    for handler, name in [
        (router.ask_actionable, "actionable_correction"),
        (router.ask_reject, "rejection"),
        (router.ask_minutes, "effort_minutes"),
        (router.ask_frontier, "automation_frontier"),
        (router.ask_regressions, "release_regressions"),
        (router.ask_disparity, "subgroup_disparity"),
        (router.ask_worst_site, "site_conformance"),
        (router.ask_hazards, "hazards"),
    ]:
        try:
            entry = handler(con, "")
        except Exception as exc:  # a broken handler must not take down /api/ask
            entry = {"unavailable": type(exc).__name__}
        digest[name] = entry
    return digest


def answer(con, question: str) -> dict[str, Any] | None:
    """One grounded Messages call. Returns None on any failure - the caller
    falls back to the deterministic refusal, so the portal never 500s and never
    blocks on the network longer than TIMEOUT_S."""
    key = api_key()
    if not key:
        return None

    digest = grounding_digest(con)
    body = json.dumps({
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM,
        "messages": [{
            "role": "user",
            "content": (
                "Digest:\n" + json.dumps(digest, default=str)
                + "\n\nQuestion: " + question
            ),
        }],
    }).encode()

    req = urllib.request.Request(
        API_URL, data=body, method="POST",
        headers={
            "content-type": "application/json",
            "x-api-key": key,
            "anthropic-version": API_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return None

    text = "".join(
        block.get("text", "")
        for block in payload.get("content", [])
        if block.get("type") == "text"
    ).strip()
    if not text:
        return None

    return {
        "question": question,
        "answer": text,
        "provenance": {
            "router": "llm-grounded fallback (deterministic intents matched nothing)",
            "model": payload.get("model", MODEL),
            "grounding": ("digest of canonical metric-layer aggregates only - "
                          "no raw case rows, no SQL, no identity"),
            "note": ("Non-deterministic: the same question may phrase its answer "
                     "differently. Numbers are constrained to the digest."),
        },
    }
