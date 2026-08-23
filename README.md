# Case Spine

One case ledger, six lenses.

A reference build of unified telemetry for an AI analysis pipeline of the kind Heartflow
operates: coronary CT in, machine segmentation, a human analyst correcting a 3D vessel
model, computational fluid dynamics, a diagnostic result out.

The whole thing exists to compute one number that currently is not computed anywhere:

> **actionable-correction rate** — the share of accepted cases where analyst correction
> moved an FFR value across the 0.80 decision threshold. That is, where the human *changed
> the answer* rather than confirming it.

Minutes-per-case is a cost metric. Actionable-correction rate is a safety metric. Removing a
human from a diagnostic loop requires the second one, stratified.

**All data here is synthetic.** See [Provenance](#provenance).

---

## Run it

```bash
make venv     # python -m venv .venv && pip install -e ".[dev]"
make all      # seed fixture, build the spine, run every check and the fast suite
make serve    # http://127.0.0.1:8000
make e2e      # browser suite (downloads Chromium on first run)
make mcp      # MCP server on stdio
```

No database server, no cloud account. The pipeline runs against DuckDB from a local
fixture; `/docs` gives you the OpenAPI schema. `make deploy` starts a production-shaped
server (multi-worker, no reload, health-gated, every client route smoke-tested) and refuses
to adopt a port already served by a process it did not start.

**Three test suites, run as separate processes.**

| Suite | Runtime | Covers |
|---|---|---|
| `pytest` | ~7 s | 11 data checks + 77 tests: metric semantics, API contract, regulatory guardrails, MCP governance |
| `pytest tests/e2e/test_lenses.py` | ~30 s | Playwright against a self-booted server |
| `make e2e-deployed` | ~12 s | Playwright against the running deploy — canvases sampled for paint, not presence |

They run as separate processes on purpose. Playwright's sync API drives a greenlet-backed
event loop that cannot coexist in-process with the anyio async tests the MCP suite needs —
and splitting them is what you want operationally anyway, so a Chromium download never gates
the fast suite.

---

## The idea

Every question worth asking about this pipeline spans systems that do not talk to each other:

| Question | Needs | Why it cannot be asked today |
|---|---|---|
| Did this release degrade accuracy on one vendor's scanners? | release × scanner × ΔFFR | Release data and clinical outcome live apart |
| Is this complaint an anecdote or a trend? | complaint × stratum × release | Complaints are investigated one at a time |
| Did that field visit reduce rejections? | site × visit × rejection over time | Field service has no outcome feedback |
| Did this site's plaque numbers move because it swapped scanners? | detector generation × result × time | Detector generation is not carried per case |
| How many live cases match hazard H-014? | risk file × case facts | The risk file is prose in a separate system |

The fix is not a data warehouse. It is a **narrow conformed spine** — six columns —
with everything else left where it lives:

```
case_id · site_id · scanner_key · model_version · case_day · stratum
```

Two derivations carry the design:

- **`detector_at_scan`** resolves against the site's migration date, not its current
  scanner. Photon-counting CT measures roughly a third less total plaque volume than
  energy-integrating, and EID-derived thresholds do not transfer — so without this, a
  hardware swap silently rewrites history.
- **`ffr_pre`** is FFR recomputed on the *pre-correction* geometry. No upstream system
  stores it, because nothing ever needed it: the pipeline solves CFD once, on the final
  model, since that is the deliverable. Producing it is a batch re-solve over corrections
  already persisted as training labels. It is the highest-value computation in the project
  and it requires no new instrumentation.

---

## Layout

```
spine/
  generate.py        synthetic fixture in source-system shape (five un-joined tables)
  sources.py         extractors — swap the body for a real connector, contract unchanged
  models/*.sql       the transform: dimensions, spine, hazard matches, complaints
  build.py           runs the models; `--check` runs data tests
  metrics.py         canonical metric definitions + the significance test
app/
  main.py            read-only FastAPI; six lenses, no write path
  static/index.html  client, consumes the API
orchestration/
  definitions.py     Dagster assets + asset checks (production path)
semantic/
  model/cubes/       Cube schema — one metric definition served to every consumer
infra/               Terraform: enterprise module (EKS+Redshift — the Heartflow
                     target-architecture collateral, ~$73/mo, validate-only) and
                     aws-free-tier/ (t3.micro + compose + Caddy — the one you apply)
validation/          CSA validation plan
tests/               contract · semantic · guardrail · statistics
```

---

## Deployment

Assembled from components already in Heartflow's stack, as named in their own requisitions:

```
Aurora ─┐
S3      ├─→ Dagster ──→ Redshift ──→ Cube Cloud ──┬─→ Portal (Django/TS on EKS)
Smarteeva│                                        ├─→ Power BI
Ketryx  ─┘                                        └─→ Tableau
```

Terraform · GitHub Actions → Harness · Playwright · k6 — all inside the existing VPC.

**No new vendor, no new subprocessor, no new data egress.** Existing HITRUST, ISO 27001 and
SOC 2 Type 2 scope is unchanged. That is the difference between a security review measured in
weeks and one measured in quarters.

Cube Cloud is the load-bearing choice. `actionable_correction_rate` is defined once, in
[`semantic/model/cubes/case_spine.yml`](semantic/model/cubes/case_spine.yml), and served
identically to the portal, Power BI and Tableau. Without it, three teams compute it three
ways, disagree by two points, and the meeting becomes about whose number is right.

Terraform deliberately schedules onto **existing node groups** and relies on VPC CNI prefix
delegation rather than requesting new subnets — Heartflow's public GitHub org carries a fork
of `aws-subnet-ip-address-utilization-monitor`, which suggests address exhaustion is a live
constraint on that cluster.

---

## Deploying to AWS (free tier)

The full plan, free-tier arithmetic and leftover register live in
[`deploy/aws/PLAN.md`](deploy/aws/PLAN.md). Short form: `release.yml` publishes
the image to GHCR (data checks gate the build); `infra/aws-free-tier/` applies a
t3.micro + docker compose + Caddy (TLS + basic-auth, SSM-only administration, no
SSH port, nightly `/state` → S3). Verify with the same suites as everywhere:

```bash
DEPLOY_BASE=https://<host> DEPLOY_AUTH=spine:<password> pytest tests/e2e/test_deployed.py -q
```

The MCP server stays local-first by design (its audience is a local agent host);
it is deliberately not exposed on the public instance.

## Regulatory posture

Production and quality-system software under FDA **Computer Software Assurance** (final
September 2025, reissued 3 February 2026 to align with QMSR). **Not device software.**

It *observes*. It never routes, prioritises or dispositions a case. The moment it decides
which cases skip human review, it crosses into device software under a different regime —
510(k) K250902 already established that automating internal QC is a cleared device change.

That boundary is enforced in CI rather than asserted in a document:

| Test | Property |
|---|---|
| `test_api_exposes_no_write_routes` | Every route is GET |
| `test_database_connection_is_read_only` | The warehouse connection rejects DDL |
| `test_no_routing_or_disposition_endpoint` | No route implies case disposition |
| `test_spine_carries_no_identifying_columns` | No patient identifiers anywhere |
| `test_no_analyst_identity_anywhere` | No analyst identity in any schema |

That last one is a design constraint, not an oversight. Aggregation is **by case stratum**,
so the system is structurally incapable of individual performance monitoring. Analysts work
under quotas and rate job security poorly; a tool that reads as surveillance gets buried by
Operations regardless of its merits.

Full reasoning: [`validation/csa-validation-plan.md`](validation/csa-validation-plan.md).

---

## Browser tests

Playwright, in [`tests/e2e/`](tests/e2e/). They assert on **invariants, not rendered
values** — a test that hardcodes "21% of accepted volume" breaks the moment the fixture seed
changes and teaches the team to update the expectation rather than investigate, which is how
a suite stops being a safety net. Every assertion would still hold against real data.

The deployed suite (`tests/e2e/test_deployed.py`) drives the client the way a person uses
it: it opens the **Findings** narrative — 86% hero number, five charted findings each ending
in a stated conclusion — then walks all seven lenses, samples every canvas's alpha channel to
prove it actually painted (a blank canvas passes any DOM assertion), and verifies the
evidence-pack hash is identical across two independent browser-issued fetches.

The three worth reading:

- **`test_disposition_matches_the_stated_tolerance`** — every row labelled *Automate* must
  actually sit at or below the tolerance. A label that disagrees with the number beside it is
  the most dangerous defect this UI could ship, because the label is what a reader acts on.
- **`test_release_signal_never_contradicts_its_p_value`** — `regression` and `improved`
  require p < 0.05; a material effect without support must read `unconfirmed`.
- **`test_api_failure_surfaces_instead_of_rendering_empty`** — with the API blocked the page
  must say so. A data UI that fails silently renders empty tables that read as *no findings*,
  which in this domain would mean *no hazards matched*.

An autouse fixture promotes any browser console error to a test failure, because a
data-driven UI degrades silently by default. Tests that provoke failure on purpose opt out
with `@pytest.mark.allow_console_errors`, so the exemption is explicit and greppable.

## MCP server

[`mcp_server/server.py`](mcp_server/server.py) exposes the spine as a governed tool surface
for AI agents — seven tools, all annotated `readOnlyHint`.

```bash
claude mcp add case-spine -- python -m mcp_server.server
```

**There is no `run_sql` tool, and there will not be one.** That is the whole design. Every
tool is a *named metric query* composed from `spine/metrics.py`, so an agent can select and
slice but cannot invent a metric, join arbitrarily, or reach a column the semantic layer does
not expose. A free-text SQL tool over a clinical warehouse is a governance hole no amount of
prompt engineering closes: it makes output unauditable, lets the model compute one metric
three ways, and hands it a route around the PHI boundary.

What follows from that:

- **Rejection over guessing.** An unknown measure returns an error naming it. The agent is
  told it asked for something that does not exist rather than receiving a near-miss.
- **Provenance on every result** — filters applied, row count, and the definition source —
  so an agent cites rather than asserts.
- **Semantics in the tool descriptions.** A model that does not know 0.80 is the ischemia
  threshold, or that actionable-correction rate is a *safety* measure while minutes-per-case
  is a *cost* measure, will pick the wrong tool confidently. The description field is where
  that knowledge has to live.
- **Audited.** Every call is logged to `data/mcp-audit.log` with arguments and duration. In a
  regulated setting, "what did the agent look at" has to be answerable months later.
- **Capped at the protocol boundary.** An over-large `limit` is refused by schema validation
  before the tool body runs, so the agent is told it asked for too much rather than handed a
  truncated answer it may treat as complete.

Nineteen tests cover it, including `test_there_is_no_sql_tool`,
`test_no_tool_leaks_identifying_fields`, and `test_missing_record_errors_rather_than_inventing`.
Most run against an in-memory transport; one spawns the real subprocess over stdio, because
in-memory does not prove the module is launchable the way an agent host launches it.

## Three things to look at

**`/api/engineering/releases`** — the planted regression. Model v4.1.0 raised
actionable-correction rate on Canon reconstructions from 11.2% to **19.3%** (lift 1.71,
p = 0.005) while other manufacturers held flat; v4.1.3 recovered it. Median analyst minutes
barely moved, so no throughput dashboard would have caught it.

Note the `signal` field requires **both** a material lift and p < 0.05. An earlier version
flagged on ratio alone and produced a false positive on a small Siemens cell — a drift
monitor that cries wolf gets muted, which is the same as not having one.

**`/api/quality/complaints/{id}/trace`** — complaint → case → site → hazard → stratum →
trend by release, in one request. Today that traversal spans Smarteeva, the case store, the
label store and Ketryx.

**`/api/field/detector-transitions`** — two sites migrate to photon-counting mid-window and
their median plaque volume drops ~33%. Nothing fails: no rejection, no complaint, no alert.
The numbers simply move because the detector changed.

---

## Provenance

Every figure is synthetic. The *dependency structure* follows public disclosure and the CCTA
literature so the analysis demonstrates something real:

- FFR decision threshold 0.80; grey zone 0.75–0.80
- median analyst processing 26 min (S-1, Q4 2024); median turnaround 1.6 h
- real-world rejection 8–15%; motion artifact ~78% of rejections (ADVANCE registry)
- automation failure predicted by stents and Agatston > 967
- photon-counting CT measures ~⅓ lower total plaque volume (*Radiology*, 2025)
- SCCT/SCAI 2026 consensus requires nitroglycerin and heart-rate control

Three signals are planted so the lenses have something true to find; they are documented at
the bottom of [`spine/generate.py`](spine/generate.py).

This is a demonstration of an architecture and an analysis method. It is not a claim about
Heartflow's actual numbers, and it uses no Heartflow data.
