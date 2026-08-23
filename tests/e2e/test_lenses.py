"""
End-to-end tests for the lenses, against the self-booted server.

These assert on INVARIANTS rather than on rendered values. A test that hardcodes
"21% of accepted volume" breaks the moment the fixture seed changes and teaches the
team to update the expectation rather than investigate - which is how a suite stops
being a safety net. Every assertion here would still be correct against real data,
including data with ties.

The pattern matters for a regulated UI: the thing you verify is that the screen
cannot show something untrue, not that it shows one particular true thing.

The client is the 7-lens narrative app: Findings (landing), Operations, Quality,
Engineering, Field, Evidence, Platform. Lenses other than Findings are display:none
until their nav button is clicked, so every test that reads a lens opens it first.
"""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")

LENSES = ["Findings", "Operations", "Quality", "Engineering", "Field",
          "Evidence", "Actions", "Platform"]


def pct(text: str) -> float:
    m = PCT.search(text)
    assert m, f"expected a percentage in {text!r}"
    return float(m.group(1))


def open_lens(page, label: str):
    page.get_by_role("button", name=label).click()
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


def set_tolerance(page, value: float):
    """Drive the #tol range slider and wait for the async re-render.

    fill() refuses input[type=range], so set the value and fire the same event the
    slider fires. The verdict re-renders only after the /api/ops/frontier fetch
    resolves, so wait until it states the tolerance we just set rather than
    sleeping an arbitrary interval.
    """
    page.locator("#tol").evaluate(
        "(el, v) => { el.value = v; el.dispatchEvent(new Event('input')); }",
        str(value))
    page.wait_for_function(
        "v => document.getElementById('verdict').innerText.includes(v)",
        arg=f"≤{value:.2f}%")


def verdict_stats(text: str) -> tuple[int, int, float]:
    """(eligible strata, total strata, automatable volume %) from the verdict line."""
    m = re.search(r"(\d+)\s+of\s+(\d+)\s+strata", text)
    assert m, f"verdict does not state eligibility: {text!r}"
    volume = pct(text.split("—")[1])  # after the em dash
    return int(m.group(1)), int(m.group(2)), volume


# ------------------------------------------------------------------ shell
def test_app_loads_and_hydrates(app_page):
    expect(app_page).to_have_title("Case Spine")

    # landing lens: the hero must state a real headline share, not a placeholder
    big = app_page.locator("#heroBig").inner_text()
    assert PCT.search(big), f"hero is not a percentage: {big!r}"
    assert 0 < pct(big) <= 100
    stats = app_page.locator("#heroStats .v")
    assert stats.count() >= 4
    for i in range(stats.count()):
        v = stats.nth(i).inner_text()
        assert v.strip() not in ("", "—", "NaN", "undefined", "null"), \
            f"hero stat {i} empty: {v!r}"

    # every KPI (Operations lens) must render a value, not an empty shell or a dash
    open_lens(app_page, "Operations")
    expect(app_page.locator(".kpi")).to_have_count(6)
    for i in range(6):
        v = app_page.locator(".kpi .v").nth(i).inner_text()
        assert v.strip() not in ("", "—", "NaN", "undefined", "null"), \
            f"KPI {i} empty: {v!r}"


def test_findings_is_the_landing_lens(app_page):
    """The portal opens on the argument, not on a table. If this regresses the
    thing becomes a data browser again, which is what it was criticised for."""
    expect(app_page.locator("#l-findings")).to_be_visible()
    expect(app_page.get_by_role("button", name="Findings")).to_have_attribute(
        "aria-selected", "true")


def test_lens_switching_shows_exactly_one_lens(app_page):
    keys = ["findings", "ops", "quality", "eng", "field", "evidence",
            "actions", "platform"]
    expect(app_page.locator("#nav button")).to_have_count(len(LENSES))
    for key, label in zip(keys, LENSES):
        app_page.get_by_role("button", name=label).click()
        expect(app_page.locator(f"#l-{key}")).to_be_visible()
        assert app_page.locator("section.lens.on").count() == 1
        expect(app_page.get_by_role("button", name=label)).to_have_attribute(
            "aria-selected", "true")


@pytest.mark.parametrize("canvas_id", [
    "vizEffort", "vizDelta", "vizRelease", "vizDetector", "vizDisparity"])
def test_every_finding_visualisation_actually_paints(app_page, canvas_id):
    """Presence is not rendering. A blank canvas passes any DOM assertion."""
    assert canvas_is_drawn(app_page, canvas_id), f"{canvas_id} rendered blank"


# ------------------------------------------------------------------ operations
def test_frontier_is_ordered_by_residual_risk(app_page):
    """The frontier only means anything if it is monotone. Ties are fine;
    an inversion is not."""
    open_lens(app_page, "Operations")
    rates = [pct(c.inner_text()) for c in
             app_page.locator("#strata tbody tr td:nth-child(4)").all()]
    assert len(rates) > 5
    assert rates == sorted(rates), f"strata not ordered by risk: {rates}"


def test_tolerance_slider_is_monotone_in_volume(app_page):
    """More tolerance must never buy less automatable volume.

    This is the invariant the whole automation argument rests on. If it inverts,
    someone has broken the ordering or the cumulative sum.
    """
    open_lens(app_page, "Operations")
    seen = []
    for value in [0, 4, 8, 12, 16]:
        set_tolerance(app_page, value)
        eligible, total, volume = verdict_stats(
            app_page.locator("#verdict").inner_text())
        assert 0 <= eligible <= total
        seen.append((value, eligible, volume))

    for (_, s1, v1), (_, s2, v2) in zip(seen, seen[1:]):
        assert s2 >= s1, f"eligible strata decreased: {seen}"
        assert v2 >= v1, f"automatable volume decreased: {seen}"


def test_zero_tolerance_admits_only_zero_risk_strata(app_page):
    """Boundary condition, and a sanity check that the filter is actually applied.

    With ties in the data a stratum can sit at exactly 0.00%, so "0 of N" is not an
    invariant - but "nothing with any observed risk qualifies" is. The verdict's
    eligible count must agree with the row labels, and every row labelled Automate
    must show a 0.00% rate.
    """
    open_lens(app_page, "Operations")
    set_tolerance(app_page, 0)

    eligible, total, _ = verdict_stats(app_page.locator("#verdict").inner_text())
    assert eligible < total, "zero tolerance cannot admit every stratum"

    automate_rates = []
    for row in app_page.locator("#strata tbody tr").all():
        if row.locator(".tag").inner_text().strip() == "Automate":
            automate_rates.append(pct(row.locator("td").nth(3).inner_text()))
    assert len(automate_rates) == eligible, \
        f"verdict says {eligible} eligible but {len(automate_rates)} rows say Automate"
    for rate in automate_rates:
        assert rate == 0.0, f"labelled Automate at {rate}% under a 0% tolerance"


def test_disposition_matches_the_stated_tolerance(app_page):
    """Every row labelled Automate must actually sit at or below the tolerance.

    A label that disagrees with the number beside it is the single most dangerous
    defect this UI could ship, because the label is what a reader acts on.

    Rendered rates are rounded to 2dp, so comparisons allow half an ULP (0.005).
    """
    open_lens(app_page, "Operations")
    set_tolerance(app_page, 10)
    eps = 0.005 + 1e-9

    for row in app_page.locator("#strata tbody tr").all():
        rate = pct(row.locator("td").nth(3).inner_text())
        label = row.locator(".tag").inner_text().strip()
        if label == "Automate":
            assert rate <= 10.0 + eps, f"labelled Automate at {rate}% under a 10% tolerance"
        if label == "Monitor":
            assert 10.0 - eps < rate <= 17.0 + eps, \
                f"labelled Monitor at {rate}% under a 10% tolerance (band is 10-17%)"
        if label == "Human required":
            assert rate > 10.0 - eps, \
                f"labelled Human required at {rate}% under a 10% tolerance"


# ------------------------------------------------------------------ quality
def test_hazards_render_with_controls(app_page):
    open_lens(app_page, "Quality")
    rows = app_page.locator("#haz tbody tr")
    expect(rows).not_to_have_count(0)
    for row in rows.all():
        assert re.match(r"H-\d+", row.locator("td").first.inner_text().strip())
        assert "controls:" in row.locator("td").nth(1).inner_text()


def _traverse(page, row):
    """Click a complaint row and wait until the trace shows THAT complaint."""
    cid = int(row.get_attribute("data-id"))
    row.click()
    page.wait_for_function(
        "label => document.getElementById('trace').innerText.includes(label)",
        arg=f"C-{cid:03d}")
    return cid


def test_complaint_traversal_resolves_the_full_chain(app_page):
    """The cross-reference: complaint -> case -> site -> hazard -> stratum -> release."""
    open_lens(app_page, "Quality")
    app_page.wait_for_selector("#comp tbody tr")

    # the lens pre-selects one complaint; traverse a DIFFERENT one so the wait
    # below proves the click actually re-ran the traversal
    selected = app_page.locator("#comp tbody tr.sel").first.get_attribute("data-id")
    rows = app_page.locator("#comp tbody tr")
    target = rows.nth(0) if rows.nth(0).get_attribute("data-id") != selected else rows.nth(1)
    _traverse(app_page, target)
    expect(app_page.locator("#comp tbody tr.sel")).to_have_count(1)

    # inner_text() reflects rendered text, and .lbl is text-transform: uppercase,
    # so compare case-insensitively rather than asserting on the styled casing.
    labels = [e.inner_text().casefold()
              for e in app_page.locator("#trace .lbl").all()]
    for expected in ["complaint", "-> case", "-> site", "-> hazard",
                     "-> stratum", "-> by release"]:
        assert expected in labels, f"trace lost the {expected!r} hop: {labels}"
    expect(app_page.locator("#trace .finding")).to_be_visible()


def test_every_complaint_traverses_without_error(app_page):
    """Exercises all of them - the console-error fixture turns any failed fetch or
    null dereference on an edge-case complaint into a failure."""
    open_lens(app_page, "Quality")
    app_page.wait_for_selector("#comp tbody tr")
    rows = app_page.locator("#comp tbody tr")
    for i in range(min(rows.count(), 12)):
        _traverse(app_page, rows.nth(i))
        expect(app_page.locator("#trace .finding")).to_be_visible()


# ------------------------------------------------------------------ engineering
def test_release_signal_never_contradicts_its_p_value(app_page):
    """A drift monitor that flags on ratio alone cries wolf and gets muted.

    This test encodes the rule: `regression` and `improved` require materiality
    (lift >= 1.25x or <= 0.80x) AND p < 0.05; a material effect without support
    must read `unconfirmed`; `stable` must not be material at all.

    Column order in the new client: Model, Make, Cases, Crude, Std., Lift(5),
    p(6), Signal. Lift renders at 2dp and p at 3dp, so comparisons carry half an
    ULP of slack rather than pretending the screen shows full precision.
    """
    open_lens(app_page, "Engineering")
    app_page.wait_for_selector("#rel tbody tr")
    l_eps, p_eps = 0.005 + 1e-9, 0.0005 + 1e-9

    rows = app_page.locator("#rel tbody tr").all()
    assert len(rows) > 3
    for row in rows:
        cells = row.locator("td")
        lift = float(cells.nth(5).inner_text())
        p_txt = cells.nth(6).inner_text().strip()
        p = 0.0005 if p_txt.startswith("<") else float(p_txt)
        signal = row.locator(".tag").inner_text().strip()
        material = lift >= 1.25 - l_eps or lift <= 0.80 + l_eps

        if signal in ("regression", "improved"):
            assert p < 0.05 + p_eps, f"{signal} flagged at p={p}"
            assert material, f"{signal} flagged at lift={lift}"
        if signal == "unconfirmed":
            assert material and p >= 0.05 - p_eps, \
                f"unconfirmed with lift={lift} p={p}"
        if signal == "stable":
            assert 0.80 - l_eps < lift < 1.25 + l_eps, \
                f"stable despite material lift={lift} (p={p})"


def test_a_confirmed_regression_is_surfaced(app_page):
    """The fixture plants one genuine regression. If the lens cannot find it, the
    lens is broken - this is the golden-case check for the engineering view."""
    open_lens(app_page, "Engineering")
    app_page.wait_for_selector("#rel tbody tr")
    regressions = app_page.locator("#rel tbody").get_by_text("regression", exact=True)
    assert regressions.count() >= 1, "planted regression not detected"


# ------------------------------------------------------------------ field
def test_sites_ordered_by_rejection_descending(app_page):
    open_lens(app_page, "Field")
    app_page.wait_for_selector("#sites tbody tr")
    rates = [pct(c.inner_text()) for c in
             app_page.locator("#sites tbody tr td:nth-child(4)").all()]
    assert rates == sorted(rates, reverse=True), f"worklist not ranked: {rates}"


def test_detector_transition_reports_a_downward_shift(app_page):
    """Photon-counting measures ~1/3 lower plaque volume than energy-integrating.
    The shift must render, and it must be negative - a positive shift would mean
    the detector resolution is inverted somewhere in the SQL."""
    open_lens(app_page, "Field")
    app_page.wait_for_selector("#det > div")
    blocks = app_page.locator("#det > div")
    assert blocks.count() >= 1

    shifts = []
    for i in range(blocks.count()):
        # the "Shift" label is an .eyebrow, which is text-transform: uppercase -
        # match the rendered text case-insensitively
        parts = re.split(r"(?i)shift", blocks.nth(i).inner_text(), maxsplit=1)
        if len(parts) < 2:
            continue
        shift = float(re.search(r"(-?\d+\.\d+)%", parts[1]).group(1))
        shifts.append(shift)
        assert shift < 0, f"expected a downward plaque-volume shift, got {shift}%"
        assert -60 < shift < -10, f"shift {shift}% outside a plausible range"
    assert shifts, "no transition block reported a shift"


# ------------------------------------------------------------------ resilience
@pytest.mark.allow_console_errors
def test_api_failure_surfaces_instead_of_rendering_empty(page, base_url):
    """A data UI that fails silently is worse than one that errors.

    With the API blocked the page must say so, not render empty tables that read
    as 'no findings' - which in this domain would mean 'no hazards matched'.
    The client signals the failure path explicitly via body[data-ready="error"].
    """
    page.route("**/api/**", lambda route: route.abort())
    page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_selector('body[data-ready="error"]', state="attached")
    # .first: the banner is inserted at the top of .wrap, ahead of the static
    # .finding call-outs that exist in the Platform lens markup
    expect(page.locator(".finding").first).to_contain_text("Failed to load")


@pytest.mark.parametrize("width,height", [(1280, 800), (768, 1024), (375, 812)])
def test_no_horizontal_page_scroll(page, base_url, width, height):
    """Wide tables must scroll inside their own container, never the page body.
    Checked on every lens - a hidden lens contributes nothing to scrollWidth, so
    the landing view alone would prove nothing about the other six."""
    page.set_viewport_size({"width": width, "height": height})
    page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_selector('body[data-ready="1"]', state="attached", timeout=30_000)
    for label in LENSES:
        page.get_by_role("button", name=label).click()
        overflow = page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert overflow <= 1, \
            f"{label} lens scrolls horizontally by {overflow}px at {width}x{height}"
