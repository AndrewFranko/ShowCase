"""
The action layer - where findings become work.

Everything before this observed. This module is the write path, and its boundary
is deliberate and narrow:

  WRITES GO TO A SEPARATE STORE (data/actions.duckdb). The spine stays read-only;
  nothing here can touch a case, a result, or the warehouse the metrics read.
  Routing or dispositioning a CASE is device software and stays forbidden.
  Acknowledging, investigating and resolving a FINDING is QMS workflow - the same
  class of software as a complaint-handling system, squarely inside Computer
  Software Assurance. The validation plan records this re-assessment.

Design points a reviewer will care about:

  Append-only audit.  Every transition is an event row that is never updated or
  deleted. The current state is just the fold of the events. "Who decided what,
  when, and why" is answerable months later without archaeology.

  Idempotent sync.  sync_findings() derives work items from the CURRENT warehouse
  (escalated disparity arms, confirmed regressions, excess-rejection sites,
  hazards with complaint load) keyed by (kind, subject). Re-running creates
  nothing twice and never resurrects an item a human closed.

  Evidence pinning.  Each item snapshots the numbers AND the warehouse grain hash
  at creation, so a work item still says what the data looked like when it was
  raised, even after the warehouse moves.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from spine import evidence, metrics

import os

ROOT = Path(__file__).resolve().parent.parent
# Configurable because the container runs a read-only root filesystem: workflow
# state must live on a declared writable volume, not wherever the code sits.
ACTIONS_DB = Path(os.environ.get("ACTIONS_DB", ROOT / "data" / "actions.duckdb"))

STATES = ["open", "acknowledged", "investigating", "resolved", "dismissed"]
TRANSITIONS: dict[str, set[str]] = {
    "open": {"acknowledged", "dismissed"},
    "acknowledged": {"investigating", "resolved", "dismissed"},
    "investigating": {"resolved", "dismissed"},
    "resolved": {"open"},      # reopen is allowed - closing evidence can be wrong
    "dismissed": {"open"},
}

KINDS = {
    "disparity": "Subgroup disparity escalation",
    "regression": "Confirmed release regression",
    "field_visit": "Site exceeds expected rejection",
    "hazard_review": "Hazard carrying complaint load",
    "ux_finding": "UX assessment finding (dogfooding: the portal tracks its own defects)",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(_retries: int = 10) -> duckdb.DuckDBPyConnection:
    """Open the action store - always in the same (writable) configuration.

    Two constraints collide here and the resolution is worth recording:
      * ACROSS processes, DuckDB allows many read-only connections OR one writer,
        so a multi-worker deploy can contend on the write lock.
      * WITHIN a process, DuckDB refuses to open the same file with a DIFFERENT
        configuration - mixing read_only and writable connections raises
        immediately. A first attempt at "reads open read-only" broke every
        request that followed a write in the same worker.
    So: every connection is short-lived and writable (one configuration,
    process-wide), and cross-process lock contention is absorbed by a bounded
    retry with backoff (~2.75s worst case) rather than surfacing as a 500.
    """
    import time as _time
    ACTIONS_DB.parent.mkdir(parents=True, exist_ok=True)
    last: Exception | None = None
    for attempt in range(_retries):
        try:
            con = duckdb.connect(str(ACTIONS_DB))
            break
        except duckdb.IOException as exc:      # lock held by a sibling worker
            last = exc
            _time.sleep(0.05 * (attempt + 1))
    else:
        raise last  # type: ignore[misc]
    con.execute("""
        CREATE TABLE IF NOT EXISTS actions (
            action_id   VARCHAR PRIMARY KEY,
            kind        VARCHAR NOT NULL,
            subject     VARCHAR NOT NULL,
            title       VARCHAR NOT NULL,
            evidence    VARCHAR NOT NULL,       -- JSON snapshot at creation
            grain_sha   VARCHAR NOT NULL,       -- warehouse state when raised
            state       VARCHAR NOT NULL,
            created_at  VARCHAR NOT NULL,
            updated_at  VARCHAR NOT NULL,
            UNIQUE (kind, subject)
        )""")
    con.execute("""
        CREATE TABLE IF NOT EXISTS action_events (
            event_id    VARCHAR PRIMARY KEY,
            action_id   VARCHAR NOT NULL,
            occurred_at VARCHAR NOT NULL,
            actor       VARCHAR NOT NULL,
            from_state  VARCHAR,
            to_state    VARCHAR NOT NULL,
            note        VARCHAR NOT NULL
        )""")
    con.execute("""
        CREATE TABLE IF NOT EXISTS signatures (
            signature_id  VARCHAR PRIMARY KEY,
            claim_type    VARCHAR NOT NULL,
            manifest_sha  VARCHAR NOT NULL,
            pack_path     VARCHAR NOT NULL,
            actor         VARCHAR NOT NULL,
            role          VARCHAR NOT NULL,
            note          VARCHAR NOT NULL,
            signed_at     VARCHAR NOT NULL
        )""")
    return con


# --------------------------------------------------------------------- findings → items
def _candidates(spine_con) -> list[dict]:
    out: list[dict] = []
    grain = evidence.spine_fingerprint(spine_con)["grain_sha256"][:16]

    d = metrics.subgroup_disparity(spine_con)
    for e in d["escalations"]:
        out.append({
            "kind": "disparity",
            "subject": f"{e['axis']}:{e['level']}",
            "title": f"Disparity: {e['level']} at {e['rate']:.1%} "
                     f"({e['disparity']:.2f}x the best arm)",
            "evidence": {"axis": e["axis"], "level": e["level"], "n": e["n"],
                         "rate": e["rate"], "disparity": e["disparity"],
                         "p_value": e["p_value"], "policy": d["policy"]},
            "grain": grain,
        })

    rows = spine_con.execute("""
        SELECT s.model_version, d.scanner_make, count(*) n,
               sum(s.crossed_threshold) hits, avg(s.crossed_threshold) rate
        FROM fct_case_spine s JOIN dim_site d USING (site_id)
        WHERE s.accepted = 1 GROUP BY 1,2 HAVING count(*) >= 40 ORDER BY 2,1
    """).fetchall()
    base: dict[str, tuple] = {}
    for mv, make, n, hits, rate in rows:
        if make not in base:
            base[make] = (n, int(hits), rate)
            continue
        bn, bh, br = base[make]
        lift = rate / br if br else 1.0
        p = metrics.two_proportion_p(int(hits), n, bh, bn)
        if lift >= 1.25 and p < 0.05:
            out.append({
                "kind": "regression",
                "subject": f"{mv}:{make}",
                "title": f"Regression: {mv} on {make} at {rate:.1%} "
                         f"({lift:.2f}x lift, p={p:.4f})",
                "evidence": {"model_version": mv, "scanner_make": make, "n": n,
                             "rate": rate, "lift": lift, "p_value": p},
                "grain": grain,
            })

    for sid, name, obs, exp, exc, rec in spine_con.execute("""
        SELECT site_id, site_name, observed_reject_rate, expected_reject_rate,
               excess_reject_rate, recoverable_cases
        FROM fct_site_conformance
        WHERE excess_reject_rate >= 0.05 AND recoverable_cases >= 3
        ORDER BY excess_reject_rate DESC LIMIT 5""").fetchall():
        out.append({
            "kind": "field_visit",
            "subject": f"site:{sid}",
            "title": f"Field visit: {name} rejects {obs:.1%} vs {exp:.1%} expected "
                     f"(~{rec:.0f} recoverable cases)",
            "evidence": {"site_id": sid, "site_name": name, "observed": obs,
                         "expected": exp, "excess": exc, "recoverable": rec},
            "grain": grain,
        })

    for hid, matches, complaints in spine_con.execute("""
        SELECT * FROM (
            SELECT h.hazard_id, count(DISTINCT m.case_id) AS matches,
                   (SELECT count(*) FROM fct_complaint c
                     WHERE c.hazard_id = h.hazard_id) AS complaints
            FROM raw_hazards h
            LEFT JOIN fct_hazard_match m ON m.hazard_id = h.hazard_id
            GROUP BY h.hazard_id
        ) WHERE complaints >= 10 ORDER BY hazard_id""").fetchall():
        out.append({
            "kind": "hazard_review",
            "subject": hid,
            "title": f"Hazard review: {hid} - {matches:,} realised conditions, "
                     f"{complaints} complaint(s)",
            "evidence": {"hazard_id": hid, "matches": matches,
                         "complaints": complaints},
            "grain": grain,
        })
    return out


def sync_findings(spine_con) -> dict:
    """Create work items for current findings. Idempotent on (kind, subject);
    never resurrects an item a human already moved or closed."""
    con = connect()
    try:
        existing = {(k, s) for k, s in
                    con.execute("SELECT kind, subject FROM actions").fetchall()}
        created = []
        for c in _candidates(spine_con):
            if (c["kind"], c["subject"]) in existing:
                continue
            aid = uuid.uuid4().hex[:12]
            now = _now()
            con.execute(
                "INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?)",
                [aid, c["kind"], c["subject"], c["title"],
                 json.dumps(c["evidence"], default=str), c["grain"],
                 "open", now, now])
            con.execute(
                "INSERT INTO action_events VALUES (?,?,?,?,?,?,?)",
                [uuid.uuid4().hex[:12], aid, now, "sync", None, "open",
                 f"raised from warehouse state {c['grain']}"])
            created.append({"action_id": aid, "kind": c["kind"],
                            "title": c["title"]})
        total = con.execute("SELECT count(*) FROM actions").fetchone()[0]
        return {"created": created, "total_items": total}
    finally:
        con.close()


def create_manual(kind: str, subject: str, title: str, evidence_data: dict,
                  actor: str) -> dict:
    """Manually raise a work item - used by the UX loop to dogfood: assessment
    findings are tracked through the portal's own lifecycle rather than a
    side-channel document. Same (kind, subject) idempotency as sync."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}")
    if not actor.strip():
        raise ValueError("a manual item names who raised it")
    con = connect()
    try:
        if con.execute("SELECT 1 FROM actions WHERE kind=? AND subject=?",
                       [kind, subject]).fetchone():
            return {"action_id": None, "existing": True, "subject": subject}
        aid = uuid.uuid4().hex[:12]
        now = _now()
        con.execute("INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?)",
                    [aid, kind, subject, title,
                     json.dumps(evidence_data, default=str), "manual",
                     "open", now, now])
        con.execute("INSERT INTO action_events VALUES (?,?,?,?,?,?,?)",
                    [uuid.uuid4().hex[:12], aid, now, actor.strip(),
                     None, "open", f"raised manually: {title[:80]}"])
        return {"action_id": aid, "existing": False, "subject": subject}
    finally:
        con.close()


# --------------------------------------------------------------------- lifecycle
def list_actions(state: str | None = None) -> list[dict]:
    con = connect()
    try:
        where, params = ("WHERE state = ?", [state]) if state else ("", [])
        cur = con.execute(f"""
            SELECT a.*, (SELECT count(*) FROM action_events e
                          WHERE e.action_id = a.action_id) AS events
            FROM actions a {where}
            ORDER BY CASE a.state WHEN 'open' THEN 0 WHEN 'acknowledged' THEN 1
                     WHEN 'investigating' THEN 2 ELSE 3 END, a.updated_at DESC""",
            params)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["evidence"] = json.loads(r["evidence"])
        return rows
    finally:
        con.close()


def transition(action_id: str, to_state: str, actor: str, note: str) -> dict:
    if to_state not in STATES:
        raise ValueError(f"unknown state {to_state!r}; states: {STATES}")
    if not actor.strip():
        raise ValueError("actor is required - an anonymous audit trail is not one")
    if not note.strip():
        raise ValueError("a transition without a note is not auditable")
    con = connect()
    try:
        row = con.execute("SELECT state FROM actions WHERE action_id = ?",
                          [action_id]).fetchone()
        if not row:
            raise KeyError(f"action {action_id} not found")
        frm = row[0]
        if to_state not in TRANSITIONS.get(frm, set()):
            raise ValueError(
                f"illegal transition {frm} -> {to_state}; "
                f"allowed from {frm}: {sorted(TRANSITIONS.get(frm, set()))}")
        now = _now()
        con.execute("UPDATE actions SET state = ?, updated_at = ? "
                    "WHERE action_id = ?", [to_state, now, action_id])
        con.execute("INSERT INTO action_events VALUES (?,?,?,?,?,?,?)",
                    [uuid.uuid4().hex[:12], action_id, now, actor.strip(),
                     frm, to_state, note.strip()])
        return {"action_id": action_id, "from": frm, "to": to_state, "at": now}
    finally:
        con.close()


def audit_trail(action_id: str) -> list[dict]:
    con = connect()
    try:
        cur = con.execute(
            "SELECT occurred_at, actor, from_state, to_state, note FROM action_events "
            "WHERE action_id = ? ORDER BY occurred_at", [action_id])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        con.close()


# --------------------------------------------------------------------- signatures
def sign_pack(pack: dict, actor: str, role: str, note: str) -> dict:
    """Freeze an evidence pack to disk and record who stood behind it.

    Verification precedes signature: a pack that fails its own hash check cannot
    be signed, full stop.
    """
    if not actor.strip() or not role.strip():
        raise ValueError("actor and role are required on a signature")
    ok, msg = evidence.verify(pack)
    if not ok:
        raise ValueError(f"refusing to sign an unverifiable pack: {msg}")
    path = evidence.persist(pack)
    con = connect()
    try:
        sid = uuid.uuid4().hex[:12]
        con.execute("INSERT INTO signatures VALUES (?,?,?,?,?,?,?,?)",
                    [sid, pack["content"]["claim_type"], pack["manifest_sha256"],
                     str(path), actor.strip(), role.strip(),
                     note.strip() or "-", _now()])
        return {"signature_id": sid, "manifest_sha256": pack["manifest_sha256"],
                "pack_path": str(path)}
    finally:
        con.close()


def list_signed() -> list[dict]:
    """Signed packs, re-verified on every read - a signature over a file that no
    longer verifies is surfaced as broken, not hidden."""
    con = connect()
    try:
        cur = con.execute("SELECT * FROM signatures ORDER BY signed_at DESC")
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        con.close()
    for r in rows:
        p = Path(r["pack_path"])
        if not p.exists():
            r["verification"] = "MISSING - pack file deleted after signing"
            continue
        ok, msg = evidence.verify(evidence.load(p))
        r["verification"] = "verified" if ok else f"BROKEN - {msg}"
    return rows
