# Internal engineering weak spots + SaMD burden (agent 4)
Primary source: S-1/A#1 (Aug 1 2025), 510(k) K250902 summary, Glassdoor/Indeed, GitHub.

## CORRECTION TO AGENT FRAMING
Agent used stale FY2026 guidance ($218-222M, +24-26%, issued Mar 2026) to build a
"growth decelerating" thesis. Guidance was raised twice since, to $246-250M (+40-42%).
Growth ACCELERATED. Do not repeat the deceleration claim. The margin argument still holds
and is stronger: volume +74% YoY means the production line must scale much faster.

## THE PRODUCTION PIPELINE (verified, S-1 pp.120, 126-127)
DICOM ingest -> ML segmentation (coronary tree, myocardium) -> "proprietary software that
guides quality-oriented production analysts through each step to review and potentially
correct the segmentation" -> ML regenerates final 3D model using analyst inputs ->
stenosis + plaque quantification + CFD blood-flow simulation -> web app / PDF / EMR push.

- "The corrections and changes from the analyst quality inspection step are stored in a
  database as labels for training our algorithms." => the correction loop IS the training
  data flywheel. The analyst tool is COGS driver + label factory + post-2031 moat generator.
- Core anatomic + FFRCT algorithms on 3rd generation. Median TAT 1.6 hours.
- Analyst processing time: 69 min (2021) -> 26 min (Q4 2024), ~62% reduction.
- S-1: "future new algorithm launches will have significantly less impact on automation
  increases and associated gross margin expansion." => easy gains HARVESTED.
- Compute: AWS PLUS "production related computers... located in our Mountain View office and
  in Austin, Texas" — on-prem production hardware in two offices.
- Capitalized internal-use software: only $4.6M (2023) / $4.1M (2024).

## THE RISK-CONTROL TRAP (the crux)
- S-1: "we cannot assure you... that our analyst-based review process will identify and
  correct any errors in the outputs of our AI Technologies."
  => The human QC layer is the RISK CONTROL OF RECORD. Automating it is a risk-control
     change requiring re-justification under ISO 14971.
- K250902 (v4.0, cleared Jul 18 2025) explicitly included "automation of internal quality
  controls functions" as a CLEARED DEVICE CHANGE, not a background refactor.

## PCCP (verified, K250902)
- 1 of only 8 PCCP-authorized clearances out of 92 cardiology AI/ML 510(k)s in 2025.
- Covers exactly THREE modifications: optimize training params for new data; incorporate 3D
  spatial context as new input; fine-tune post-processing params for complex regions.
  Acceptance: non-inferiority on plaque detection sensitivity + volume error, DICE >= 0.7.
- Models LOCKED: "All algorithms are then frozen and validated prior to product release."
- Ground truth: 60,555 annotated areas, 583 lesions, 100 patients, 67 institutions,
  stratified by age/sex/image quality/scanner/plaque type/vessel location.
- Train/test separation enforced by a "restricted library solely used for validation
  testing" — a PROCESS control where it should be a SYSTEM control. Audit-finding risk.

## RELEASE ENGINEERING IS A PATIENT-SAFETY SURFACE (S-1)
"we have experienced software code defects and software release process defects that have
resulted in intermittent interruptions to the physician's ability to use our Heartflow
Platform" — and a subset were MAUDE-reportable.

## STACK
- "cloud-based algorithmic pipelines for image and geometry processing (C++, Python, AWS)"
- "interactive 3D graphical software (C++, Windows)" = the analyst correction workstation
- AWS + Terraform/Chef/Ansible, Docker, Kubernetes, GitHub Actions, Jenkins, Harness
- GitHub org github.com/heartflow: only 3 repos, all forks. Includes
  aws-subnet-ip-address-utilization-monitor => EKS subnet IP exhaustion, real k8s scaling walls.
- No engineering blog, no talks, no papers under HeartFlow affiliation. Recruiting liability.

## CULTURE (Glassdoor 2.8/5, 177 reviews, 27% below IT average)
- "Modern software engineering practices like cloud native development, agile devops, and
  MLOps are lacking."
- "Management does not understand how an AI/ML company efficiently works, [they] all come
  from Medtronic and manage day to day like it."
- "too many concurrent, high priority projects for the limited resources available"
- "several layers of bureaucracy"; "constant re-organization"
- Positive counter-signal: "On the Software Engineering side, the culture is evolving
  rapidly and in a good direction (fixing fundamentals to go faster)."
- Comparably: Executive Team rated D.
- Intern req: "transition toward a cloud-native, unified ML pipeline" => currently neither.

## ANALYST OPS (Austin)
- 26,400 sq ft Austin lease EXPIRING DECEMBER 2026. HQ Mountain View 61,500 sq ft to 2030.
- Indeed 2.8/5, job security & advancement 2.1/5. "repetitive in a dim lit environment";
  "Metrics based, micro managed."
- Glassdoor Austin: "You have to meet a daily quota or else you are at risk of being fired";
  "Austin feels like an afterthought."
- Analysts work in a "light-controlled production environment", require "contrast
  sensitivity to grayscale" and "color perception", weekends/holidays.

## PATENTS / THE CLIFF (S-1, as of Dec 31 2024)
- 586 issued worldwide (309 US, 280 foreign) + 103 pending.
- Some cover "deriving FFRCT using purely machine learning methods" — hedge against
  pure-ML competitors bypassing CFD claims.
- NEXT LICENSED-PATENT EXPIRY 2028. NEXT OWNED-PATENT EXPIRY 2031.
  Foundational US8157742B2 (Taylor, priority Aug 12 2010) expires Jan 25, 2031.
- => Moat must migrate from method patents to labeled-data asset + clearances + payer
     coverage. Annotation/label infrastructure is a STRATEGIC ASSET managed as a cost center.

## REGULATORY FRAMEWORK DATES
- QMSR effective Feb 2, 2026 — 21 CFR 820 incorporates ISO 13485:2016 by reference.
  FDA retired QSIT; inspects under Compliance Program 7382.850.
- CSA final Sept 24 2025 -> SUPERSEDED Feb 3 2026 by "Computer Software Assurance for
  Production and Quality MANAGEMENT System Software" (retitled for QMSR). Supplements the
  2002 GPSV except SUPERSEDES GPSV Section 6.
  - Scope: production/QMS software incl SaaS/IaaS/PaaS, analytics, automation, AND AI/ML
    tools used for production/QMS purposes. EXPLICITLY EXCLUDES device software (SaMD).
  - High-process-risk features (automated accept/reject, automated corrections) -> scripted
    or hybrid testing. Everything else -> UNSCRIPTED (exploratory, scenario-based, ad-hoc).
  - Record: intended use, risk rationale, objectives, testing performed, issues, conclusion.
    Automated test results are acceptable evidence.
  => The economic barrier to building good internal tools dropped hard.
- PCCP for AI-Enabled Device Software Functions — FINAL Dec 4, 2024.
- AI-Enabled Device Software Functions: Lifecycle Management — STILL DRAFT (Jan 2025).
- Content of Premarket Submissions for Device Software Functions — Final Jun 14, 2023.
- FD&C 524B in force since Mar 29 2023; RTA authority since Oct 1 2023. Requires SBOM.
  NOTE: 524B SBOM and IEC 62304 SOUP list are the SAME dependency graph maintained for two
  regulators under two schemas. Most teams maintain both by hand.
- IEC 62304 Edition 2: FDIS ~May 2026, publication forecast early-mid 2027. Adds a
  NORMATIVE AI/ML section requiring dataset version control, model drift tracking,
  retraining processes, post-market performance monitoring.
- One study: 50% of US AI/ML device recalls stemmed from design or development problems.

## CAVEATS
Glassdoor/Indeed/SEC block WebFetch (403); Glassdoor quotes are search-surfaced snippets.
Patent counts as of Dec 31 2024; headcount as of Mar 31 2025. Analyst headcount estimated.
