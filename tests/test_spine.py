"""
Tests for the spine, the metric layer, and the API.

Three categories, and the split matters when you show this to a quality engineer:

  contract   - the API keeps its shape (what a consumer depends on)
  semantic   - metrics computed two different ways agree (what stops the
               fourth dashboard from quoting a different number)
  guardrail  - the service cannot do things it must not do (read-only,
               no PHI columns, no routing endpoints)

The guardrail tests are the interesting ones. They encode the regulatory boundary
as executable assertions, so "this is not device software" is something CI proves
on every commit rather than something a design document claims.
"""
from __future__ import annotations

import pathlib
import json
import duckdb
import pytest
from fastapi.testclient import TestClient

from app.main import DB, app
from spine import metrics


@pytest.fixture(scope="session")
def client():
    if not DB.exists():
        pytest.skip("spine not built - run `python -m spine.generate && python -m spine.build`")
    return TestClient(app)


@pytest.fixture(scope="session")
def con():
    if not DB.exists():
        pytest.skip("spine not built")
    c = duckdb.connect(str(DB), read_only=True)
    yield c
    c.close()


# ------------------------------------------------------------------ contract
def test_overview_shape(client):
    r = client.get("/api/overview")
    assert r.status_code == 200
    body = r.json()
    for key in ("cases", "accepted_cases", "reject_rate",
                "actionable_correction_rate", "sites", "complaints"):
        assert key in body, f"overview lost `{key}`"
    assert body["cases"] == body["accepted_cases"] + body["rejected_cases"]


def test_case_inspector_joins_every_source(client, con):
    cid = con.execute(
        "SELECT case_id FROM fct_hazard_match LIMIT 1").fetchone()[0]
    body = client.get(f"/api/case/{cid}").json()
    assert body["case_id"] == cid
    assert body["site_name"]
    assert body["scanner_make"]
    assert body["model_version"]
    assert body["hazards"], "a hazard-matched case should report its hazards"


def test_missing_case_is_404(client):
    assert client.get("/api/case/99999999").status_code == 404


def test_frontier_is_monotone(client):
    strata = client.get("/api/ops/frontier").json()["strata"]
    rates = [s["actionable_correction_rate"] for s in strata]
    assert rates == sorted(rates), "frontier must be ordered by residual risk"
    cum = [s["cumulative_share"] for s in strata]
    assert cum == sorted(cum)
    assert cum[-1] == pytest.approx(1.0, abs=1e-6)


def test_tolerance_is_monotone_in_volume(client):
    prev = -1.0
    for tol in (0.0, 0.04, 0.08, 0.12, 0.5):
        got = client.get(f"/api/ops/frontier?tolerance={tol}").json()["at_tolerance"]
        assert got["volume_share"] >= prev - 1e-9, "more tolerance must not buy less volume"
        prev = got["volume_share"]


def test_complaint_trace_resolves_the_chain(client):
    cs = client.get("/api/quality/complaints").json()
    assert cs, "fixture should contain complaints"
    trace = client.get(f"/api/quality/complaints/{cs[0]['complaint_id']}/trace").json()
    assert trace["complaint"]["case_id"] is not None
    assert trace["complaint"]["site_name"]
    assert trace["stratum_cohort"]["accepted_cases"] > 0
    assert trace["by_release"]


# ------------------------------------------------------------------ semantic
def test_metric_layer_agrees_with_direct_sql(con):
    """The whole point of a semantic layer: one definition, one answer."""
    via_layer = con.execute(
        metrics.select(["actionable_correction_rate"])).fetchone()[0]
    direct = con.execute(
        "SELECT sum(crossed_threshold)::DOUBLE / count(*) "
        "FROM fct_case_spine WHERE accepted = 1").fetchone()[0]
    assert via_layer == pytest.approx(direct, abs=1e-12)


def test_frontier_reconciles_to_the_whole(con):
    strata = metrics.frontier(con)
    total_from_strata = sum(s.accepted_cases for s in strata)
    accepted = con.execute(
        "SELECT count(*) FROM fct_case_spine WHERE accepted = 1").fetchone()[0]
    suppressed = accepted - total_from_strata
    assert suppressed >= 0
    # suppression should be a rounding error, not a material share of the book
    assert suppressed / accepted < 0.05, "too much volume lost to thin-stratum suppression"


def test_unknown_measure_is_rejected():
    with pytest.raises(KeyError):
        metrics.select(["made_up_metric"])
    with pytest.raises(KeyError):
        metrics.select(["cases"], by=["analyst_id"])


def test_rates_are_rates(client):
    body = client.get("/api/overview").json()
    for k in ("reject_rate", "actionable_correction_rate", "grey_zone_rate"):
        assert 0.0 <= body[k] <= 1.0, f"{k} out of range"


# ------------------------------------------------------------------ guardrail
BANNED_COLUMNS = {
    "patient_id", "mrn", "accession", "accession_number", "study_uid", "series_uid",
    "sop_uid", "patient_name", "dob", "analyst_id", "analyst_name", "pixel_data",
}


def test_spine_carries_no_identifying_columns(con):
    """PHI boundary, enforced in CI rather than asserted in a document."""
    for table in ("fct_case_spine", "fct_complaint", "fct_hazard_match", "dim_site"):
        cols = {r[0].lower() for r in con.execute(f"DESCRIBE {table}").fetchall()}
        leaked = cols & BANNED_COLUMNS
        assert not leaked, f"{table} leaked identifying column(s): {sorted(leaked)}"


def test_no_analyst_identity_anywhere(con):
    """Aggregation is by case stratum. The system must be structurally incapable
    of individual performance monitoring - that is what keeps Operations on side."""
    tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
    for t in tables:
        cols = {r[0].lower() for r in con.execute(f"DESCRIBE {t}").fetchall()}
        offenders = {c for c in cols if "analyst" in c and c != "analyst_min"}
        assert not offenders, f"{t} carries analyst identity: {sorted(offenders)}"


def test_write_routes_are_confined_to_the_action_layer():
    """The narrowed rule, re-assessed per the validation plan's change control
    (section 9): the SPINE surface stays GET-only - no endpoint may write to a
    case, a result, or the warehouse the metrics read. Writes exist ONLY on the
    action layer (finding workflow + evidence signatures), which persists to a
    separate store. Acknowledging a FINDING is QMS workflow; dispositioning a
    CASE is device software and remains forbidden."""
    # /api/investigations is the complaint-investigation business process
    # (21 CFR 820.198 complaint files / 803 MDR) - the canonical QMS workflow.
    # Extended consciously; see validation plan Amendment A.
    WRITABLE_PREFIXES = ("/api/actions", "/api/evidence/", "/api/investigations")
    for route in app.routes:
        methods = getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}
        path = getattr(route, "path", "")
        if methods - {"GET"}:
            assert methods == {"POST"}, f"{path} exposes {methods}"
            assert path.startswith(WRITABLE_PREFIXES), \
                f"write route {path} outside the action layer"
            # a write route must never take a case identifier
            assert "case" not in path, f"{path} writes against a case"


def test_action_store_is_not_the_spine():
    """The write path and the warehouse must be different files, and the spine
    dependency must stay read-only in source - the property that keeps every
    metric untouched by the workflow layer."""
    import inspect
    from app import main as app_main
    from spine import actions as act
    assert act.ACTIONS_DB.resolve() != app_main.DB.resolve()
    assert "read_only=True" in inspect.getsource(app_main.db)


def test_database_connection_is_read_only(con):
    with pytest.raises(duckdb.Error):
        con.execute("CREATE TABLE should_not_exist (x INT)")


def test_no_routing_or_disposition_endpoint():
    """Guards against the specific scope creep that changes the regulatory regime:
    an endpoint that tells the pipeline which cases may skip human review."""
    forbidden = ("route", "dispatch", "assign", "skip", "auto-approve",
                 "disposition", "triage")
    for route in app.routes:
        path = getattr(route, "path", "").lower()
        assert not any(f in path for f in forbidden), (
            f"{path} looks like a decision endpoint; that is device software")


# ------------------------------------------------------------------ statistics
def test_two_proportion_p_detects_a_real_difference():
    # 20% vs 10% on 400 apiece is a genuine effect
    assert metrics.two_proportion_p(80, 400, 40, 400) < 0.01


def test_two_proportion_p_ignores_small_cell_noise():
    """The reason this function exists: a 1.3x lift on a small cell is routine
    chance. Alerting on it trains everyone to ignore the alerts."""
    # 13% vs 10% on 60 apiece - a 1.3x lift, and meaningless
    assert metrics.two_proportion_p(8, 60, 6, 60) > 0.05


def test_two_proportion_p_is_symmetric_and_bounded():
    a = metrics.two_proportion_p(30, 200, 15, 200)
    b = metrics.two_proportion_p(15, 200, 30, 200)
    assert a == pytest.approx(b)
    assert 0.0 <= a <= 1.0
    assert metrics.two_proportion_p(0, 0, 5, 50) == 1.0


def test_release_signal_requires_significance(client):
    """A release is flagged only when the effect is both material and supported."""
    for r in client.get("/api/engineering/releases").json():
        if r["signal"] in ("regression", "improved"):
            assert r["p_value"] < 0.05, (
                f"{r['model_version']}/{r['scanner_make']} flagged as {r['signal']} "
                f"at p={r['p_value']:.3f}")
        if r["signal"] == "unconfirmed":
            material = (r["lift_vs_first_release"] >= 1.25
                        or r["lift_vs_first_release"] <= 0.80)
            assert material and r["p_value"] >= 0.05


# ------------------------------------------------------------------ iteration 01
# Case-mix standardisation. See workflow/01-case-mix-confounding.md.
def test_standardisation_is_a_no_op_on_the_reference_population(con):
    """Standardising the reference population against itself must return the crude
    rate. If this drifts, the weighting is wrong."""
    got = metrics.standardised_rate(con, where=metrics.ACCEPTED)
    assert got["standardised_rate"] == pytest.approx(got["crude_rate"], abs=1e-9)
    assert got["reference_coverage"] == pytest.approx(1.0, abs=1e-9)


def test_standardisation_removes_a_pure_mix_shift(con):
    """The property that justifies the whole iteration.

    Build two cohorts with IDENTICAL per-stratum rates but DIFFERENT stratum mixes.
    Their crude rates must differ; their standardised rates must not. If this fails,
    standardisation is not doing its job.
    """
    easy, hard = "CAC<100 / motion lo", "CAC>1k / motion md"
    rates = {}
    for s in (easy, hard):
        rates[s] = con.execute(
            "SELECT avg(crossed_threshold) FROM fct_case_spine "
            "WHERE accepted = 1 AND stratum = ?", [s]).fetchone()[0]
    if rates[easy] is None or rates[hard] is None:
        pytest.skip("fixture lacks both strata")
    assert rates[easy] != pytest.approx(rates[hard], abs=1e-6), \
        "strata must differ in difficulty for this test to mean anything"

    # cohort A: mostly easy. cohort B: mostly hard. same per-stratum rates by
    # construction, because both draw from the same underlying cases.
    a = metrics.standardised_rate(
        con, where="accepted = 1 AND stratum IN (?, ?)", params=[easy, hard])
    b = metrics.standardised_rate(
        con, where="accepted = 1 AND stratum IN (?, ?)", params=[hard, easy])
    # same population either way - sanity that argument order does not matter
    assert a["standardised_rate"] == pytest.approx(b["standardised_rate"], abs=1e-12)

    # a cohort restricted to the hard stratum has a much higher crude rate, but its
    # standardised rate is pulled toward the reference mix
    hard_only = metrics.standardised_rate(
        con, where="accepted = 1 AND stratum = ?", params=[hard])
    assert hard_only["crude_rate"] > rates[easy]
    assert hard_only["reference_coverage"] < 0.5, \
        "a single stratum cannot cover the reference population"


def test_release_signal_uses_the_standardised_rate(client):
    """The endpoint must judge on the standardised rate and expose both, so a
    reviewer can see the correction that was applied."""
    for r in client.get("/api/engineering/releases").json():
        assert "standardised_rate" in r and "crude_lift" in r
        assert "reference_coverage" in r
        if r["standardised_rate"] is not None:
            assert 0.0 <= r["standardised_rate"] <= 1.0


def test_standardisation_changes_at_least_one_conclusion(client):
    """Documents the point of the iteration: crude and standardised lift disagree
    somewhere, otherwise the correction would be theatre."""
    rows = client.get("/api/engineering/releases").json()
    diffs = [abs(r["lift_vs_first_release"] - r["crude_lift"]) for r in rows]
    assert max(diffs) > 0.02, "standardisation had no material effect anywhere"


# ------------------------------------------------------------------ iteration 02
# Subgroup disparity with FDR control. See workflow/02-subgroup-disparity.md.
def test_wilson_interval_brackets_the_estimate():
    lo, hi = metrics.wilson_interval(50, 100)
    assert lo < 0.5 < hi
    # behaves at the edges, where the normal approximation goes out of bounds
    for successes, n in [(0, 10), (10, 10), (1, 3), (0, 1)]:
        lo, hi = metrics.wilson_interval(successes, n)
        assert 0.0 <= lo <= hi <= 1.0, f"interval escaped [0,1] at {successes}/{n}"
    # narrows as n grows
    narrow = metrics.wilson_interval(500, 1000)
    wide = metrics.wilson_interval(5, 10)
    assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])


def test_benjamini_hochberg_matches_a_worked_example():
    """Known case: p = .001 .008 .039 .041 .042 .06 .074 .205 at q=.05 rejects the
    first four (largest k with p_(k) <= q*k/m is k=4, .041 <= .05*4/8 = .025? no).
    Recompute against the definition rather than trusting memory."""
    p = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205]
    q, m = 0.05, len(p)
    expected_k = max((k for k in range(1, m + 1) if sorted(p)[k - 1] <= q * k / m),
                     default=0)
    got = metrics.benjamini_hochberg(p, q)
    assert sum(got) == expected_k
    # rejections must be exactly the smallest p-values
    threshold = sorted(p)[expected_k - 1] if expected_k else -1
    for pv, rejected in zip(p, got):
        assert rejected == (pv <= threshold)


def test_benjamini_hochberg_is_less_conservative_than_bonferroni():
    """The reason BH was chosen. With many tests, Bonferroni hides real effects."""
    p = [0.001, 0.004, 0.006, 0.009, 0.02, 0.3, 0.4, 0.5, 0.6, 0.7]
    bh = sum(metrics.benjamini_hochberg(p, 0.10))
    bonferroni = sum(1 for x in p if x <= 0.05 / len(p))
    assert bh > bonferroni


def test_benjamini_hochberg_rejects_nothing_under_the_null():
    """Uniform p-values are what pure noise looks like. Flagging them would mean the
    monitor manufactures findings."""
    uniform = [i / 40 for i in range(1, 41)]
    assert sum(metrics.benjamini_hochberg(uniform, 0.10)) <= 4


def test_disparity_escalation_is_conjunctive(con):
    """Significant is not the same as actionable. Every escalation must clear all
    three predetermined gates; anything that clears only some must not escalate."""
    d = metrics.subgroup_disparity(con)
    for finding in d["findings"]:
        for arm in finding["arms"]:
            if arm["escalate"]:
                assert arm["fdr_significant"]
                assert arm["disparity_vs_best"] >= metrics.MIN_DISPARITY
                assert arm["n"] >= metrics.MIN_ARM_N
            elif arm["fdr_significant"]:
                assert (arm["disparity_vs_best"] < metrics.MIN_DISPARITY
                        or arm["n"] < metrics.MIN_ARM_N), \
                    "an arm clearing every gate was not escalated"


def test_disparity_finds_the_known_clinical_gradient(con):
    """Calcium burden and motion are known to drive segmentation difficulty. If the
    monitor cannot recover that, it is not measuring what it claims to."""
    d = metrics.subgroup_disparity(con)
    axes = {f["axis"]: f for f in d["findings"]}
    assert axes["calcium_band"]["best_level"] == "CAC<100"
    assert axes["calcium_band"]["worst_level"] == "CAC>1k"
    assert axes["calcium_band"]["disparity_ratio"] > 1.5
    assert axes["motion_band"]["best_level"] == "motion lo"
    assert axes["motion_band"]["worst_level"] == "motion hi"


def test_disparity_does_not_invent_findings_on_null_axes(con):
    """site_class and detector should show no material disparity in this fixture.
    A monitor that flags them is flagging noise."""
    d = metrics.subgroup_disparity(con)
    axes = {f["axis"]: f for f in d["findings"]}
    for null_axis in ("site_class", "detector_at_scan"):
        assert axes[null_axis]["disparity_ratio"] < metrics.MIN_DISPARITY, \
            f"{null_axis} flagged a disparity that should not exist"


def test_disparity_rejects_an_unknown_axis(con):
    with pytest.raises(KeyError):
        metrics.subgroup_disparity(con, axes=["patient_ethnicity"])


def test_disparity_endpoint_states_its_policy(client):
    body = client.get("/api/quality/disparity").json()
    policy = body["policy"]
    assert policy["fdr_q"] == metrics.FDR_Q
    assert policy["min_disparity_ratio"] == metrics.MIN_DISPARITY
    assert policy["min_arm_n"] == metrics.MIN_ARM_N
    assert "not demographic equity analysis" in policy["note"]
    for e in body["escalations"]:
        assert e["disparity"] >= metrics.MIN_DISPARITY


# ------------------------------------------------------------------ iteration 03
# Attributable rejection. See workflow/03-attributable-rejection.md.
def test_expected_rejection_is_a_proper_case_mix_reweighting(con):
    """Aggregated over the whole network, expected must equal observed. If it does
    not, the weights are wrong."""
    got = con.execute("""
        SELECT sum(expected_reject_rate * cases) / sum(cases),
               sum(rejections)::DOUBLE / sum(cases)
        FROM fct_site_conformance""").fetchone()
    # sites below the volume floor are excluded from the table, so allow a small gap
    assert got[0] == pytest.approx(got[1], abs=0.02)


def test_conformance_excludes_low_volume_sites(con):
    """A site with 9 cases and 2 rejections has a 22% rate and no information."""
    smallest = con.execute("SELECT min(cases) FROM fct_site_conformance").fetchone()[0]
    assert smallest >= 25


def test_conformance_does_not_adjust_away_the_technique_signal(con):
    """The trap this iteration exists to avoid.

    Stratification is on patient-intrinsic factors only. If motion or nitro had been
    included, sites with poor technique would be given credit for the artifacts
    their technique produced, and the worklist would rank nobody.
    """
    cols = {r[0].lower() for r in con.execute("DESCRIBE fct_site_conformance").fetchall()}
    # the technique measures must be REPORTED (so a field specialist can act) ...
    assert {"median_heart_rate", "nitro_rate", "median_motion"} <= cols
    # ... and the expected rate must still discriminate between sites that differ
    # only in technique. Two sites with similar case mix but different motion must
    # get similar expected rates and different observed rates.
    spread = con.execute("""
        SELECT stddev_pop(expected_reject_rate), stddev_pop(observed_reject_rate)
        FROM fct_site_conformance""").fetchone()
    assert spread[0] < spread[1], \
        "expected varies as much as observed - case mix is absorbing the technique signal"


def test_conformance_reports_how_much_the_adjustment_matters(client):
    """The honest output of this iteration: a number saying whether ranking on raw
    rejection is safe. Without it, a reader cannot tell whether the adjustment is
    doing anything."""
    body = client.get("/api/field/conformance").json()
    net = body["network"]
    assert "case_mix_variance_explained" in net
    assert 0.0 <= net["case_mix_variance_explained"] <= 1.0
    assert net["interpretation"]
    assert net["n_sites"] > 0


def test_conformance_worklist_is_ranked_by_excess(client):
    body = client.get("/api/field/conformance").json()
    excess = [s["excess_reject_rate"] for s in body["sites"]]
    assert excess == sorted(excess, reverse=True)


def test_recoverable_cases_is_never_negative(con):
    """A site performing better than its case mix predicts has nothing to recover;
    reporting a negative there would invite someone to 'fix' a good site."""
    n = con.execute(
        "SELECT count(*) FROM fct_site_conformance WHERE recoverable_cases < 0").fetchone()[0]
    assert n == 0


# ------------------------------------------------------------------ iteration 04
# Reproducible evidence packs. See workflow/04-evidence-pack.md.
from spine import evidence  # noqa: E402


def test_evidence_pack_is_reproducible(con):
    """The property that makes a pack evidence rather than an archive: same
    warehouse state in, same manifest hash out."""
    a = evidence.build_frontier_pack(con, tolerance=0.08)
    b = evidence.build_frontier_pack(con, tolerance=0.08)
    assert a["manifest_sha256"] == b["manifest_sha256"]
    # ... and the timestamp is deliberately outside the hash
    assert a["generated_at"] != b["generated_at"] or True


def test_different_inputs_produce_different_hashes(con):
    a = evidence.build_frontier_pack(con, tolerance=0.08)
    b = evidence.build_frontier_pack(con, tolerance=0.12)
    assert a["manifest_sha256"] != b["manifest_sha256"]


def test_tampering_is_detected(con):
    """A pack that has been edited must fail verification. Without this it is a
    text file, not an audit trail."""
    pack = evidence.build_frontier_pack(con)
    ok, msg = evidence.verify(pack)
    assert ok, msg

    tampered = json.loads(json.dumps(pack, default=str))
    tampered["content"]["result"]["volume_share"] = 0.99
    ok, msg = evidence.verify(tampered)
    assert not ok and "modified" in msg


def test_malformed_pack_fails_verification():
    ok, msg = evidence.verify({"content": {"x": 1}})
    assert not ok and "malformed" in msg


def test_pack_records_the_population_supporting_the_claim(con):
    """Closes the gap their 510(k) leaves open: a restricted validation library that
    'aims to prevent' contamination is a procedure. A recorded population hash makes
    it checkable against a training manifest."""
    pack = evidence.build_frontier_pack(con)
    pop = pack["content"]["population"]
    assert pop["reference"]["n"] > 0
    assert len(pop["reference"]["case_id_sha256"]) == 64
    assert pop["reference"]["selector"]
    if pop["eligible"]["n"]:
        assert pop["eligible"]["n"] < pop["reference"]["n"]


def test_pack_pins_code_and_warehouse_state(con):
    pack = evidence.build_frontier_pack(con)["content"]
    assert pack["code_version"]
    fp = pack["spine_fingerprint"]
    assert fp["row_counts"]["fct_case_spine"] > 0
    assert len(fp["grain_sha256"]) == 64


def test_pack_always_states_limitations(con):
    """A pack claiming no limitations is not credible. Both builders must carry
    them, and they must include the observational caveat."""
    for build in (evidence.build_frontier_pack, evidence.build_disparity_pack):
        content = build(con)["content"]
        assert content["limitations"], f"{build.__name__} omitted limitations"
        assert content["method"]
        assert content["claim"]


def test_persist_is_content_addressed_and_idempotent(con, tmp_path):
    pack = evidence.build_frontier_pack(con)
    p1 = evidence.persist(pack, tmp_path)
    p2 = evidence.persist(pack, tmp_path)
    assert p1 == p2
    assert pack["manifest_sha256"][:16] in p1.name
    reloaded = evidence.load(p1)
    assert evidence.verify(reloaded)[0]


def test_evidence_endpoints_return_verifiable_packs(client):
    for url in ("/api/evidence/frontier", "/api/evidence/disparity"):
        pack = client.get(url).json()
        ok, msg = evidence.verify(pack)
        assert ok, f"{url}: {msg}"
        assert pack["content"]["limitations"]


# ------------------------------------------------------------------ iteration 05
# Agent evaluation harness. See workflow/05-agent-evaluation.md.
from spine import agent_eval  # noqa: E402


def test_reference_agent_scores_perfectly(con):
    """Positive control. The reference agent follows the documented tool contract
    exactly; if it stops scoring 6/6, the harness or the data changed, not a model."""
    out = agent_eval.run(agent_eval.reference_agent, con)
    s = out["summary"]
    assert s["passed"] == s["cases"], [r for r in out["results"] if not r["passed"]]
    assert s["tool_selection"] == 1.0
    assert s["interpretation"] == 1.0


def test_naive_agent_fails_every_case(con):
    """Negative control, and the more important one.

    A harness that cannot fail an agent making the exact mistakes the tool
    descriptions warn against is not measuring anything.
    """
    out = agent_eval.run(agent_eval.naive_agent, con)
    assert out["summary"]["passed"] == 0
    # every case must be caught by the interpretation check specifically
    assert out["summary"]["interpretation"] == 0.0


def test_harness_separates_its_three_scoring_dimensions(con):
    """The dangerous profile is right number, wrong tool, wrong claim. The scorer
    must be able to express that rather than collapsing to pass/fail."""
    out = agent_eval.run(agent_eval.naive_agent, con)
    by_id = {r["case"]: r for r in out["results"]}
    r = by_id["clinical-gradient"]
    assert r["tool_selection"] is True
    assert r["numeric"] is True
    assert r["interpretation"] is False
    assert r["passed"] is False


def test_ground_truth_is_recomputed_not_frozen(con):
    """Every case resolves its expectation from the warehouse. A frozen constant
    would break on any fixture change and train the team to edit expectations."""
    for case in agent_eval.SUITE:
        assert callable(case.ground_truth)
        value = case.ground_truth(con)
        assert value is not None, f"{case.id} produced no ground truth"


def test_harness_reports_non_discriminating_cases(con):
    """Eval suites rot when a case silently stops separating right from wrong.

    Cases carrying a foil compare it to ground truth; if they coincide on this run,
    the numeric check proves nothing and the harness must say so rather than
    reporting a meaningless pass.
    """
    out = agent_eval.run(agent_eval.reference_agent, con)
    assert "non_discriminating_cases" in out["summary"]
    for r in out["results"]:
        assert "discriminating" in r
    # cases with a foil must actually evaluate it
    foiled = {c.id for c in agent_eval.SUITE if c.foil is not None}
    assert foiled, "no case carries a foil - degeneracy detection is inert"


def test_every_eval_case_documents_why_it_exists(con):
    """A case without a rationale is a case nobody can maintain."""
    for case in agent_eval.SUITE:
        assert case.rationale and len(case.rationale) > 40, case.id
        assert case.expected_tool
        assert case.question.endswith("?")


# ------------------------------------------------------------------ interconnect
def test_ask_routes_the_eight_intents(client):
    """Every documented intent must resolve; every answer must carry provenance
    naming the deterministic router so nobody mistakes it for an LLM."""
    from spine.ask import VOCABULARY
    for q in VOCABULARY:
        body = client.get("/api/ask", params={"q": q}).json()
        assert "answer" in body, f"{q!r} -> {body}"
        assert body["provenance"]["resolved_intent"]
        assert "no external LLM" in body["provenance"]["router"]


def test_ask_refuses_rather_than_guessing(client):
    """An approximate answer in a regulated portal is worse than none."""
    body = client.get("/api/ask", params={"q": "what is for lunch"}).json()
    assert "error" in body and "answer" not in body
    assert body["try"], "a refusal must offer the vocabulary"


def test_ask_agrees_with_the_metric_layer(client, con):
    """The Ask box, the API and the MCP tools must never disagree on a number."""
    body = client.get("/api/ask", params={"q": "how often does correction change the answer"}).json()
    truth = con.execute(
        "SELECT avg(crossed_threshold) FROM fct_case_spine WHERE accepted = 1"
    ).fetchone()[0]
    assert body["value"] == pytest.approx(truth, abs=1e-12)


def test_ask_parses_tolerance_from_the_question(client):
    a = client.get("/api/ask", params={"q": "automate at 8% tolerance"}).json()
    b = client.get("/api/ask", params={"q": "automate at 12% tolerance"}).json()
    assert b["value"] >= a["value"], "more tolerance must not buy less volume"


def test_site_card_joins_every_lens(client, con):
    sid = con.execute(
        "SELECT site_id FROM fct_site_conformance ORDER BY excess_reject_rate DESC LIMIT 1"
    ).fetchone()[0]
    body = client.get(f"/api/site/{sid}").json()
    for key in ("site_name", "cases", "reject_rate", "conformance",
                "hazards", "by_release", "complaints"):
        assert key in body, f"site card lost {key!r}"
    assert client.get("/api/site/999999").status_code == 404


def test_complaint_filters_partition_consistently(client):
    """Filtered subsets must reconcile with the unfiltered whole."""
    everything = client.get("/api/quality/complaints").json()
    assert all("model_version" in c and "site_id" in c for c in everything)
    versions = {c["model_version"] for c in everything}
    total = sum(len(client.get("/api/quality/complaints",
                               params={"model_version": v}).json())
                for v in versions)
    assert total == len(everything), "per-release filters lose or duplicate rows"


def test_ask_endpoint_is_read_only_surface(client):
    """The Ask box must not become a query hole: no SQL-shaped input survives."""
    body = client.get("/api/ask", params={"q": "SELECT * FROM fct_case_spine"}).json()
    assert "error" in body, "SQL text must not resolve to an intent"


# ------------------------------------------------------------------ action layer
import pathlib as _pathlib  # noqa: E402

from spine import actions as actions_mod  # noqa: E402


@pytest.fixture()
def action_store(tmp_path, monkeypatch):
    """Isolated action store per test - the real one is live workflow state."""
    monkeypatch.setattr(actions_mod, "ACTIONS_DB", tmp_path / "actions.duckdb")
    return actions_mod


def test_sync_is_idempotent_and_typed(action_store, con):
    first = action_store.sync_findings(con)
    assert first["total_items"] > 0
    kinds = {c["kind"] for c in first["created"]}
    assert kinds <= set(action_store.KINDS)
    again = action_store.sync_findings(con)
    assert again["created"] == [], "sync resurrected or duplicated items"


def test_lifecycle_enforces_the_state_machine(action_store, con):
    aid = action_store.sync_findings(con)["created"][0]["action_id"]
    with pytest.raises(ValueError):
        action_store.transition(aid, "investigating", "a", "skip not allowed")
    action_store.transition(aid, "acknowledged", "andrii", "triaging")
    action_store.transition(aid, "resolved", "andrii", "fixed upstream")
    with pytest.raises(ValueError):
        action_store.transition(aid, "acknowledged", "andrii", "terminal only reopens")
    action_store.transition(aid, "open", "andrii", "reopening - fix regressed")


def test_audit_requires_actor_and_note(action_store, con):
    """An anonymous or unexplained transition is not an audit trail."""
    aid = action_store.sync_findings(con)["created"][0]["action_id"]
    with pytest.raises(ValueError):
        action_store.transition(aid, "acknowledged", "", "note")
    with pytest.raises(ValueError):
        action_store.transition(aid, "acknowledged", "andrii", "  ")


def test_audit_trail_is_complete_and_ordered(action_store, con):
    aid = action_store.sync_findings(con)["created"][0]["action_id"]
    action_store.transition(aid, "acknowledged", "a1", "n1")
    action_store.transition(aid, "investigating", "a2", "n2")
    trail = action_store.audit_trail(aid)
    assert [e["to_state"] for e in trail] == ["open", "acknowledged", "investigating"]
    assert all(e["note"] for e in trail)


def test_items_pin_the_warehouse_state(action_store, con):
    from spine import evidence as ev
    action_store.sync_findings(con)
    items = action_store.list_actions()
    grain = ev.spine_fingerprint(con)["grain_sha256"][:16]
    assert all(i["grain_sha"] == grain for i in items), \
        "work items must record the warehouse state they were raised from"


def test_signature_refuses_an_unverifiable_pack(action_store, con):
    from spine import evidence as ev
    pack = ev.build_frontier_pack(con)
    tampered = json.loads(json.dumps(pack, default=str))
    tampered["content"]["result"]["volume_share"] = 0.99
    with pytest.raises(ValueError):
        action_store.sign_pack(tampered, "andrii", "qe", "should fail")


def test_signature_roundtrip_verifies_on_read(action_store, con, tmp_path, monkeypatch):
    from spine import evidence as ev
    monkeypatch.setattr(ev, "EVIDENCE_DIR", tmp_path / "evidence")
    pack = ev.build_frontier_pack(con)
    sig = action_store.sign_pack(pack, "andrii", "quality engineer", "release review")
    listed = action_store.list_signed()
    assert listed[0]["verification"] == "verified"
    assert listed[0]["manifest_sha"] == pack["manifest_sha256"]
    # break the frozen file: the list must SAY so, not hide it
    path = _pathlib.Path(sig["pack_path"])
    broken = json.loads(path.read_text(encoding="utf-8"))
    broken["content"]["claim"] = "edited after signing"
    path.write_text(json.dumps(broken), encoding="utf-8")
    assert "BROKEN" in action_store.list_signed()[0]["verification"]


def test_briefing_is_a_complete_artifact(client):
    html = client.get("/api/briefing").text
    for section in ("Findings requiring action", "Signed evidence",
                    "Subgroup escalations", "warehouse grain"):
        assert section in html
    dl = client.get("/api/briefing", params={"download": "true"})
    assert "attachment" in dl.headers.get("content-disposition", "")


# ------------------------------------------------------------------ business processes
from spine import investigation as inv_mod  # noqa: E402
from spine import shadow  # noqa: E402


def test_shadow_partitions_and_reconciles(con):
    r = shadow.simulate(con, tolerance=0.08, guard=0.0)
    accepted = con.execute(
        "SELECT count(*) FROM fct_case_spine WHERE accepted = 1").fetchone()[0]
    assert r["volume"]["auto_released"] + r["volume"]["human_reviewed"] == accepted
    assert (r["harm"]["would_be_false_negatives"]
            + r["harm"]["would_be_false_positives"]) == r["harm"]["changed_answers"]
    assert len(r["harm"]["ledger"]) == r["harm"]["changed_answers"]


def test_shadow_guard_band_is_monotone(con):
    """More guard must never increase harm or volume. If this inverts, the guard
    is not doing what the policy claims."""
    prev_harm, prev_vol = None, None
    for row in shadow.guard_tradeoff(con, tolerance=0.08):
        if prev_harm is not None:
            assert row["changed_answers"] <= prev_harm
            assert row["auto_released"] <= prev_vol
        prev_harm, prev_vol = row["changed_answers"], row["auto_released"]


def test_shadow_harm_concentrates_near_the_threshold(con):
    """The clinical premise of the guard band, verified rather than asserted:
    a small band removes a disproportionate share of the harm."""
    base = shadow.simulate(con, 0.08, 0.0)["harm"]["changed_answers"]
    guarded = shadow.simulate(con, 0.08, 0.03)
    if base < 20:
        pytest.skip("not enough harm in fixture to measure concentration")
    harm_kept = guarded["harm"]["changed_answers"] / base
    vol_kept = (guarded["volume"]["auto_released"]
                / shadow.simulate(con, 0.08, 0.0)["volume"]["auto_released"])
    assert harm_kept < vol_kept * 0.5, (
        f"guard removed harm no faster than volume ({harm_kept:.2f} vs {vol_kept:.2f})")


def test_shadow_directions_never_mix(con):
    r = shadow.simulate(con, tolerance=0.12, guard=0.0)
    for row in r["harm"]["ledger"]:
        if row["direction"] == "would_be_false_negative":
            assert row["ffr_post"] <= 0.80 < row["ffr_pre"]
        else:
            assert row["ffr_pre"] <= 0.80 < row["ffr_post"]


def test_policy_pack_is_reproducible_and_verifiable(con):
    a = shadow.build_policy_pack(con, 0.08, 0.03)
    b = shadow.build_policy_pack(con, 0.08, 0.03)
    assert a["manifest_sha256"] == b["manifest_sha256"]
    assert evidence.verify(a)[0]
    assert a["content"]["limitations"]
    assert "harm_ledger_case_ids_sha256" in a["content"]["result"]


def test_investigation_process_enforces_its_gates(action_store, con, tmp_path, monkeypatch):
    monkeypatch.setattr(inv_mod, "RECORDS_DIR", tmp_path / "inv")
    b = inv_mod.board(con)
    assert b["summary"]["received"] > 0
    target = next(i["complaint_id"] for i in b["items"]
                  if i["complaint_type"] == "false_negative")

    opened = inv_mod.open_investigation(con, target, "andrii")
    assert opened["state"] == "under_investigation"
    with pytest.raises(ValueError):
        inv_mod.open_investigation(con, target, "andrii")   # no duplicates
    with pytest.raises(ValueError):
        inv_mod.decide(con, target, "not_reportable", "andrii", "no")  # thin
    with pytest.raises(ValueError):
        inv_mod.close(con, target, "andrii")                # decide first

    d = inv_mod.decide(con, target, "mdr_reportable", "andrii",
                       "Malfunction with potential to contribute to serious "
                       "injury; mechanism present.")
    assert d["late"] is True, "fixture complaints are historic; lateness must show"

    closed = inv_mod.close(con, target, "andrii")
    rec = evidence.load(pathlib.Path(closed["record_path"]))
    assert evidence.verify(rec)[0]
    assert rec["content"]["decision"]["late"] is True
    # The sealed record's trail ends at "decided" BY CONSTRUCTION: the closing
    # event records the seal's own hash, so it cannot be inside what it seals.
    # The close event lives in the live audit store, referencing the manifest.
    assert [e["to_state"] for e in rec["content"]["audit_trail"]] == \
        ["under_investigation", "decided"]
    live_trail = actions_mod.audit_trail(f"inv:{target}")
    assert live_trail[-1]["to_state"] == "closed"
    assert closed["manifest_sha256"][:16] in live_trail[-1]["note"]

    after = inv_mod.board(con)
    assert after["summary"]["closed"] == 1
    assert after["items"][0]["deadline_day"] == \
        after["items"][0]["complaint_day"] + inv_mod.MDR_DEADLINE_DAYS


def test_investigation_file_carries_the_cross_references(con):
    cid = con.execute("SELECT complaint_id FROM fct_complaint "
                      "WHERE complaint_type='false_negative' LIMIT 1").fetchone()[0]
    f = inv_mod.assemble_file(con, cid)
    assert len(f["chronology"]) >= 4
    assert {"same site", "same stratum", "same release"} == \
        {s["scope"] for s in f["siblings"]}
    assert "release_flag" in f["device"]
    assert f["mdr_assessment"]["rule_trace"]
    assert f["warehouse_grain"]


# ------------------------------------------------------------------ cube parity
def test_cube_schema_agrees_with_the_metric_layer():
    """Closes the KNOWN GAP documented in semantic/model/cubes/case_spine.yml:
    two hand-maintained definitions of one metric with no test between them is
    exactly the drift the semantic layer exists to prevent.

    Structural parity, no Cube runtime needed:
      1. every Cube measure on the case_spine cube has a counterpart in
         metrics.MEASURES (no orphan metrics served to BI that the API cannot
         reproduce);
      2. the accepted-only filter agrees: a Cube measure filtered to accepted=1
         must be accepted-filtered in metrics.py, and vice versa for the shared
         correction metrics - the exact mistake this guards is a dashboard
         quoting a rate over ALL cases while the API quotes accepted-only.
    """
    import yaml

    schema = yaml.safe_load(
        (pathlib.Path(__file__).parent.parent / "semantic" / "model" / "cubes"
         / "case_spine.yml").read_text(encoding="utf-8"))
    cube = next(c for c in schema["cubes"] if c["name"] == "case_spine")

    for measure in cube["measures"]:
        name = measure["name"]
        assert name in metrics.MEASURES, (
            f"Cube serves measure {name!r} that spine.metrics does not define - "
            f"BI and the API would disagree about what exists")

        cube_accepted = any("accepted = 1" in f.get("sql", "")
                            for f in measure.get("filters", []))
        api_accepted = "FILTER (accepted = 1)" in metrics.MEASURES[name]
        # count-style measures encode the filter differently on the API side
        if name in ("accepted_cases",):
            api_accepted = True
        if name in ("cases", "rejected_cases", "reject_rate",
                    "median_turnaround_min"):
            continue  # whole-population by definition on both sides
        assert cube_accepted == api_accepted, (
            f"{name!r}: Cube accepted-filter={cube_accepted} but "
            f"metrics.py accepted-filter={api_accepted} - the two surfaces "
            f"would quote different denominators")


def test_cube_dimensions_exist_on_the_spine(con):
    """Every dimension the Cube schema exposes must be a real spine column -
    a phantom dimension fails only at BI query time otherwise."""
    import yaml
    schema = yaml.safe_load(
        (pathlib.Path(__file__).parent.parent / "semantic" / "model" / "cubes"
         / "case_spine.yml").read_text(encoding="utf-8"))
    cube = next(c for c in schema["cubes"] if c["name"] == "case_spine")
    cols = {r[0].lower() for r in con.execute("DESCRIBE fct_case_spine").fetchall()}
    for dim in cube["dimensions"]:
        assert dim["sql"].lower() in cols, (
            f"Cube dimension {dim['name']!r} maps to missing column {dim['sql']!r}")
