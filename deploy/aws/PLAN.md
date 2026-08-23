# AWS Free-Tier Deployment Plan — Case Spine

Goal: the containerised portal (233 MB image, self-contained DuckDB warehouse,
`/state` volume for workflow writes) running on AWS at **$0 within Free Tier
limits**, verified by the same Playwright suites that gate every deploy locally —
plus a register that closes out every leftover from the project.

---

## 0. One decision before anything: which Free Tier do you have?

AWS changed the Free Tier on **15 July 2025**:

| Account created | What you get | Consequence for this plan |
|---|---|---|
| **Before 2025-07-15 (legacy)** | 12 months: 750 h/mo t2.micro/t3.micro EC2, 30 GB EBS, 5 GB S3, 750 h RDS, ECR 500 MB, always-free Lambda/DynamoDB/CloudFront | Run the EC2 path continuously for 12 months at $0 |
| **After 2025-07-15 (Free Plan)** | **$100 credit** at signup (+ up to $100 more for completing activities), valid up to 6 months; account cannot incur charges beyond credits on the Free Plan | Same EC2 path; a t3.micro ~$7.60/mo burns credits slowly — ~6 months easily covered. Hard $0 ceiling is built in (Free Plan blocks overage) |

Either way the architecture below fits. The **new Free Plan is actually safer**
(it cannot bill you); on a legacy account we add billing guardrails (Phase 1).

---

## 1. Architecture decision — why one EC2 instance, not the fancy options

The whole system was deliberately built to run from **one container**: DuckDB
baked at image-build (with the 11 data checks as a build gate), FastAPI serving
API + client, one declared writable volume at `/state`. The free-tier-honest
options:

| Option | Verdict |
|---|---|
| **A. EC2 t3.micro + docker compose** ✅ | Exactly what we run locally. 1 vCPU/1 GB is enough (compose limit is already 768 MB and the container is healthy in it). 750 h/mo covers 24×7. **Chosen.** |
| B. Lambda + API Gateway (always-free) | Read lenses would fit, but the action layer and investigation records need persistent writes → EFS or a DynamoDB storage rewrite. A storage-layer rewrite to save ~$8/mo of credits is bad engineering. Rejected. |
| C. ECS Fargate | No free tier at all. Rejected. |
| D. EKS (the enterprise Terraform in `infra/`) | $0.10/h control plane ≈ $73/mo before nodes. That module remains the *target-architecture document* for the Heartflow pitch (their stack), not the free-tier deploy. Kept, clearly labelled. |
| E. Lightsail | Only 90 days free. Rejected. |

**Image registry: GitHub Container Registry (GHCR)**, not ECR. Free, unlimited
for public images, integrates with the CI we already wrote, and keeps the AWS
footprint to compute+network only. (ECR's 500 MB free tier would also fit the
233 MB image — GHCR is chosen for CI simplicity, not necessity.)

**Warehouse**: stays baked-in DuckDB. No RDS (nothing to put in it), no Redshift
(free trial only, and the `Warehouse` Redshift branch is a documented stub).

### Target shape

```
GitHub repo ──push──▶ GitHub Actions ──build+test──▶ GHCR: case-spine:sha
                                                        │
   you (browser/Playwright) ──HTTPS──▶ Caddy ──▶ docker compose on EC2 t3.micro
                                        │              └─ /state on the 30 GB EBS
                              Let's Encrypt TLS         └─ nightly /state → S3 (≤5 GB)
```

Security posture for an internet-facing instance (this is synthetic data, but we
practice like it isn't):
- **No SSH port.** Administration via **SSM Session Manager** (free, IAM-scoped,
  audited) — instance role gets `AmazonSSMManagedInstanceCore`, port 22 closed.
- **HTTP(S) restricted to your IP** in the security group by default; widen
  deliberately if you want to share the link.
- **Caddy in front** for automatic TLS + `basic_auth` — the portal has no auth of
  its own (the OIDC seam is documented but unbound), so the proxy supplies the
  minimum credible gate before anything is reachable from the internet.
- Budget alarm at $1 (legacy account) / rely on the Free Plan ceiling (new).

---

## 2. Phases

### Phase 1 — Repo + CI go live (this is also Leftover #1)
The project is **not a git repository**; the CI written in
`.github/workflows/ci.yml` (fast suite, e2e, deployed-suite, guardrails, SBOM,
`terraform validate`) has **never executed**. Steps:
1. `git init`, commit, create GitHub repo, push.
2. Add `.gitignore` (`.venv*`, `data/`, `deploy/server.log`, `evidence/`,
   `ux/*.json` kept, `node_modules` n/a).
3. Watch the five CI jobs run for the first time on Linux — expect and fix
   Linux-vs-Windows drift (path separators in tests, the `deployed` job's
   process-group teardown). This finally executes `terraform validate` on the
   enterprise module (Leftover #2) and the whole suite on a second OS.
4. Add a `release.yml` workflow: on push to `main`, build the image, run the
   in-image data checks, push `ghcr.io/<user>/case-spine:{sha,latest}`.

### Phase 2 — AWS substrate via Terraform (`infra/aws-free-tier/`, new module)
Deliberately tiny — free tier is mostly about what you *don't* create:
- default VPC (create nothing), one **security group** (443/80 from `your_ip`,
  no 22), one **t3.micro** (or t4g.micro on new accounts — cheaper per credit)
  with 20 GB gp3 EBS, an **Elastic IP** (free while attached),
- **IAM instance role**: `AmazonSSMManagedInstanceCore` + `s3:PutObject` on one
  backup bucket,
- **S3 bucket** (versioned, ≤5 GB) for `/state` backups,
- (legacy accounts) `aws_budgets_budget` at $1 with email alert,
- `user_data` cloud-init: install docker + compose plugin, write
  `docker-compose.aws.yml` (image from GHCR, `case-spine-state` volume, Caddy
  service with your domain-or-IP + basic_auth hash), `docker compose up -d`,
  and a systemd timer for the nightly `aws s3 sync /state s3://…`.
- State backend: local tfstate committed nowhere / or S3 backend in the same
  bucket — small enough either way; plan uses local state with the file
  gitignored, documented.

Free-tier arithmetic (legacy): 750 h EC2 ✅, 30 GB EBS ✅ (we use 20),
EIP attached ✅, S3 ≤5 GB ✅, data transfer out 100 GB/mo ✅. Expected bill: **$0.00**.
New Free Plan: ~$8–9/mo of the $100+ credits; ceiling enforced by AWS.

### Phase 3 — Deploy + verify with the suites we already trust
1. `terraform apply` (needs only: your IP, GHCR image ref, basic-auth hash,
   optional domain).
2. Health gate: same contract as everywhere — `/api/overview` answering through
   Caddy.
3. **Run the real verification against the cloud**, exactly like local:
   `DEPLOY_BASE=https://<host> pytest tests/e2e/test_deployed.py` (41 tests) and
   `DEPLOY_BASE=… python tests/ux/measure_tasks.py aws` — the measurement
   harness doubles as a latency-honest smoke of the persona tasks over real
   internet RTT. Note: Playwright needs the basic-auth credentials —
   `browser.new_context(http_credentials=…)`; small fixture addition, done in
   this phase.
4. Wire the `deployed` CI job's optional cloud variant: manual-trigger workflow
   that runs the suite against the EC2 URL (secrets: URL + credentials).

### Phase 4 — Operations on free tier
- **Updates**: `docker compose pull && up -d` via SSM (or a tiny
  `deploy/aws/update.sh` invoked through `aws ssm send-command`). Watchtower is
  tempting but a silent auto-updater contradicts this project's "deploys must be
  loud" lesson (workflow/06) — rejected on principle.
- **Backups**: nightly `/state` → S3 (investigation records, signatures,
  actions DB). Restore = `aws s3 sync` back + `compose restart`. Rehearse once.
- **Teardown**: `terraform destroy` (EIP released, bucket kept unless emptied).
  On the new Free Plan, also note the 6-month credit horizon in the record.

---

## 3. Leftovers register — everything open, and where it lands

| # | Leftover | Disposition in this plan |
|---|---|---|
| 1 | **Repo not under git; CI (5 jobs) never executed** | Phase 1 — the prerequisite for everything |
| 2 | **Terraform never validated/run anywhere** | Phase 1 (`terraform validate` in CI) + Phase 2 actually *applies* the new free-tier module — the enterprise `infra/` module stays as pitch collateral, relabelled in README |
| 3 | **Cube schema ↔ `metrics.py` parity — documented KNOWN GAP, untested** | Close in Phase 1: a fast-suite test parsing `semantic/model/cubes/case_spine.yml` and asserting each measure's filter/appearance against `metrics.MEASURES` (no Cube runtime needed for structural parity) |
| 4 | Dagster `Warehouse` Redshift branch is a stub; schedule never daemon-run | Remains a stub **by design** on free tier (no Redshift). Record updated to say the seam is exercised only by DuckDB; revisit only if a real warehouse appears |
| 5 | MCP server is stdio-only, absent from deployments | Stays local-first (its audience is a local agent host). Documented in README; HTTP transport is future work, deliberately not exposed on a public EC2 |
| 6 | 5 open sev-≤2 UX findings (F6, F8-partial, F10, G1, G2) | Already tracked as `ux_finding` work items in the portal itself; candidates for a cycle-2 UX loop after the cloud deploy — not blockers |
| 7 | No auth on the portal (OIDC seam unbound) | Phase 2: Caddy basic_auth + IP-restricted security group is the free-tier answer; the OIDC seam remains the enterprise answer |
| 8 | Windows-only verification of `deploy/local_deploy.py` multi-worker caveat | Phase 1 CI runs the deployed job on Linux (2 workers), closing the loop the Windows 1-worker note left open |
| 9 | No backup story for sealed records/signatures | Phase 4 nightly S3 sync + one rehearsed restore |
| 10 | Playwright suites never run against a remote (non-localhost) target | Phase 3 — plus the http_credentials fixture addition |
| 11 | Published claude.ai artifacts are stale vs the current portal | Out of scope here; optional refresh after the cloud URL exists |
| 12 | 9 open process work items (regressions/disparities/field visits) | Demo data working as intended — they are the content of the portal, not debt |

## 4. Execution order & effort

| Step | Depends on | Effort |
|---|---|---|
| Phase 1 (git, CI live, Cube-parity test, Linux fixes) | GitHub account | ~1 session |
| Phase 2 (Terraform module) | AWS account + `aws configure` credentials **from you** | ~1 session |
| Phase 3 (apply, verify, cloud CI job) | Phases 1–2 | short |
| Phase 4 (backup timer, restore rehearsal, runbook) | Phase 3 | short |

**What I need from you to execute:** (a) which Free Tier generation your account
is (or create a fresh one — new Free Plan recommended: it cannot bill you);
(b) AWS credentials configured locally (`aws configure`, a scoped IAM user —
never the root user); (c) a GitHub account/repo destination; (d) whether the
portal should be reachable only from your IP or shared more widely.

## 5. Verification (definition of done)

- CI: all jobs green on GitHub, including `terraform validate` on both modules.
- `terraform apply` from zero completes; instance reachable **only** via
  HTTPS+basic-auth and SSM; port 22 closed; budget alarm (legacy) armed.
- `DEPLOY_BASE=https://<host>` → **41/41 deployed-browser tests** and a
  `ux/cycle-aws-metrics.json` with 6/6 persona tasks completing over the wire.
- Nightly backup object visible in S3; one restore rehearsed.
- Bill after 72 h: **$0.00** (legacy) / credits burn ≤ $1 (new plan).
