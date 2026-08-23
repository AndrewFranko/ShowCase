# Validation Plan — Case Spine

**Document ID:** VAL-CSP-001
**Revision:** A
**Software:** Case Spine (analysis-pipeline telemetry and reporting)
**Classification:** Production and quality-system software. **Not device software.**

---

## 1. Purpose and scope

This plan establishes assurance for Case Spine under FDA's *Computer Software Assurance
for Production and Quality Management System Software* (final September 2025, reissued
3 February 2026 to align with the Quality Management System Regulation). That guidance
supplements the 2002 *General Principles of Software Validation* and supersedes its
Section 6.

CSA permits assurance effort proportionate to **process risk** rather than uniform scripted
validation of every function. This plan applies that principle: high-risk features receive
scripted testing, everything else receives unscripted testing backed by automated results.

### 1.1 Intended use

Case Spine aggregates records already held in existing systems onto a single conformed
grain (one row per case) and presents read-only projections of that data to four internal
audiences: Operations, Quality, Engineering and Field Service.

Its purpose is to make measurable a quantity that is not currently computed: the rate at
which analyst correction changes the diagnostic classification of a case, stratified by case
characteristics.

### 1.2 Explicitly out of scope

Case Spine **does not**:

- process, generate, alter or transmit any patient-facing analysis result;
- route, prioritise, triage or disposition any case;
- determine whether any case may bypass human review;
- write to any upstream system.

Any of the above would constitute a device software function and would move this software
out of the CSA framework entirely. §4.3 defines the controls that prevent this by
construction, and §6 defines the change trigger if it is ever proposed.

---

## 2. Regulatory basis

| Reference | Application |
|---|---|
| FDA CSA guidance (Feb 2026) | Primary framework. Risk-based assurance; unscripted testing acceptable for non-high-risk features; automated test results are acceptable objective evidence |
| 21 CFR 820 (QMSR, effective 2 Feb 2026) | Incorporates ISO 13485:2016 by reference |
| ISO 13485:2016 §4.1.6 | Validation of software used in the quality management system |
| ISO 13485:2016 §7.5.6 | Validation of processes for production and service provision |
| ISO 14971:2019 | Risk management. Case Spine **reports on** risk controls; it **is not** one |
| IEC 62304 | **Not applicable.** Case Spine is not device software and is not incorporated into a device |
| FD&C Act §524B | SBOM maintained; see §7 |

> **Note on the boundary.** 510(k) K250902 included "automation of internal quality controls
> functions" as a cleared device change. That establishes that automating the analyst QC step
> *is* a device change. Case Spine deliberately stops short of that line: it measures the step,
> it does not modify or bypass it. Evidence produced by Case Spine may inform a future device
> submission, but the tool itself remains production/QMS software.

---

## 3. Process risk assessment

Per CSA, risk is assessed by asking whether a software failure could compromise product
quality or patient safety, and whether the failure would be detected.

| # | Feature | Failure mode | Could it affect a patient result? | Process risk | Assurance |
|---|---|---|---|---|---|
| F1 | Metric definitions (`spine/metrics.py`, Cube model) | Metric computed incorrectly; a decision is informed by a wrong number | No — no path to a patient result. Could misinform an internal decision | **High** | Scripted + automated regression |
| F2 | Spine transform (`030_fct_case_spine.sql`) | Wrong join or grain; downstream everything is wrong | No | **High** | Scripted + automated data tests |
| F3 | Hazard signature evaluation (`040_…`) | Hazard match count wrong; residual-risk reporting misleads Quality | No, but feeds the risk management file | **High** | Scripted + automated |
| F4 | Regulatory boundary (read-only, no PHI, no routing) | Software acquires a capability that changes its classification | Yes, indirectly | **High** | Scripted; enforced in CI |
| F5 | Complaint traversal | Complaint resolved to the wrong case | No, but could misdirect an investigation | **Medium** | Automated contract tests |
| F6 | Site and release projections | Aggregate displayed incorrectly | No | **Low** | Unscripted / exploratory |
| F7 | Presentation layer (chart rendering, layout, theming) | Visual defect | No | **Low** | Unscripted / exploratory |
| F8 | Local fixture generator | Synthetic data unrealistic | No — development only, never in production | **Low** | Unscripted |

**Rationale for the overall determination.** No Case Spine failure can alter, delay or
suppress a patient-facing analysis. The service holds no write path to the case pipeline and
runs against a read-only warehouse credential. The realistic worst case is that an internal
decision is informed by an incorrect number — a business risk, mitigated by F1–F3 assurance
and by the reconciliation tests in §4.2.

---

## 4. Assurance activities

### 4.1 Scripted testing — high process risk (F1–F4)

Automated, executed on every commit, retained as evidence (§5).

| Test | Objective | Location |
|---|---|---|
| Metric layer agrees with direct SQL | One definition, one answer | `test_metric_layer_agrees_with_direct_sql` |
| Unknown measures and dimensions rejected | Callers cannot silently invent a metric | `test_unknown_measure_is_rejected` |
| Spine grain is one row per case | Grain integrity | `build.py --check`, Dagster `check_grain` |
| Every case resolves to site and model version | Referential integrity | `build.py --check` |
| Rejected cases carry no analyst facts | Rejected cases never reach an analyst | `build.py --check` |
| Accepted cases carry the counterfactual | `ffr_pre` present wherever it must be | `build.py --check`, `check_counterfactual_present` |
| Detector resolves at scan time | Scanner migration does not rewrite history | `build.py --check`, `check_detector_at_scan` |
| Frontier is monotone and reconciles | Ordering and cumulative share are coherent | `test_frontier_is_monotone`, `test_frontier_reconciles_to_the_whole` |
| Release signals require significance | Drift alerting does not fire on small-cell noise | `test_release_signal_requires_significance` |

### 4.2 Scripted testing — regulatory boundary (F4)

These are the tests to present at audit. Each encodes a classification-critical property as
an executable assertion, so the claim "this is not device software" is demonstrated on every
commit rather than asserted in prose.

| Test | Property |
|---|---|
| `test_api_exposes_no_write_routes` | Every route is GET |
| `test_database_connection_is_read_only` | The warehouse connection rejects DDL/DML |
| `test_no_routing_or_disposition_endpoint` | No route name implies case disposition |
| `test_spine_carries_no_identifying_columns` | No patient identifiers on any table |
| `test_no_analyst_identity_anywhere` | No analyst identity in any schema |
| `check_phi_boundary` (Dagster asset check) | Same, enforced at materialisation |

### 4.3 Unscripted testing — medium and low process risk (F5–F8)

Exploratory and scenario-based testing, recorded as a short session note per release:
tester, duration, areas covered, issues found. Per CSA this record is intentionally
concise; screenshots and step-by-step protocols are not required at this risk level.

Scenarios: filter and tolerance interaction; empty and single-row states; a stratum falling
below the suppression threshold; complaint with no matched hazard; site with no field visit;
narrow viewport; light and dark rendering.

---

## 5. Evidence and records

Per CSA, the record consists of: intended use, risk determination, objectives tested, testing
performed, results and issues, and a conclusion.

| Record | Location | Retention |
|---|---|---|
| This plan | `validation/csa-validation-plan.md`, version-controlled | Life of system + 2 yr |
| Automated results | CI artifact `validation-evidence-<sha>`, JUnit XML | 400 days |
| Data test results | `spine/build.py --check` console output, captured in CI | 400 days |
| Materialisation checks | Dagster asset check history | Per Dagster retention |
| Unscripted session notes | Release record | Life of system + 2 yr |
| Dependency inventory | CI artifact `sbom-<sha>` | 400 days |

**Traceability.** Each risk in §3 maps to named tests in §4; each test resides at a stated
path; each CI run pins a commit SHA. Requirement → risk → test → result → commit is therefore
navigable without a separate traceability matrix.

---

## 6. Change control

Routine changes (new projection, layout, performance) proceed under normal review with the
§4 suite as regression evidence.

**This plan must be re-executed and the classification re-assessed before any change that:**

1. introduces a non-GET route or any write path;
2. adds an endpoint that routes, prioritises, triages or dispositions a case;
3. introduces a column carrying patient identity, DICOM identifiers, pixel data or analyst
   identity;
4. causes any output to reach a clinician or influence a delivered analysis;
5. moves computation of a delivered FFR or plaque value into this service.

Items 1, 2 and 4 would very likely make Case Spine a device software function. That
determination belongs to Regulatory Affairs, not to engineering, and the guardrail tests
in §4.2 are designed to fail loudly rather than allow such a change to land quietly.

---

## 7. Software of unknown provenance and SBOM

Case Spine is not device software, so IEC 62304 SOUP obligations do not attach. §524B SBOM
obligations attach to cyber devices, not to this service. A dependency inventory is
nevertheless generated in CI (`pip-licenses`) because the same graph feeds both the
organisation's SOUP list and its SBOM, and maintaining one source is cheaper and less
error-prone than maintaining two by hand.

Runtime dependencies are deliberately few: DuckDB or Redshift connector, FastAPI, Uvicorn.

---

## 8. Conclusion

Case Spine is production and quality-system software with no path to a patient-facing result.
Assurance is scaled to process risk: scripted and automated for the metric layer, the spine
transform, hazard evaluation and the regulatory boundary; unscripted for presentation.

The software is fit for its intended use when the §4.1 and §4.2 suites pass on the commit
being released and a §4.3 session note is recorded.

| | Name | Role | Date |
|---|---|---|---|
| Prepared by | | Author | |
| Reviewed by | | Quality Engineering | |
| Approved by | | Quality Assurance | |

---

## 9. Amendment A — the action layer (change-control re-assessment)

Trigger: §6 item 1 (introduction of non-GET routes). Re-assessed as required.

**Added:** a finding-workflow layer — work items derived from findings (disparity
escalations, confirmed regressions, excess-rejection sites, hazard review), a
five-state lifecycle with mandatory actor and note on every transition, an
append-only event log, evidence-pack signatures (verify-before-sign, re-verify on
every read), and a generated HTML briefing.

**Classification outcome: unchanged — production and quality-system software.**
The write path persists to a separate store (`data/actions.duckdb`); the spine
connection remains read-only in source; no write route accepts a case identifier;
no output reaches a clinician or alters a delivered analysis. Managing findings is
the same software class as complaint handling (ISO 13485 §8.2.2 feedback and §8.5
improvement workflows) — QMS software squarely inside CSA scope. Dispositioning a
*case* remains the forbidden boundary, now enforced by
`test_write_routes_are_confined_to_the_action_layer` and
`test_action_store_is_not_the_spine`.

**Extension (same amendment):** the complaint-investigation process
(`/api/investigations/*`) — open → decide → close with the 30-day MDR clock,
mandatory decision rationale, late-decision flagging, and a sealed investigation
record artifact. This is 21 CFR 820.198 complaint-file workflow, the canonical QMS
software function; classification unchanged for the same reasons and under the
same store-separation controls.

**Process risk of the additions:** Medium. A wrong workflow state misleads an
internal user; no patient-facing path exists. Assurance: scripted lifecycle tests
(legal and illegal transitions, mandatory audit fields, idempotent sync,
verify-before-sign) run on every commit.

---

*Prepared as a reference artifact against a synthetic dataset. Risk determinations and the
classification rationale would require confirmation by Heartflow Regulatory Affairs against
the actual system before use.*
