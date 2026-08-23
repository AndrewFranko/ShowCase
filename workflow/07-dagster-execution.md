# Iteration 07 — The Dagster path, executed for real

## The claim being tested

`orchestration/definitions.py` had been written but never executed — the weakest claim in
the repo. It asserted that the same SQL files `spine/build.py` runs locally could be
materialised as Dagster assets with checks attached. Written against an assumed API, run
against nothing. This iteration installed Dagster in an isolated venv and made the module
real.

## Environment

- **Dagster 1.13.19**, duckdb 1.5.5, Python 3.11.1, in a separate `.venv-dagster/`
  (deliberately not the app venv — Dagster's dependency tree is heavy and the app's pins
  stay untouched).
- The machine's C: drive was at 0 bytes free during the run; pip temp, `TMP`/`TEMP` and
  `DAGSTER_HOME` had to be pointed at the D: drive for anything to execute. Not a code
  problem, but it is the honest reason some commands below carry env overrides.

## Drift found and fixed

The module loaded none of its assets as written. Four real defects, one Windows footgun:

1. **`from __future__ import annotations` breaks the `@asset` decorator.** Dagster 1.13
   inspects the runtime type of the `context` parameter annotation; PEP 563 turns it into
   the *string* `"AssetExecutionContext"` and the decorator rejects it with
   `DagsterInvalidDefinitionError`. Removed the future import (Python 3.11 handles
   `str | None` natively). This was the only true written-from-memory-vs-installed API
   drift — everything else imported (`asset_check`, `AssetCheckResult(passed=...)`,
   `define_asset_job`, `Definitions`) matched the installed 1.13 API exactly.
2. **The extract assets were decorative.** `raw_cases` et al. called
   `spine.sources.*()` and recorded a row count — but never landed a `raw_*` table in the
   warehouse. Downstream SQL could only ever have succeeded against tables left behind by
   a previous `spine.build` run, which is precisely the kind of accidental green this repo
   keeps catching. They now land the fixture as `raw_*` staging tables via
   `read_json_auto`, the same contract as `spine.build.load_raw`.
3. **Relative DSN resolved against the process CWD.** `duckdb:///data/spine.duckdb` is
   relative; Dagster's working directory is not the repo root in general. Relative paths
   now resolve against the repo root (`Path(__file__)` two levels up).
4. **`060_fct_site_conformance.sql` was missing from the graph.** `spine/build.py` runs
   every file in `spine/models/`; the Dagster module wrapped only five of six. Added
   `fct_site_conformance` so both runners build the same warehouse.
5. **Serial execution.** DuckDB is single-writer; Dagster's default multiprocess executor
   would race worker processes on one file. `Definitions(executor=in_process_executor)`
   forces serial in-process execution locally. (The Redshift deployment can drop this.)

One near-miss worth recording: the first run failed with a Windows file lock —
`Cannot open file "data/spine.duckdb": being used by another process` — because the live
deploy on port 8091 had a read-only connection open mid-request. The app opens
per-request connections, so the lock is transient; the retry succeeded. A scheduled 05:00
run colliding with request traffic is a real (if small) local hazard; in production the
warehouse is Redshift and the problem does not exist.

## The command that works

```
.venv-dagster/Scripts/dagster job execute -m orchestration.definitions -j build_spine
```

Note on the documented alternative: `dagster asset materialize --select "*"` **cannot be
made to work from a Windows shell** — Click 8 glob-expands `*` on Windows after the shell
has already honoured the quotes, so Dagster receives the repo's directory listing as
arguments. The job route is the reliable one and exercises the schedule's target besides.

## Results

Run `e6442cf1` — `RUN_SUCCESS`. All 11 assets materialised, all 5 asset checks passed,
attached to the materialisation that produced them (the point of using asset checks):

| check | asset | result |
|---|---|---|
| check_grain | fct_case_spine | passed |
| check_phi_boundary | fct_case_spine | passed |
| check_detector_at_scan | fct_case_spine | passed |
| check_counterfactual_present | fct_case_spine | passed |
| check_complaint_lag | fct_complaint | passed |

Row counts in the Dagster-built `data/spine.duckdb`, verified from the app venv against
what `spine/build.py` produces from the same fixture: `fct_case_spine` 12000,
`fct_hazard_match` 2136, `fct_complaint` 81, `fct_site_conformance` 130, `dim_site` 140,
`dim_model_version` 3, and all five `raw_*` tables identical. Exact parity. The fast
suite (77 tests) still passes and the deploy on 8091 kept serving throughout.

## Still unverified — stated plainly

- **The Redshift branch of `Warehouse` remains a stub.** It raises `NotImplementedError`
  by design; no Redshift, Secrets Manager, or `redshift_connector` code has executed.
  The claim "the same SQL runs on Redshift" is still an argument, not evidence.
- **The schedule has not fired.** `ScheduleDefinition` loads and targets the job that now
  demonstrably runs, but no daemon has evaluated the cron. Headless execution is proven;
  scheduled execution is not.
- **`dagster dev` (the webserver) was not run** — `dagster-webserver` was skipped to keep
  the isolated venv minimal. The module docstring's `dagster dev -m orchestration.definitions`
  is expected to work but has not been observed working.
