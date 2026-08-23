"""
Dagster definitions - the production execution path.

Locally, `python -m spine.build` runs the same SQL files against DuckDB with no
infrastructure. In production Dagster runs them against Redshift on a schedule.
The SQL is identical; only the connection changes. Keeping the transform in .sql
files rather than in pandas is what makes that true.

Why Dagster specifically: it is already in Heartflow's stack (named in the IT
Director, Data Services and AI Enablement requisition alongside Redshift and Cube
Cloud). Introducing Airflow or Prefect here would mean a new vendor review for no
capability gain.

Asset checks are used rather than a separate test job because in a regulated
context you want the evidence that the data was validated attached to the
materialisation that produced it. When an auditor asks "how do you know the spine
was correct on 14 March", the answer should be a link, not an archaeology project.

Run:
    dagster dev -m orchestration.definitions
"""
# NOTE: no `from __future__ import annotations` here. Dagster inspects the
# runtime type of the `context` parameter annotation; postponed evaluation
# (PEP 563) turns it into a string and the @asset decorator rejects it.
import os
from pathlib import Path

from dagster import (
    AssetCheckResult,
    AssetExecutionContext,
    Definitions,
    MetadataValue,
    ScheduleDefinition,
    asset,
    asset_check,
    define_asset_job,
    in_process_executor,
)

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "spine" / "models"
RAW = ROOT / "data" / "raw"


# --------------------------------------------------------------------- resources
class Warehouse:
    """Thin wrapper so the same asset body runs against DuckDB or Redshift.

    Production binds this to Redshift via redshift_connector using credentials from
    Secrets Manager; the local default is the DuckDB file the rest of the repo uses.
    """

    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or os.environ.get("SPINE_DSN", "duckdb:///data/spine.duckdb")

    def execute(self, sql: str):
        if self.dsn.startswith("duckdb://"):
            import duckdb
            # Relative paths resolve against the repo root, not the process CWD -
            # Dagster's working directory is not the repo root in general.
            path = Path(self.dsn.replace("duckdb:///", ""))
            if not path.is_absolute():
                path = ROOT / path
            path.parent.mkdir(parents=True, exist_ok=True)
            con = duckdb.connect(str(path))
            try:
                return con.execute(sql).fetchall()
            finally:
                con.close()
        # production branch
        import redshift_connector  # noqa: F401  (installed in the prod image only)
        raise NotImplementedError(
            "bind Warehouse to redshift_connector with Secrets Manager credentials")

    def scalar(self, sql: str):
        rows = self.execute(sql)
        return rows[0][0] if rows else None


WAREHOUSE = Warehouse()


def _run_model(context: AssetExecutionContext, filename: str, table: str) -> None:
    sql = (MODELS / filename).read_text(encoding="utf-8")
    WAREHOUSE.execute(sql)
    n = WAREHOUSE.scalar(f"SELECT count(*) FROM {table}")
    context.add_output_metadata({
        "rows": MetadataValue.int(n or 0),
        "model": MetadataValue.path(str(MODELS / filename)),
    })


def _land_raw(context: AssetExecutionContext, name: str) -> None:
    """Land one source extract as a raw_* staging table.

    Locally this lands the JSON fixture (same contract as spine.build.load_raw);
    in production the extract asset is the real connector described in
    spine/sources.py writing to the Redshift staging schema. The table name and
    columns are identical either way - that is the contract downstream SQL
    depends on.
    """
    path = (RAW / f"{name}.json")
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found - run `python -m spine.generate` first")
    WAREHOUSE.execute(
        f"CREATE OR REPLACE TABLE raw_{name} AS "
        f"SELECT * FROM read_json_auto('{path.as_posix()}', "
        f"maximum_object_size=200000000)")
    n = WAREHOUSE.scalar(f"SELECT count(*) FROM raw_{name}")
    context.add_output_metadata({"rows": MetadataValue.int(n or 0)})


# --------------------------------------------------------------------- extracts
@asset(group_name="extract", description="Case management (Aurora read replica)")
def raw_cases(context: AssetExecutionContext) -> None:
    _land_raw(context, "cases")


@asset(group_name="extract", description="Analyst corrections (S3 label store)")
def raw_analyst_events(context: AssetExecutionContext) -> None:
    """The pre-correction geometry lives here.

    Note that `ffr_pre` is NOT an upstream column - nothing ever needed it, because
    the pipeline solves CFD once on the final model since that is the deliverable.
    Producing it is a batch re-solve over this store, and it is the single
    highest-value computation in the project.
    """
    _land_raw(context, "analyst_events")


@asset(group_name="extract", description="Complaints (Smarteeva REST)")
def raw_complaints(context: AssetExecutionContext) -> None:
    _land_raw(context, "complaints")


@asset(group_name="extract", description="Risk file with hazard signatures (Ketryx)")
def raw_hazards(context: AssetExecutionContext) -> None:
    _land_raw(context, "hazards")


@asset(group_name="extract", description="Site and scanner registry (DICOM headers)")
def raw_sites(context: AssetExecutionContext) -> None:
    _land_raw(context, "sites")


# --------------------------------------------------------------------- models
@asset(group_name="dimensions", deps=[raw_sites])
def dim_site(context: AssetExecutionContext) -> None:
    _run_model(context, "010_dim_site.sql", "dim_site")


@asset(group_name="dimensions")
def dim_model_version(context: AssetExecutionContext) -> None:
    _run_model(context, "020_dim_model_version.sql", "dim_model_version")


@asset(group_name="spine", deps=[raw_cases, raw_analyst_events, dim_site])
def fct_case_spine(context: AssetExecutionContext) -> None:
    """The spine. One immutable row per case."""
    _run_model(context, "030_fct_case_spine.sql", "fct_case_spine")


@asset(group_name="spine", deps=[fct_case_spine, raw_hazards])
def fct_hazard_match(context: AssetExecutionContext) -> None:
    _run_model(context, "040_fct_hazard_match.sql", "fct_hazard_match")


@asset(group_name="spine", deps=[fct_case_spine, raw_complaints, fct_hazard_match])
def fct_complaint(context: AssetExecutionContext) -> None:
    _run_model(context, "050_fct_complaint.sql", "fct_complaint")


@asset(group_name="spine", deps=[fct_case_spine, dim_site])
def fct_site_conformance(context: AssetExecutionContext) -> None:
    """Expected-vs-observed rejection per site, stratified by case mix.

    Run by spine.build (it executes every file in spine/models/); carried here
    too so the Dagster graph builds the same warehouse as the local runner.
    """
    _run_model(context, "060_fct_site_conformance.sql", "fct_site_conformance")


# --------------------------------------------------------------------- checks
@asset_check(asset=fct_case_spine, description="Grain is one row per case")
def check_grain() -> AssetCheckResult:
    dupes = WAREHOUSE.scalar(
        "SELECT count(*) - count(DISTINCT case_id) FROM fct_case_spine")
    return AssetCheckResult(passed=dupes == 0, metadata={"duplicate_case_ids": dupes})


@asset_check(asset=fct_case_spine, description="No identifying columns on the spine")
def check_phi_boundary() -> AssetCheckResult:
    banned = {"patient_id", "mrn", "accession", "accession_number", "study_uid",
              "series_uid", "sop_uid", "patient_name", "dob",
              "analyst_id", "analyst_name"}
    cols = {r[0].lower() for r in WAREHOUSE.execute("DESCRIBE fct_case_spine")}
    leaked = sorted(cols & banned)
    return AssetCheckResult(passed=not leaked, metadata={"leaked": leaked or "none"})


@asset_check(asset=fct_case_spine, description="Detector resolves at scan time")
def check_detector_at_scan() -> AssetCheckResult:
    n = WAREHOUSE.scalar(
        "SELECT count(DISTINCT detector_at_scan) FROM fct_case_spine s "
        "JOIN dim_site d USING (site_id) WHERE d.detector_switch_day IS NOT NULL")
    return AssetCheckResult(passed=n == 2, metadata={"distinct_detectors_at_migrated_sites": n})


@asset_check(asset=fct_case_spine, description="Accepted cases carry the counterfactual")
def check_counterfactual_present() -> AssetCheckResult:
    n = WAREHOUSE.scalar(
        "SELECT count(*) FROM fct_case_spine WHERE accepted = 1 AND ffr_pre IS NULL")
    return AssetCheckResult(passed=n == 0, metadata={"accepted_without_ffr_pre": n})


@asset_check(asset=fct_complaint, description="No complaint predates its case")
def check_complaint_lag() -> AssetCheckResult:
    n = WAREHOUSE.scalar("SELECT count(*) FROM fct_complaint WHERE reporting_lag_days < 0")
    return AssetCheckResult(passed=n == 0, metadata={"negative_lag_rows": n})


# --------------------------------------------------------------------- jobs
build_spine = define_asset_job("build_spine", selection="*")

defs = Definitions(
    assets=[raw_cases, raw_analyst_events, raw_complaints, raw_hazards, raw_sites,
            dim_site, dim_model_version,
            fct_case_spine, fct_hazard_match, fct_complaint, fct_site_conformance],
    asset_checks=[check_grain, check_phi_boundary, check_detector_at_scan,
                  check_counterfactual_present, check_complaint_lag],
    jobs=[build_spine],
    schedules=[ScheduleDefinition(job=build_spine, cron_schedule="0 5 * * *")],
    # DuckDB is a single-writer embedded database: assets must not run in
    # parallel OS processes against the same file. In-process serial execution
    # is correct locally; the Redshift deployment can drop this override.
    executor=in_process_executor,
)
