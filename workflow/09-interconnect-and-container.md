# Iteration 09 — Interconnection features + container path executed

## Disk / Docker (user-authorized)
Deleted Docker's WSL data VHDX (35 GB) + bootstrap distro via `wsl --unregister` —
C: went from 0 bytes free to 36 GB free. Docker Desktop recreated its distros on
restart and the engine came up in ~15 s, confirming the full-disk root cause from
workflow/08. Image `case-spine:local` then built first try; the in-image spine
build ran with `--check`. `docker compose up` reports healthy; the hardened compose
settings (read-only rootfs, cap_drop ALL, tmpfs /tmp, non-root uid 10001) all work.

## Features built
- **/api/ask + header Ask box** — deterministic keyword router over spine/metrics
  (8 intents, refuses rather than guesses, provenance on every answer, explicitly
  NOT an external LLM: wiring a hosted model into the portal would cross the one
  security boundary the platform argument is built on; free-form reasoning belongs
  on the MCP server with a real model attached).
- **/api/site/{id} + site card** — conformance, hazard realisations, release
  exposure and complaints for one site on one card; linked from the conformance
  table, the site worklist, the complaint trace, and Finding 04's footer.
- **Filterable complaints** — same list, three doors in: hazard row, engineering
  release row, site card. Filter chip + clear.
- **URL hash deep links** — #lens=…, #complaint=N, #site=N, #hazard=H-xxx,
  #release=vX — a shared URL reconstructs the exact view on a cold load.
- **Finding footers deep-link** into the lenses they summarise.

## Verification
- Fast suite 90 passed (7 new ask/site/filter tests incl. ask-vs-metric-layer
  agreement and partition consistency of complaint filters).
- Deployed browser suite 32 passed against BOTH the local deploy (8091) and the
  container (8088), including cold-load deep links and cross-lens click-throughs.
- Evidence manifest hash identical through the container across two fetches.

## Honest notes
- The Ask router answers 8 intents; anything else is refused by design.
- Container runs the image's baked warehouse (build-time fixture) — correct for a
  demo, and the SPINE_DSN env seam is where a real warehouse plugs in.
- Terraform remains the only still-unexecuted artifact (no binary on this machine).
