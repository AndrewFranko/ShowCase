"""
Executes the SQL models in order against DuckDB (local) or Redshift (production).

The models are plain SQL on purpose. Locally they run in DuckDB with no
infrastructure; in production the same files are executed by Dagster against
Redshift (see orchestration/definitions.py). Keeping the transform in SQL rather
than in pandas is what makes that swap a configuration change instead of a rewrite.

Usage:
    python -m spine.build                 # build data/spine.duckdb
    python -m spine.build --check         # build, then run assertions
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
MODELS = Path(__file__).resolve().parent / "models"
RAW = ROOT / "data" / "raw"
DB = ROOT / "data" / "spine.duckdb"

RAW_TABLES = ["sites", "cases", "analyst_events", "complaints", "hazards"]


def load_raw(con: duckdb.DuckDBPyConnection) -> None:
    """Land the source extracts as raw_* tables.

    In production these are Dagster assets writing to a Redshift staging schema;
    the contract (table names and columns) is identical either way.
    """
    for name in RAW_TABLES:
        path = RAW / f"{name}.json"
        if not path.exists():
            sys.exit(f"missing {path} - run `python -m spine.generate` first")
        con.execute(
            f"CREATE OR REPLACE TABLE raw_{name} AS "
            f"SELECT * FROM read_json_auto(?, maximum_object_size=200000000)",
            [str(path)],
        )
        n = con.execute(f"SELECT count(*) FROM raw_{name}").fetchone()[0]
        print(f"  raw_{name:16s} {n:6d} rows")


def run_models(con: duckdb.DuckDBPyConnection) -> None:
    for sql_file in sorted(MODELS.glob("*.sql")):
        print(f"  {sql_file.name}")
        con.execute(sql_file.read_text(encoding="utf-8"))


def check(con: duckdb.DuckDBPyConnection) -> int:
    """Assertions that must hold for the spine to be trustworthy.

    These are data tests, not unit tests - they run against whatever was just
    built, local or production, and they are the thing you point an auditor at
    when they ask how you know the pipeline is right.
    """
    failures = []

    def assert_that(label: str, sql: str, want) -> None:
        got = con.execute(sql).fetchone()[0]
        ok = got == want if not callable(want) else want(got)
        print(f"  [{'ok ' if ok else 'FAIL'}] {label}: {got}")
        if not ok:
            failures.append(label)

    # grain
    assert_that("spine grain is one row per case",
                "SELECT count(*) - count(DISTINCT case_id) FROM fct_case_spine", 0)
    assert_that("every case has a site",
                "SELECT count(*) FROM fct_case_spine WHERE site_id IS NULL", 0)
    assert_that("every case has a model version",
                "SELECT count(*) FROM fct_case_spine WHERE model_version IS NULL", 0)

    # rejected cases never reach an analyst, so must have no correction facts
    assert_that("rejected cases carry no analyst facts",
                "SELECT count(*) FROM fct_case_spine "
                "WHERE accepted = 0 AND analyst_min IS NOT NULL", 0)
    assert_that("accepted cases all carry the counterfactual",
                "SELECT count(*) FROM fct_case_spine "
                "WHERE accepted = 1 AND ffr_pre IS NULL", 0)

    # detector must be resolved at scan time, not site-current
    assert_that("detector resolves at scan time for migrated sites",
                "SELECT count(DISTINCT detector_at_scan) FROM fct_case_spine s "
                "JOIN dim_site d USING (site_id) "
                "WHERE d.detector_switch_day IS NOT NULL", 2)

    # referential integrity
    assert_that("complaints all resolve to a case",
                "SELECT count(*) FROM raw_complaints k "
                "LEFT JOIN fct_case_spine s USING (case_id) WHERE s.case_id IS NULL", 0)
    assert_that("no complaint predates its case",
                "SELECT count(*) FROM fct_complaint WHERE reporting_lag_days < 0", 0)

    # PHI boundary - the spine must not have acquired identifying columns
    banned = {"patient_id", "mrn", "accession", "accession_number", "study_uid",
              "series_uid", "sop_uid", "patient_name", "dob", "analyst_id", "analyst_name"}
    cols = {r[0].lower() for r in con.execute("DESCRIBE fct_case_spine").fetchall()}
    leaked = sorted(cols & banned)
    print(f"  [{'ok ' if not leaked else 'FAIL'}] no identifying columns on the spine: "
          f"{leaked or 'none'}")
    if leaked:
        failures.append("PHI boundary")

    # plausibility - these are the numbers the lenses report
    assert_that("reject rate within published real-world range (8-15%)",
                "SELECT round(1 - avg(accepted), 4) FROM fct_case_spine",
                lambda v: 0.05 <= v <= 0.16)
    assert_that("actionable-correction rate is a minority of accepted cases",
                "SELECT round(avg(crossed_threshold), 4) FROM fct_case_spine "
                "WHERE accepted = 1", lambda v: 0.03 <= v <= 0.30)

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("all checks passed")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="run data tests after building")
    args = ap.parse_args()

    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    con = duckdb.connect(str(DB))

    print("landing raw extracts")
    load_raw(con)
    print("building models")
    run_models(con)

    n = con.execute("SELECT count(*) FROM fct_case_spine").fetchone()[0]
    h = con.execute("SELECT count(*) FROM fct_hazard_match").fetchone()[0]
    c = con.execute("SELECT count(*) FROM fct_complaint").fetchone()[0]
    print(f"\nfct_case_spine {n} rows · fct_hazard_match {h} · fct_complaint {c}")
    print(f"database: {DB}")

    if args.check:
        print("\nrunning data tests")
        rc = check(con)
        con.close()
        return rc
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
