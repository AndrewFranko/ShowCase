"""Share one hydrated page across the deployed suite, and make the concurrency
test actually concurrent."""
import pathlib

p = pathlib.Path(__file__).resolve().parent.parent / "tests" / "e2e" / "test_deployed.py"
s = p.read_text(encoding="utf-8")
before = s

OLD_FIXTURE = '''@pytest.fixture
def deployed(page):
    """Load the app and wait until it has actually hydrated.'''

NEW_FIXTURE = '''@pytest.fixture(scope="module")
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
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.goto(DEPLOY_BASE, wait_until="domcontentloaded")
    pg.wait_for_selector('body[data-ready="1"]', state="attached", timeout=45_000)
    yield pg
    ctx.close()


@pytest.fixture
def deployed(_hydrated):
    """Hand each test the shared page, reset to the landing lens."""
    _hydrated.get_by_role("button", name="Findings").click()
    return _hydrated


@pytest.fixture
def _retired_deployed(page):
    """Load the app and wait until it has actually hydrated.'''

assert OLD_FIXTURE in s, "fixture anchor not found"
s = s.replace(OLD_FIXTURE, NEW_FIXTURE, 1)

OLD_CONC = '''def test_concurrent_requests_do_not_break_the_read_only_warehouse(deployed):
    """Multiple uvicorn workers each open the same read-only DuckDB file. A lock
    or handle problem shows up under concurrency and never in a single request."""
    responses = [deployed.request.get(f"{DEPLOY_BASE}/api/quality/disparity")
                 for _ in range(12)]
    assert all(r.status == 200 for r in responses), \\
        [r.status for r in responses if r.status != 200]'''

NEW_CONC = '''def test_concurrent_requests_do_not_break_the_read_only_warehouse():
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
    assert all(s == 200 for s in statuses), statuses'''

assert OLD_CONC in s, "concurrency anchor not found"
s = s.replace(OLD_CONC, NEW_CONC, 1)

p.write_text(s, encoding="utf-8")
print(f"patched {len(before)} -> {len(s)} bytes")
for marker in ['scope="module"', "_hydrated", "ThreadPoolExecutor", "_retired_deployed"]:
    print(f"  {'ok ' if marker in s else 'MISSING'} {marker}")
