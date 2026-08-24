"""
Local deploy.

Production-shaped, not a dev server: no --reload, multiple workers, a fixed port,
and startup is gated on the API actually answering rather than on the process
existing. `docker compose up` is the containerised equivalent; this path exists so
the stack can be deployed and exercised without a running Docker daemon.

    python -m deploy.local_deploy up        # build spine, start, wait for healthy
    python -m deploy.local_deploy status
    python -m deploy.local_deploy down

Health is /api/overview rather than a bare socket check, because a socket says the
process is alive while /api/overview says the DuckDB connection and the metric
layer both work. Deploys that report green on a socket are how a broken build
reaches an audience.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "deploy" / ".deploy-state.json"
DB = ROOT / "data" / "spine.duckdb"

HOST = os.environ.get("DEPLOY_HOST", "127.0.0.1")
PORT = int(os.environ.get("DEPLOY_PORT", "8090"))
# Multi-worker uvicorn hands the listening socket to child processes; on Windows
# that handoff is unreliable (workers intermittently wedge with WinError 10022 in
# the log, and requests round-robined to the wedged worker hang forever - which
# surfaced as the client intermittently never reaching data-ready). Linux and the
# container keep 2 workers; Windows defaults to 1 unless explicitly overridden.
import sys as _sys
WORKERS = int(os.environ.get("DEPLOY_WORKERS",
                             "1" if _sys.platform == "win32" else "2"))
BASE = f"http://{HOST}:{PORT}"

# Every route the client depends on. A deploy is not "up" because the index page
# renders - it is up when every lens the page will call actually answers.
SMOKE_ROUTES = [
    "/",
    "/api/overview",
    "/api/ops/frontier?tolerance=0.08",
    "/api/quality/hazards",
    "/api/quality/disparity",
    "/api/quality/complaints",
    "/api/engineering/releases",
    "/api/field/sites",
    "/api/field/conformance",
    "/api/field/detector-transitions",
    "/api/evidence/frontier",
    "/api/evidence/disparity",
]


def _get(path: str, timeout: float = 8.0):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "deploy-smoke"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def build_spine() -> None:
    if DB.exists():
        print(f"  spine present: {DB}")
        return
    print("  building spine (fixture + models + data tests)")
    for mod in ("spine.generate", "spine.build"):
        args = [sys.executable, "-m", mod] + (["--check"] if mod == "spine.build" else [])
        r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout[-2000:], r.stderr[-2000:])
            sys.exit(f"spine build failed at {mod}")


def up() -> int:
    print(f"deploying to {BASE}  ({WORKERS} workers, no reload)")
    build_spine()

    # Refuse to adopt a server we did not start.
    #
    # This is the defect that hid everything else. `up` previously health-checked
    # the port, saw a 200, and reported "deploy healthy" - against an orphaned
    # uvicorn from an earlier cycle that had imported app.main BEFORE the last edit.
    # Python caches modules in memory, so that orphan served stale code
    # indefinitely while every smoke test and browser test passed green against it.
    #
    # A deploy that adopts a stranger's process is worse than a deploy that fails:
    # failure is visible. Verify the port is either ours or free, and refuse loudly
    # otherwise.
    already_answering = True
    try:
        _get("/api/overview", timeout=2)
    except Exception:                                              # noqa: BLE001
        already_answering = False

    if already_answering:
        if STATE.exists():
            print("  already running (state file matches a live server)")
            return 0
        print(f"\n  REFUSING TO DEPLOY: something is already serving on {BASE} and it\n"
              f"  is not ours - there is no deploy state file. It may be an orphan\n"
              f"  running stale code, which would silently pass every test.\n\n"
              f"  Reclaim it:  python -m deploy.local_deploy down\n"
              f"  Or pick another port:  DEPLOY_PORT=8091 python -m deploy.local_deploy up\n")
        return 2

    log = ROOT / "deploy" / "server.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    handle = log.open("w", encoding="utf-8")

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", HOST, "--port", str(PORT),
         "--workers", str(WORKERS), "--log-level", "info"],
        cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT,
        # POSIX: own session/process group, so `down` can killpg the server tree
        # without touching whoever launched us (in GitHub Actions the inherited
        # pgid is the runner's own - killpg there SIGTERMs the entire runner).
        start_new_session=(sys.platform != "win32"),
    )
    STATE.write_text(json.dumps({"pid": proc.pid, "port": PORT, "base": BASE}),
                     encoding="utf-8")

    print("  waiting for health", end="", flush=True)
    deadline = time.time() + 60
    while time.time() < deadline:
        if proc.poll() is not None:
            print("\n  server exited during startup:\n")
            print(log.read_text(encoding="utf-8")[-3000:])
            return 1
        try:
            code, _ = _get("/api/overview", timeout=3)
            if code == 200:
                print(f"  healthy after {60 - int(deadline - time.time())}s")
                break
        except (urllib.error.URLError, OSError):
            pass
        print(".", end="", flush=True)
        time.sleep(1.0)
    else:
        print("\n  never became healthy")
        return 1

    print("  smoke-testing every route the client calls")
    failures = []
    for route in SMOKE_ROUTES:
        try:
            code, body = _get(route)
            ok = code == 200 and len(body) > 0
            print(f"    [{'ok ' if ok else 'FAIL'}] {code} {len(body):>8,}b  {route}")
            if not ok:
                failures.append(route)
        except Exception as exc:                                  # noqa: BLE001
            print(f"    [FAIL] {type(exc).__name__}  {route}")
            failures.append(route)

    if failures:
        print(f"\n  DEPLOY DEGRADED - {len(failures)} route(s) failing: {failures}")
        return 1
    print(f"\n  deploy healthy: {BASE}  (pid {proc.pid}, log {log})")
    return 0


def status(quiet: bool = False) -> int:
    if not STATE.exists():
        if not quiet:
            print("not deployed")
        return 1
    try:
        code, body = _get("/api/overview", timeout=4)
        payload = json.loads(body)
        if not quiet:
            print(f"up  {BASE}  cases={payload['cases']}  "
                  f"actionable={payload['actionable_correction_rate']:.2%}")
        return 0 if code == 200 else 1
    except Exception as exc:                                       # noqa: BLE001
        if not quiet:
            print(f"down ({type(exc).__name__})")
        return 1


def pids_on_port(port: int = PORT) -> list[int]:
    """Every process listening on the port, regardless of who started it.

    Killing only the PID we recorded is not enough. Orphans accumulate: a deploy
    that fails to tear down cleanly leaves workers holding the socket, the next
    `up` sees a healthy /api/overview and reports success, and the stack quietly
    keeps serving the PREVIOUS build. That happened here - three orphaned listeners
    were serving code two edits old while every smoke test and browser test passed
    green against them.

    Reclaiming the port by port, not by remembered PID, is the only version of
    `down` that is actually idempotent.
    """
    found: set[int] = set()
    try:
        if sys.platform == "win32":
            out = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                                 capture_output=True, text=True, timeout=15).stdout
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[0] == "TCP" \
                        and parts[1].endswith(f":{port}") and parts[3] == "LISTENING":
                    with contextlib.suppress(ValueError):
                        found.add(int(parts[4]))
        else:
            out = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                                 capture_output=True, text=True, timeout=15).stdout
            for line in out.split():
                with contextlib.suppress(ValueError):
                    found.add(int(line))
    except (OSError, subprocess.SubprocessError):
        pass
    return sorted(found)


def kill_pid_tree(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, text=True)
    else:
        # Guard: a listener that predates `up` (an orphan, or a server started by
        # hand) may share OUR process group; killpg would then take down this
        # process and everything above it. In GitHub Actions that meant SIGTERMing
        # the runner itself (exit 143, "runner has received a shutdown signal").
        try:
            pgid = os.getpgid(pid)
            if pgid != os.getpgid(0):
                os.killpg(pgid, signal.SIGTERM)
                return
        except OSError:
            pass
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)


def _port_is_free(timeout: float = 20.0) -> bool:
    """Wait until nothing answers on the port.

    Found by running a down/up cycle back to back: the new server started while the
    old workers were still shutting down, and the browser suite hit a half-started
    deployment. Two tests errored, both times in fixture setup, and it looked like
    flake. It was not - `down` returning before the port was actually released is a
    real defect, and one that would be far more confusing in CI.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            _get("/api/overview", timeout=1.5)
        except Exception:                                          # noqa: BLE001
            return True
        time.sleep(0.4)
    return False


def down() -> int:
    # Reclaim by PORT, not by remembered PID. uvicorn --workers spawns children,
    # and any deploy that did not tear down cleanly leaves orphans holding the
    # socket. See pids_on_port for why that is worse than it sounds.
    targets = pids_on_port()
    recorded = None
    if STATE.exists():
        recorded = json.loads(STATE.read_text(encoding="utf-8")).get("pid")
        if recorded and recorded not in targets:
            targets.append(recorded)

    if not targets:
        print("not deployed")
        STATE.unlink(missing_ok=True)
        return 0

    print(f"  terminating {len(targets)} listener(s) on port {PORT}: {targets}")
    for pid in targets:
        kill_pid_tree(pid)
    STATE.unlink(missing_ok=True)

    if _port_is_free():
        print(f"stopped pid {pid}; port {PORT} released")
        return 0
    print(f"stopped pid {pid} but port {PORT} is still answering after 20s")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["up", "status", "down"])
    args = ap.parse_args()
    return {"up": up, "status": lambda: status(), "down": down}[args.action]()


if __name__ == "__main__":
    raise SystemExit(main())
