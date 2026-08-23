"""
E2E fixtures.

Starts the real API against the real DuckDB build and tears it down after the
session. Nothing is mocked - these tests exercise SQL, the metric layer, the HTTP
API and the browser in one pass, which is the only way to catch the class of defect
where each layer is individually correct and the seam between two of them is not.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "spine.duckdb"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url() -> str:
    """Boot the API on a free port; wait for readiness; kill it afterwards."""
    if not DB.exists():
        pytest.skip("spine not built - run `python -m spine.generate && python -m spine.build`")

    port = int(os.environ.get("E2E_PORT") or _free_port())
    url = f"http://127.0.0.1:{port}"

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )

    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
            pytest.fail(f"server exited early:\n{out}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4):
                break
        except OSError:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("server did not become ready within 30s")

    yield url

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Inject basic-auth credentials into every pytest-playwright context when a
    remote deploy behind Caddy is the target (DEPLOY_AUTH="user:pass")."""
    auth = os.environ.get("DEPLOY_AUTH", "")
    if auth and ":" in auth:
        user, password = auth.split(":", 1)
        return {**browser_context_args,
                "http_credentials": {"username": user, "password": password}}
    return browser_context_args


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "allow_console_errors: test deliberately provokes browser errors "
        "(e.g. simulated API failure); exempt it from the console-error guard")


@pytest.fixture(autouse=True)
def fail_on_console_error(page, request):
    """Any uncaught page error or console error fails the test.

    A data-driven UI degrades silently by default - a failed fetch renders an empty
    table that looks like "no results". Promoting console errors to test failures is
    what stops a broken lens from passing a green suite.

    Tests that provoke failure on purpose opt out with
    @pytest.mark.allow_console_errors, so the exemption is explicit and greppable
    rather than a blanket loosening of the rule.
    """
    if request.node.get_closest_marker("allow_console_errors"):
        yield
        return

    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}")
            if m.type == "error" else None)
    yield
    assert not errors, "browser reported errors:\n  " + "\n  ".join(errors)


@pytest.fixture
def app_page(page, base_url):
    """Loaded app with all lenses hydrated.

    NOT networkidle - the page pulls webfonts and fires a dozen API calls, and the
    network may never go quiet. And NOT `#strata` - that table lives in the
    Operations lens, which is display:none now that Findings is the landing view,
    so the default state="visible" wait times out on a perfectly healthy page.

    The client sets body[data-ready="1"] only after every lens has rendered AND
    redraw() has painted the canvases (data-ready="error" on failure). Wait on that
    explicit contract instead of inferring readiness from incidental DOM.

    Deliberately function-scoped, unlike test_deployed.py's module-scoped twin: the
    autouse console-error guard above listens on this test's own `page`, and a
    shared page would silently escape it. Against the in-process server on
    localhost the per-test hydration is cheap enough to pay for that guarantee.
    """
    page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_selector('body[data-ready="1"]', state="attached", timeout=30_000)
    return page
