# Iteration 06 — Local deploy, driven for real

## Business analysis

Two gaps carried over from the first five iterations:

1. **The client was five iterations behind the API.** Disparity, conformance,
   standardised rates and evidence packs were all live on the server and unreachable in the
   browser. So the 17-test browser suite was verifying a stale surface, which quietly
   undercut the strongest claim made about it.
2. **Nothing had been deployed.** Every test ran against a server the test process started
   itself, sharing its interpreter, imports and working directory. Defects that only appear
   across a process boundary were invisible by construction.

## Architecture

**Container path** — `Dockerfile` (multi-stage, non-root uid 10001, read-only rootfs, dropped
capabilities, `/api/overview` as the healthcheck) and `docker-compose.yml`. The spine is built
*during* the image build with `--check`, so a build producing a bad warehouse fails the image
rather than shipping it.

**Docker Desktop never came up.** The CLI is installed, the processes started, the engine pipe
never appeared after ~4 minutes of WSL2 cold start. The container artifacts are written and
reviewable but **have not been executed** — stated plainly rather than implied.

**Non-container path** — `deploy/local_deploy.py`: production uvicorn, two workers, no
`--reload`, fixed port, startup gated on `/api/overview` answering rather than on the process
existing, then a smoke test of all 12 routes the client calls.

## What actually happened

The client patch went in cleanly on first inspection — all six markers present. Except the
marker check only looked for the JavaScript. Two panels had **not** been inserted, because the
anchors used `&middot;` while the file contains a literal `·`. So `disparity()` and
`conformance()` existed and would throw on a null element.

Caught by checking the DOM ids rather than trusting the patch report.

### The real finding

With everything deployed and 12/12 browser tests green, a copy fix made 20 minutes earlier was
still not visible in the API response. Source on disk had the new string; the server returned
the old one.

Cause: **`up` health-checked the port, got a 200, and reported "deploy healthy" — against an
orphaned uvicorn from an earlier cycle.** That orphan had imported `app.main` *before* the
edit, and Python caches modules in memory, so it served stale code indefinitely.

Every green run — the 12-route smoke test, the 12 browser tests, twice — was partly against a
server running code two edits old.

The forensics were a detour worth recording: Windows `netstat` listed five PIDs on the port,
four of them already dead (stale entries), `Get-NetTCPConnection` named a dead PID as owner,
and the live orphan was a *system* Python invisible to every process query available in this
shell. Chasing PIDs was the wrong move.

The right fix is not better PID hunting. It is that **a deploy must never adopt a server it
did not start.** `up` now refuses when the port answers and no deploy-state file exists:

```
REFUSING TO DEPLOY: something is already serving on http://127.0.0.1:8090 and it
is not ours - there is no deploy state file. It may be an orphan running stale
code, which would silently pass every test.
```

A deploy that fails loudly is strictly better than one that adopts a stranger's process. Also
hardened along the way: `down` reclaims by *port* rather than by remembered PID (uvicorn
`--workers` spawns children; signalling the parent leaves them holding the socket), and waits
for the port to actually release before returning.

## Verification

Re-deployed on a clean port and confirmed the response carried the **current** string before
running anything. Then:

| Suite | Result |
|---|---|
| deployed browser (`test_deployed.py`) | **12 passed** |
| in-process browser (`test_lenses.py`) | 17 passed |
| fast (unit · contract · guardrail · MCP) | 77 passed |

**The browser suite was also proved to have teeth**, rather than assumed to: breaking one
renderer the same way the real bug broke it (`$('dispPolicy')` → a typo'd id) failed **6
tests**. Restored, green again.

The deployed suite asserts things the in-process suite structurally cannot: five lenses
reachable (it would have caught the client being five iterations behind), no console errors
across every lens, an evidence pack whose manifest hash is identical across two independent
browser-issued fetches, twelve concurrent requests against a read-only DuckDB opened by
multiple workers, and the deployed OpenAPI schema containing the iteration 02–04 routes.

## Still not done

- **Docker never ran.** The image and compose file are unexecuted.
- **Dagster and Terraform remain unexecuted** — carried over from iteration 05 and still the
  weakest claim in the repo.
- CI has no deploy job, so nothing catches this class of defect automatically.
- The `spine/metrics.py` ↔ Cube parity gap is documented but still open.
