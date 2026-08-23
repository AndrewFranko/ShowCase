# Iteration 08 — The container path, attempted for real

## The claim being tested

Iteration 06 left one artifact written but never executed: the container. `Dockerfile` and
`docker-compose.yml` were reviewed, reasoned about, and honestly labelled **not run** —
"Docker Desktop never came up." This iteration set out to close that gap: build
`case-spine:local`, `docker compose up`, wait for `(healthy)`, smoke the 12 client routes
through the published port 8088, and prove evidence-pack reproducibility
(`manifest_sha256` identical across regenerations) against the containerised warehouse.

**None of that ran.** The engine never became usable. This document records the attempt,
the diagnosis, and the root cause — which turned out not to be Docker at all.

## What was attempted

| step | result |
|---|---|
| Pre-flight: port 8088 free, compose paths valid, `README.md` present for the `COPY` | ok |
| Poll `docker info` every 20 s, ~6 min (background) | down throughout |
| Poll `docker info` every 20 s, 374 s (foreground, second window) | down throughout |
| Force-restart Docker Desktop (`Stop-Process`, `wsl --terminate docker-desktop`, relaunch) | engine answered **once**, ~2 s after relaunch |
| Re-verify before building (`docker system df`) | pipe gone again — engine had already died |
| Build / compose up / smoke table / evidence-hash check | **not executed** |

The transient green is worth recording on its own: a single successful `docker info`
during Desktop's startup window is not a usable engine. Had the build been fired on that
one green poll, it would have failed midway with a vanished pipe — the same class of
accidental-green this repo keeps catching (the orphaned-uvicorn deploy in iteration 06,
the decorative Dagster assets in iteration 07). Verify immediately before acting, not
merely once.

## Diagnostics

Collected 2026-08-22, in order of increasing specificity:

- `wsl --status` — default distro Ubuntu, WSL 2. WSL itself is functional.
- `wsl -l -v`:

  | distro | state |
  |---|---|
  | Ubuntu | Stopped |
  | zephyr | Stopped |
  | docker-desktop | **Running** |
  | docker-desktop-data | **Stopped** |

- Inside the running `docker-desktop` distro: only `/init` and the plan9 relay are
  alive; `/usr/local/bin` contains nothing but `wsl-bootstrap`; there is no
  `/var/run/docker.sock` and no `dockerd`. The distro booted its bootstrap and then
  never received the engine.
- Both named pipes absent: `//./pipe/docker_engine` (default context) and
  `//./pipe/dockerDesktopLinuxEngine` (desktop-linux context).
- Docker Desktop's own processes (`Docker Desktop.exe` ×3, `com.docker.backend.exe` ×2)
  all running — the UI-visible state would say "starting", indefinitely.

## Root cause

**The C: drive is completely full: 281 G / 281 G, 0 bytes free.**

Docker Desktop's WSL2 backend keeps its engine and image store in a VHDX at
`C:\Users\andre\AppData\Local\Docker\wsl\data` — currently **35 GB**, and it is the
backing disk of exactly the distro that refuses to start (`docker-desktop-data`,
Stopped, while its `docker-desktop` sibling boots fine because its distro VHD is a
small 1.2 GB and needs no growth). WSL2 cannot mount and grow a dynamically-expanding
VHDX with zero bytes free on the host volume, so the data distro never comes up,
`dockerd` never starts inside the bootstrap distro, and the engine pipe never appears.
The ~2 s of green after the forced restart fits the same story: the backend gets partway
through bringing the engine up, hits the disk wall, and tears down.

This also retroactively explains iteration 06's "engine pipe never appeared after
~4 minutes of WSL2 cold start" — same symptom, same cause, undiagnosed at the time. And
it rhymes with iteration 07, where pip temp and `DAGSTER_HOME` had to be pointed at D:
because C: was already at 0 bytes free. The disk has been the quiet antagonist of three
iterations.

## Remediation — the user's call, not this repo's

Both fixes are system-level changes and are deliberately **not** performed here:

1. **Free space on C:.** Even a few GB should let the data VHDX mount; note the Docker
   VHDX itself is 35 GB and is a candidate for reclamation (`docker system prune` once
   the engine runs, or deleting the VHDX from Docker Desktop's *Troubleshoot → Clean /
   purge data* if the local image cache is expendable — it is, for this repo: everything
   is rebuilt from the fixture at image build time).
2. **Relocate the Docker/WSL data root to D:** (61 GB free). Docker Desktop supports
   this via *Settings → Resources → Disk image location*, or manually with
   `wsl --export docker-desktop-data` / `--import` onto D:. This is the durable fix
   given C:'s baseline pressure.

## What remains ready to run

The execution plan is written and pre-flighted; once the engine is up it is:

```
docker compose up -d --build        # builds case-spine:local; spine built --check at image build
docker compose ps                   # wait for (healthy) — /api/overview gates it
# smoke: the 12 SMOKE_ROUTES from deploy/local_deploy.py against http://localhost:8088
# reproducibility: GET /api/evidence/frontier twice, /api/evidence/disparity twice,
#                  assert manifest_sha256 identical across calls (and stable across
#                  container restarts — the warehouse is baked into the image)
docker compose down
```

Nothing in the container path is being claimed as verified. The honest ledger stands
where iteration 06 left it, now with a diagnosis attached: the artifacts are reviewable,
the execution is blocked on disk space, and the first `docker compose up` after
remediation should be treated as the real test.
