"""
Playwright against a REAL DEPLOYMENT.

The suite in test_lenses.py boots its own server on a random port inside the test
process. This one drives whatever is actually deployed at DEPLOY_BASE - the
multi-worker, no-reload server started by `python -m deploy.local_deploy up`, or a
container from docker-compose.

The difference matters. An in-process fixture shares the test's interpreter,
imports, and working directory. A deployment does not: it has its own process
boundary, its own workers, its own static-file resolution, and its own copy of the
database. Defects that only appear across that boundary - a static asset that
resolves from the source tree but not from the image, a worker that cannot open a
read-only DuckDB file concurrently - are invisible to the in-process suite by
construction.

Skips cleanly when nothing is deployed, so it never blocks the fast path.

    python -m deploy.local_deploy up
    pytest tests/e2e/test_deployed.py
"""
from __future__ import annotations

import os
import re
import urllib.error
import urllib.request

import pytest
from playwright.sync_api import expect

DEPLOY_BASE = os.environ.get("DEPLOY_BASE", "http://127.0.0.1:8090")
# Remote deploys (the AWS free-tier instance) sit behind Caddy basic-auth.
# DEPLOY_AUTH="user:pass" flows into both the liveness probe and the browser.
DEPLOY_AUTH = os.environ.get("DEPLOY_AUTH", "")


def _auth_headers() -> dict:
    if not DEPLOY_AUTH:
        return {}
    import base64
    token = base64.b64encode(DEPLOY_AUTH.encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _http_credentials() -> dict | None:
    if not DEPLOY_AUTH or ":" not in DEPLOY_AUTH:
        return None
    user, password = DEPLOY_AUTH.split(":", 1)
    return {"username": user, "password": password}

PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def pct(text: str) -> float:
    m = PCT.search(text)
    assert m, f"expected a percentage in {text!r}"
    return float(m.group(1))


def _deployment_is_live() -> bool:
    try:
        req = urllib.request.Request(DEPLOY_BASE + "/api/overview",
                                     headers=_auth_headers())
        with urllib.request.urlopen(req, timeout=6) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


LIVE = _deployment_is_live()
pytestmark = pytest.mark.skipif(
    not LIVE,
    reason=f"no deployment at {DEPLOY_BASE} - run `python -m deploy.local_deploy up`")


@pytest.fixture(scope="module")
def _hydrated(browser):
    """One page load, shared across every read-only assertion in this module.

    Rebuilt as module-scoped after the function-scoped version thrashed: 27 tests
    each doing a full navigation plus full hydration (12 API calls and 8 canvas
    draws) starved the browser, and tests failed in fixture setup while the server
    was measurably healthy - 24 concurrent requests, all 200, max 95 ms. The
    bottleneck was never the deployment.

    It is also closer to reality: a person loads this page once and then reads it.
    Tests needing isolation (console capture, simulated API failure) take their own
    `page` instead.
    """
    ctx = browser.new_context(http_credentials=_http_credentials())
    pg = ctx.new_page()
    pg.goto(DEPLOY_BASE, wait_until="domcontentloaded")
    pg.wait_for_selector('body[data-ready="1"]', state="attached", timeout=45_000)
    yield pg
    ctx.close()


@pytest.fixture
def deployed(_hydrated):
    """Hand each test the shared page, reset to the landing lens.

    Structural selector, not get_by_role(name="Findings"): role-name matching is
    SUBSTRING by default, and once the Actions lens exists its "Sync findings"
    button also matches - two elements, strict-mode failure, and ten tests error
    in setup. The nav data-k attribute is unambiguous by construction.
    """
    _hydrated.locator('#nav button[data-k="findings"]').click()
    return _hydrated


@pytest.fixture
def _retired_deployed(page):
    """Load the app and wait until it has actually hydrated.

    The readiness signal has to live in the LANDING lens. Waiting on `#strata`
    (Operations) silently broke the moment Findings became the default view:
    wait_for_selector defaults to state="visible", the Operations lens is
    display:none until selected, so every test burned a 30-second timeout in setup
    and the suite took 13 minutes to report 25 errors that had nothing to do with
    the code under test.
    """
    # NOT networkidle. The page pulls webfonts and fires a dozen API calls, and
    # under concurrent test load the network may never go quiet - which showed up as
    # four tests failing on a 30s goto timeout while the app was perfectly healthy.
    # Wait for a real hydration signal instead of for silence.
    page.goto(DEPLOY_BASE, wait_until="domcontentloaded")
    # The app sets body[data-ready] only after every lens has rendered AND redraw()
    # has painted the canvases. Waiting on a table row instead was true too early.
    page.wait_for_selector('body[data-ready="1"]', state="attached", timeout=30_000)
    return page


def canvas_is_drawn(page, canvas_id: str) -> bool:
    """A canvas that exists but was never painted looks identical in the DOM to one
    that renders correctly. Sample the alpha channel instead of trusting presence."""
    return page.evaluate("""(id) => {
        const c = document.getElementById(id);
        if (!c || !c.width) return false;
        const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
        let painted = 0;
        for (let i = 3; i < d.length; i += 400) if (d[i] > 0) painted++;
        return painted > 50;
    }""", canvas_id)


# ------------------------------------------------------------------ smoke
def test_deployment_serves_the_client(deployed):
    expect(deployed).to_have_title("Case Spine")
    expect(deployed.locator(".kpi")).to_have_count(6)


def test_every_lens_is_reachable_on_the_deployment(deployed):
    """Five lenses now, not four. If this fails at four, the deployed client is
    behind the deployed API - which is the exact drift that made the browser suite
    test a stale surface for five iterations."""
    labels = ["Findings", "Operations", "Quality", "Engineering", "Field",
              "Evidence", "Actions", "Platform"]
    expect(deployed.locator("#nav button")).to_have_count(len(labels))
    for label in labels:
        deployed.get_by_role("button", name=label).click()
        assert deployed.locator("section.lens.on").count() == 1


def test_no_console_errors_across_every_lens(page):
    """Renderers that write into elements which do not exist throw on null and
    leave a blank panel that reads as 'no data'. Only the console catches it."""
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console.error: {m.text}")
            if m.type == "error" else None)

    page.goto(DEPLOY_BASE, wait_until="domcontentloaded")
    page.wait_for_selector('body[data-ready="1"]', state="attached", timeout=30_000)
    for label in ["Findings", "Operations", "Quality", "Engineering", "Field",
                  "Evidence", "Actions", "Platform"]:
        page.get_by_role("button", name=label).click()
        page.wait_for_timeout(250)
    assert not errors, "deployed client reported errors:\n  " + "\n  ".join(errors)


# ------------------------------------------------------------------ iteration 02
def test_disparity_panel_renders_and_separates_significance_from_escalation(deployed):
    deployed.get_by_role("button", name="Quality").click()
    deployed.wait_for_selector("#disp tbody tr")

    rows = deployed.locator("#disp tbody tr")
    assert rows.count() > 5, "disparity table did not populate"
    expect(deployed.locator("#dispPolicy")).to_contain_text("conjunctive")
    expect(deployed.locator("#dispPolicy")).to_contain_text("Benjamini")

    statuses = {r.locator(".tag").inner_text().strip().lower()
                for r in rows.all()}
    # the whole point of iteration 02: these are different states
    assert "escalate" in statuses
    assert "significant only" in statuses, (
        "no arm is significant-without-escalation, so the panel cannot demonstrate "
        "that detectability differs from actionability")


def test_no_escalated_arm_falls_below_the_effect_floor(deployed):
    """A label that disagrees with the number beside it is the dangerous defect."""
    deployed.get_by_role("button", name="Quality").click()
    deployed.wait_for_selector("#disp tbody tr")
    for row in deployed.locator("#disp tbody tr").all():
        status = row.locator(".tag").inner_text().strip().lower()
        ratio = float(row.locator("td").nth(5).inner_text().replace("x", ""))
        if status == "escalate":
            assert ratio >= 1.5, f"escalated arm at only {ratio}x"


# ------------------------------------------------------------------ iteration 03
def test_conformance_panel_reports_variance_explained(deployed):
    deployed.get_by_role("button", name="Field").click()
    deployed.wait_for_selector("#conf tbody tr")

    note = deployed.locator("#confNote").inner_text()
    assert "case mix explains" in note.lower()
    # iteration 03's finding: rejection is technique-driven, so this is small
    assert pct(note) < 20.0, f"variance explained implausibly high: {note}"

    excess = [pct(r.locator("td").nth(4).inner_text())
              for r in deployed.locator("#conf tbody tr").all()]
    assert excess == sorted(excess, reverse=True), "worklist not ranked by excess"


# ------------------------------------------------------------------ iteration 04
def test_evidence_pack_renders_with_its_limitations(deployed):
    """A pack shown without its limitations misrepresents what it establishes."""
    deployed.get_by_role("button", name="Evidence").click()
    deployed.wait_for_selector("#packTrace .hop")

    labels = [e.inner_text().casefold()
              for e in deployed.locator("#packTrace .lbl").all()]
    for expected in ["claim", "manifest", "population", "code version",
                     "warehouse", "method", "limitations"]:
        assert expected in labels, f"evidence pack lost the {expected!r} row: {labels}"

    assert len(deployed.locator("#packHash").inner_text().strip()) == 64


def test_evidence_pack_is_reproducible_through_the_browser(deployed):
    """Two independent HTTP fetches from a real browser against a real deployment
    must produce the identical manifest hash. This is the property the whole
    evidence model rests on, verified end to end rather than in-process."""
    deployed.get_by_role("button", name="Evidence").click()
    deployed.wait_for_selector("#packTrace .hop")

    deployed.locator("#verifyBtn").click()
    deployed.wait_for_selector("#hashVerdict")
    verdict = deployed.locator("#hashVerdict")
    expect(verdict).to_contain_text("Reproducible")
    assert verdict.get_attribute("data-same") == "true", verdict.inner_text()


def test_switching_claim_changes_the_hash(deployed):
    deployed.get_by_role("button", name="Evidence").click()
    deployed.wait_for_selector("#packHash")
    first = deployed.locator("#packHash").inner_text()

    deployed.locator("#claimSel").select_option("disparity")
    deployed.wait_for_timeout(600)
    second = deployed.locator("#packHash").inner_text()
    assert first != second, "different claims produced the same manifest hash"


# ------------------------------------------------------------------ deployment shape
def test_deployment_serves_static_assets_from_its_own_root(deployed):
    """Static resolution differs between running from a source tree and running
    from an image or a different working directory. Worth one assertion."""
    resp = deployed.request.get(DEPLOY_BASE + "/")
    assert resp.status == 200
    assert "text/html" in resp.headers.get("content-type", "")


def test_concurrent_requests_do_not_break_the_read_only_warehouse():
    """Multiple uvicorn workers each open the same read-only DuckDB file. A lock or
    handle problem shows up under concurrency and never in a single request.

    Genuinely parallel now. The previous version issued twelve requests in a list
    comprehension through Playwright's request context - sequential, so it proved
    nothing about concurrency while appearing to test it.
    """
    import concurrent.futures as cf
    import urllib.request

    def hit(_):
        with urllib.request.urlopen(
                DEPLOY_BASE + "/api/quality/disparity", timeout=30) as r:
            r.read()
            return r.status

    with cf.ThreadPoolExecutor(16) as pool:
        statuses = list(pool.map(hit, range(24)))
    assert all(s == 200 for s in statuses), statuses


def test_openapi_schema_is_served(deployed):
    resp = deployed.request.get(DEPLOY_BASE + "/openapi.json")
    assert resp.status == 200
    paths = resp.json()["paths"]
    for route in ("/api/quality/disparity", "/api/field/conformance",
                  "/api/evidence/frontier"):
        assert route in paths, f"{route} missing from the deployed schema"


# ------------------------------------------------------------------ narrative
def test_findings_lens_is_the_landing_view(deployed):
    """The portal opens on the argument, not on a table. If this regresses the
    thing becomes a data browser again, which is what it was criticised for."""
    expect(deployed.locator("#l-findings")).to_be_visible()
    expect(deployed.get_by_role("button", name="Findings")).to_have_attribute(
        "aria-selected", "true")


def test_hero_states_the_headline_number(deployed):
    big = deployed.locator("#heroBig").inner_text()
    assert PCT.search(big), f"hero is not a percentage: {big!r}"
    value = pct(big)
    assert 50 < value < 100, f"headline share implausible: {value}"
    expect(deployed.locator("#heroCap")).to_contain_text("confirmed the machine")
    assert deployed.locator("#heroStats .v").count() >= 4


@pytest.mark.parametrize("canvas_id", [
    "vizEffort", "vizDelta", "vizRelease", "vizDetector", "vizDisparity"])
def test_every_finding_visualisation_actually_paints(deployed, canvas_id):
    """Presence is not rendering. A blank canvas passes any DOM assertion."""
    assert canvas_is_drawn(deployed, canvas_id), f"{canvas_id} rendered blank"


@pytest.mark.parametrize("foot_id,must_contain", [
    # The caption must state the >=60-min pooled rate, never a single-bucket
    # rate: the old caption headlined the 80+ bucket, which holds one case.
    ("footEffort", "60 min and over"),
    ("footDelta", "corrections moved"),
    ("footRelease", "lift"),
    ("footDetector", "detector generation is resolved at scan time"),
    ("footDisparity", "escalated"),
])
def test_every_finding_states_a_conclusion(deployed, foot_id, must_contain):
    """A chart without a conclusion is decoration. Each finding must say what it
    means, in words, next to the picture."""
    text = deployed.locator(f"#{foot_id}").inner_text()
    assert must_contain.lower() in text.lower(), f"{foot_id}: {text[:120]!r}"
    assert len(text) > 80, f"{foot_id} conclusion is too thin"


def test_operations_lens_exposes_analyst_telemetry(deployed):
    """The original proposal. It was missing from the portal entirely."""
    deployed.get_by_role("button", name="Operations").click()
    deployed.wait_for_selector("#segs tbody tr")
    assert canvas_is_drawn(deployed, "vizConfidence")
    assert deployed.locator("#telStats .v").count() >= 4
    assert deployed.locator("#segs tbody tr").count() > 5


def test_platform_lens_makes_the_cost_argument(deployed):
    """Integration and learning are the real costs; deployment is not. If that
    argument is missing, the architecture has no justification."""
    deployed.get_by_role("button", name="Platform").click()
    deployed.wait_for_selector("#costTbl tbody tr")
    assert deployed.locator("#costTbl tbody tr").count() >= 5
    nodes = deployed.locator("#platformMap rect, #platformMap path, #platformMap text")
    assert nodes.count() > 40, "platform map did not render"
    body = deployed.locator("#l-platform").inner_text().lower()
    assert "integration" in body and "learning" in body
    assert "once per source system" in body


# ------------------------------------------------------------------ interconnect
def test_ask_box_answers_and_links(deployed):
    """The header Ask box: deterministic answer, provenance line, Open link."""
    deployed.locator("#askIn").fill("any confirmed regressions?")
    deployed.locator("#askBtn").click()
    out = deployed.locator("#askOut")
    expect(out).to_be_visible()
    expect(out).to_contain_text("regression")
    expect(out).to_contain_text("no external LLM")


def test_ask_box_refuses_gracefully(deployed):
    deployed.locator("#askIn").fill("what is for lunch")
    deployed.locator("#askBtn").click()
    out = deployed.locator("#askOut")
    expect(out).to_contain_text("Won't guess")
    assert out.locator(".askTry").count() >= 3, "refusal must offer the vocabulary"


def test_release_row_cross_links_to_filtered_complaints(deployed):
    """The interconnection the spine exists for: release identity -> complaint
    cohort, one click, two departments."""
    deployed.get_by_role("button", name="Engineering").click()
    deployed.wait_for_selector("#rel tr[data-release]")
    deployed.locator('#rel tr[data-release="v4.1.0"]').first.click()
    deployed.wait_for_selector("#compFilter .tag")
    expect(deployed.locator("#l-quality")).to_be_visible()
    expect(deployed.locator("#compFilter")).to_contain_text("v4.1.0")
    assert deployed.locator("#comp tbody tr").count() > 0
    # clear restores the full list
    deployed.locator("#clearComp").click()
    deployed.wait_for_function(
        "() => !document.querySelector('#compFilter .tag')")


def test_hazard_row_filters_complaints(deployed):
    deployed.get_by_role("button", name="Quality").click()
    deployed.wait_for_selector("#haz tr[data-hazard]")
    deployed.locator('#haz tr[data-hazard="H-014"]').click()
    deployed.wait_for_selector("#compFilter .tag")
    expect(deployed.locator("#compFilter")).to_contain_text("H-014")


def test_trace_site_link_opens_the_site_card(deployed):
    deployed.get_by_role("button", name="Quality").click()
    deployed.wait_for_selector('#trace a[href^="#site="]')
    deployed.locator('#trace a[href^="#site="]').first.click()
    deployed.wait_for_selector("#siteCardPanel:visible")
    expect(deployed.locator("#l-field")).to_be_visible()
    assert deployed.locator("#scStats > div").count() >= 6
    assert "#site=" in deployed.url


def test_deep_link_survives_a_cold_load(page):
    """A shared URL must reconstruct the exact view - lens, record, everything.
    That is what makes an analysis referencable in a meeting or an email."""
    page.goto(DEPLOY_BASE + "/#hazard=H-014", wait_until="domcontentloaded")
    page.wait_for_selector('body[data-ready="1"]', state="attached", timeout=45_000)
    page.wait_for_selector("#compFilter .tag")
    expect(page.locator("#l-quality")).to_be_visible()
    expect(page.locator("#compFilter")).to_contain_text("H-014")


# ------------------------------------------------------------------ action layer
def test_actions_lens_runs_the_full_lifecycle(deployed):
    """Sync findings, apply a transition with actor+note, read the audit trail -
    the write path exercised through the real UI against the real deployment."""
    deployed.get_by_role("button", name="Actions").click()
    deployed.locator("#syncBtn").click()
    # WAIT FOR THE SYNC ROUND-TRIP, not merely for cards to exist - cards from the
    # boot-time load are already present. Racing ahead means sync's re-render can
    # land between our clicks: the note gets filled on a node that is about to be
    # detached and the retried click hits the fresh card with an EMPTY note, which
    # is correctly refused - and the test then waits forever for a state change.
    # Local timing hid this; the container's slower volume exposed it.
    deployed.wait_for_selector("#syncOut:has-text('total')")
    card = deployed.locator("#actionList [data-aid]").first

    # a transition without a note must be refused, visibly
    card.locator(".trGo").click()
    expect(card.locator(".trOut")).to_contain_text("refused")

    # State-independent: the store persists across runs, so the first card may be
    # in ANY state. Assert on the SPECIFIC card and the ACTUAL target state we
    # selected, not on "some card becomes acknowledged".
    aid = card.get_attribute("data-aid")
    target = card.locator(".trSel").input_value()
    card.locator(".trNote").fill("triaging from e2e")
    card.locator(".trGo").click()
    deployed.wait_for_function(
        """([aid, target]) => {
            const c = document.querySelector(`#actionList [data-aid="${aid}"]`);
            return c && c.querySelector('.tag').textContent === target;
        }""", arg=[aid, target])

    moved = deployed.locator(f'#actionList [data-aid="{aid}"]')
    moved.locator(".trAudit").click()
    deployed.wait_for_selector(f'#actionList [data-aid="{aid}"] .trTrail .hop')
    trail = moved.locator(".trTrail").inner_text()
    assert "triaging from e2e" in trail, "the transition note must appear in the audit"


def test_signing_flow_verifies_then_records(deployed):
    deployed.get_by_role("button", name="Evidence").click()
    deployed.wait_for_selector("#packTrace .hop")
    deployed.locator("#signActor").fill("andrii")
    deployed.locator("#signRole").fill("quality engineer")
    deployed.locator("#signNote").fill("e2e review")
    deployed.locator("#signBtn").click()
    deployed.wait_for_selector("#signVerdict")
    expect(deployed.locator("#signVerdict")).to_contain_text("Signed")
    deployed.wait_for_selector("#signedTbl tbody tr")
    expect(deployed.locator("#signedTbl tbody tr").first).to_contain_text("verified")


def test_briefing_export_link_serves_the_artifact(deployed):
    resp = deployed.request.get(DEPLOY_BASE + "/api/briefing?download=true")
    assert resp.status == 200
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert "Findings requiring action" in resp.text()


# ------------------------------------------------------------------ business processes
def test_shadow_simulator_guard_tradeoff_is_live(deployed):
    """The policy decision surface: dragging the guard band must move volume and
    harm in opposite directions, live, from the deployed warehouse."""
    deployed.locator('#nav button[data-k="ops"]').click()
    deployed.wait_for_selector("#shStats .v")

    def stat(i):
        # Intl.NumberFormat separates thousands with U+00A0 in some locales;
        # keep only digits rather than enumerating whitespace variants.
        return int(re.sub(r"\D", "",
                          deployed.locator("#shStats .v").nth(i).inner_text()))
    harm = lambda: stat(4)   # noqa: E731
    auto = lambda: stat(0)   # noqa: E731

    deployed.locator("#shGuard").evaluate(
        "(el)=>{el.value='0';el.dispatchEvent(new Event('input'))}")
    deployed.wait_for_function(
        "() => document.querySelectorAll('#shLedger tbody tr').length > 20")
    h0, a0 = harm(), auto()

    deployed.locator("#shGuard").evaluate(
        "(el)=>{el.value='0.05';el.dispatchEvent(new Event('input'))}")
    deployed.wait_for_function(
        "() => document.querySelectorAll('#shLedger tbody tr').length < 10")
    h5, a5 = harm(), auto()

    assert h5 < h0, "guard band must reduce changed answers"
    assert a5 < a0, "guard band must cost some volume"
    assert deployed.locator("#shCurve tbody tr").count() >= 5
    expect(deployed.locator("#shFraming")).to_contain_text("Retrospective replay")


def test_investigation_process_end_to_end_in_the_browser(deployed):
    """The modelled business process, driven through the real UI: open an
    investigation, watch a thin rationale refused, decide (late-flagged), seal."""
    deployed.locator('#nav button[data-k="quality"]').click()
    deployed.wait_for_selector("#invBoard tbody tr")
    expect(deployed.locator("#invToday")).to_contain_text("deadline 30 days")

    openable = deployed.locator("#invBoard .invOpen")
    if openable.count() == 0:
        pytest.skip("no complaint left in 'received' on this persistent store")
    row = deployed.locator("#invBoard tr[data-inv]").filter(
        has=deployed.locator(".invOpen")).first
    row.locator(".invOpen").click()
    deployed.wait_for_selector("#invDrawer #invDecide")
    drawer = deployed.locator("#invDrawer")
    expect(drawer).to_contain_text("Chronology")
    expect(drawer).to_contain_text("MDR assessment")
    expect(drawer).to_contain_text("Isolated or systemic")

    deployed.locator("#invRationale").fill("no")
    deployed.locator("#invDecide").click()
    expect(deployed.locator("#invOut")).to_contain_text("refused")

    deployed.locator("#invRationale").fill(
        "Substantive rationale recorded from the e2e run: mechanism present, "
        "documented per 820.198.")
    deployed.locator("#invDecide").click()
    expect(deployed.locator("#invOut")).to_contain_text("decided")
    # fixture complaints are historic, so the clock has always run out
    expect(deployed.locator("#invOut")).to_contain_text("LATE")

    deployed.locator("#invClose").click()
    # Cycle-1 F4/F2: sealing transitions the drawer to the sealed-record view
    deployed.wait_for_selector(
        '#invDrawer:has-text("Sealed investigation record")')
    assert re.search(r"[0-9a-f]{64}",
                     deployed.locator("#invDrawer").inner_text())


# ------------------------------------------------------------------ UX cycle 1
def test_f1_policy_brief_is_satisfiable_with_the_tolerance_dial(deployed):
    """Regression for cycle-0 F1 (sev 4): with tolerance raised, at least one
    guard row must satisfy the benchmark brief (>=600h returned, FN<=5)."""
    deployed.locator('#nav button[data-k="ops"]').click()
    deployed.wait_for_selector("#shTol")
    # Wait on the DATA, not the readout: shTolOut updates synchronously while
    # the curve re-renders only after the fetch resolves - waiting on the label
    # reads the stale 8% curve (a race this test itself had on first run).
    before = deployed.locator("#shCurve tbody tr").first.inner_text()
    deployed.locator("#shTol").evaluate(
        "(el)=>{el.value='0.12';el.dispatchEvent(new Event('input'))}")
    deployed.wait_for_function(
        """(prev) => {
            const r = document.querySelector('#shCurve tbody tr');
            return r && r.innerText !== prev;
        }""", arg=before)
    rows = deployed.locator("#shCurve tbody tr")
    satisfiable = False
    for i in range(rows.count()):
        cells = rows.nth(i).locator("td")
        hours = int(re.sub(r"\D", "", cells.nth(2).inner_text()) or 0)
        fn = int(re.sub(r"\D", "", cells.nth(4).inner_text()) or 0)
        if hours >= 600 and fn <= 5:
            satisfiable = True
    assert satisfiable, "T5 brief unsatisfiable even with the tolerance dial"
    # F5 bundle: the FTE assumptions must be visible, not just in the payload
    expect(deployed.locator("#shStats")).to_contain_text("productive")


def test_f3_board_defaults_to_urgency_triage(deployed):
    """Regression for F3 (sev 3): default view is Overdue, most-urgent first,
    with counted quick filters."""
    deployed.locator('#nav button[data-k="quality"]').click()
    deployed.wait_for_selector("#invFilters [data-f]")
    pressed = deployed.locator('#invFilters [data-f][aria-pressed="true"]')
    assert pressed.get_attribute("data-f") == "overdue"
    for f in ("overdue", "actionable", "closed", "all"):
        label = deployed.locator(f'#invFilters [data-f="{f}"]').inner_text()
        assert re.search(r"\(\d+\)", label), f"filter {f} lacks a count"
    clocks = [int(re.sub(r"[^\d-]", "", c.inner_text().replace("OVERDUE", "")))
              for c in deployed.locator(
                  "#invBoard tr[data-inv] td:nth-child(4)").all()[:8]]
    assert clocks == sorted(clocks), f"not urgency-sorted: {clocks}"


def test_f4_sealed_investigation_offers_no_decision_controls(deployed):
    """Regression for F4 (sev 3): a closed investigation renders the record view
    with no live decision controls - prevention, not error messages."""
    deployed.locator('#nav button[data-k="quality"]').click()
    deployed.wait_for_selector("#invFilters [data-f]")
    deployed.locator('#invFilters [data-f="closed"]').click()
    rows = deployed.locator("#invBoard tr[data-inv]")
    if rows.count() == 0:
        pytest.skip("no closed investigation in state")
    assert rows.first.locator(".invView").inner_text() == "Record"
    rows.first.locator(".invView").click()
    deployed.wait_for_selector(
        '#invDrawer:has-text("Sealed investigation record")')
    assert deployed.locator("#invDrawer #invDecide").count() == 0
    assert deployed.locator("#invDrawer #invClose").count() == 0


def test_f2_sealed_record_reachable_and_verified_posthoc(deployed):
    """Regression for F2 (sev 4): manifest hash, verification status and the
    as-sealed audit trail reachable from the board at any later time."""
    deployed.locator('#nav button[data-k="quality"]').click()
    deployed.wait_for_selector("#invFilters [data-f]")
    deployed.locator('#invFilters [data-f="closed"]').click()
    rows = deployed.locator("#invBoard tr[data-inv]")
    if rows.count() == 0:
        pytest.skip("no closed investigation in state")
    rows.first.locator(".invView").click()
    deployed.wait_for_selector(
        '#invDrawer:has-text("Sealed investigation record")')
    body = deployed.locator("#invDrawer").inner_text()
    assert re.search(r"[0-9a-f]{64}", body), "manifest hash not shown"
    assert "verified" in body
    assert "\u2192" in body or "->" in body, "as-sealed audit trail missing"
    assert "#investigation=" in deployed.url, "deep link not set (F9)"
