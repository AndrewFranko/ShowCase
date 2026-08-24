"""Postgres connection for CaseOps.

DSN via CASEOPS_DSN; default matches caseops/docker-compose.yml. This system is
read-WRITE by design - it is the upstream operational system of record, unlike
the spine, which reads from it and must stay read-only.
"""
from __future__ import annotations

import os

import psycopg
from psycopg.rows import dict_row

DSN = os.environ.get(
    "CASEOPS_DSN", "postgresql://caseops:caseops@127.0.0.1:5434/caseops")


def connect() -> psycopg.Connection:
    return psycopg.connect(DSN, row_factory=dict_row)


ACTIVE_STATUSES = ("assigned", "in_review", "blocked")


def fan_out(cur, source: str, source_id: int, hospital_id: int,
            device_id: int | None, message: str) -> int:
    """The warning mechanism: when something changes at a hospital, every analyst
    holding an ACTIVE ticket there gets one notification naming exactly the
    tickets affected. Device-scoped events warn only analysts on that device;
    site-wide events warn everyone active at the hospital. Analysts with no
    active ticket there are deliberately not notified - a warning system that
    broadcasts trains people to ignore it."""
    cur.execute(
        """SELECT analyst_id, array_agg(ticket_id ORDER BY ticket_id) AS tids
           FROM ticket
           WHERE hospital_id = %s AND status = ANY(%s) AND analyst_id IS NOT NULL
             AND (%s::int IS NULL OR device_id = %s)
           GROUP BY analyst_id""",
        (hospital_id, list(ACTIVE_STATUSES), device_id, device_id))
    n = 0
    for row in cur.fetchall():
        cur.execute(
            """INSERT INTO notification (analyst_id, source, source_id, ticket_ids, message)
               VALUES (%s, %s, %s, %s, %s)""",
            (row["analyst_id"], source, source_id, row["tids"], message))
        n += 1
    return n
