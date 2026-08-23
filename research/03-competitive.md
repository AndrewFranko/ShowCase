# Competitive landscape — key findings (agent 3)

## Threat board
| Threat | Severity | Timing |
|---|---|---|
| Cleerly (plaque-first reframing, ~$578M raised) | High | Now |
| Shared vendor-neutral CPT 75577 for plaque | High | Live Jan 2026 |
| Scanner OEM bundling (Siemens syngo.CT Coronary Cockpit) | Med-High | 2026-2028 |
| ML surrogates commoditizing CFD | Med-High | Already happened |
| Wire-free invasive physiology (CathWorks/Medtronic, Pie Medical) | Medium | 2026+ |
| Caristo inflammation axis (CaRi-Heart De Novo Jul 2026) | Medium | 2026+ |
| Photon-counting CT recalibration | Medium | 2026-2029 |
| Keya/Shukun (China) global price anchor | Low-Med US / High global | Now |

## Reimbursement structure (CRITICAL)
- FFRCT = **CPT 75580**, CMS ~$1,017 (2025). HeartFlow-specific-ish. CMS proposed
  reassigning to APC 5724 in CY2026 (-5.5% geometric mean cost); HeartFlow formally objected.
- Plaque = **CPT 75577**, Category I effective 1/1/2026, 4.00 RVUs, ~$1,012 office / $951 OPPS.
  **VENDOR-NEUTRAL** — HeartFlow, Cleerly, Elucid, Caristo, Artrya all bill it identically.
  => HeartFlow did the payer-education work and converted a proprietary economic position
     into a commodity one.
- CMS CY2027 OPPS proposed rule (Jul 2, 2026): new "Software as a Medical Service (SaMS)"
  category, status indicator O1, 36 HCPCS codes, 21 into New Technology APCs.
  **Comments due Aug 31, 2026.** Single largest binary risk to the per-case model.
- STAT News (Nov 2025): "Medicare will pay more than $1,000 for AI to analyze a heart scan.
  Is that too much?" — payer scrutiny of the whole category.

## LITIGATION: HeartFlow v. Cleerly
- Filed **E.D. Texas, April 13, 2026**. Six patents (priority 2012-2018).
- Targets Cleerly ISCHEMIA, Plaque Analysis, Compare. Seeks **permanent injunction**.
- Alleges founder Dr. James Min misused confidential info while a HeartFlow consultant.
  HeartFlow language: "one of the most egregious examples of piracy in the medical
  technology industry."
- Cleerly: "a lawsuit to limit competition... baseless claims."
- Read: patent litigation is what you do when the technical lead no longer self-enforces.

## Head-to-head (the only one, and it's bad for HeartFlow)
EHJ-Imaging Methods & Practice, single-center retrospective, **n=44 patients / 54 vessels**:
| Metric | Cleerly AI-QCT | HeartFlow FFRCT |
|---|---|---|
| Sensitivity | 0.84 | 0.84 |
| Specificity | **0.74** | **0.51** |
| Accuracy | 0.78 | 0.63 |
| AUC | **0.91** | **0.76** |
Caveats: n=54 vessels, single center, retrospective, median CAC 654, selection bias.
Hypothesis-generating only — but Cleerly cites it constantly and HeartFlow has no rebuttal study.

## CFD moat is technically gone
- Siemens **cFFR**: ML CT-FFR on a standard desktop workstation, on-site. MACHINE registry:
  per-vessel accuracy 58% (CTA) -> 78%; per-patient 71% -> 85%.
- DL surrogates: ~2,000x speedup over CFD (<2e-2 CPU-seconds/forward eval, Physics of Fluids 2022).
- Physics-informed DL surrogate trained on 1,014 synthetic coronary geometries (2026).
- **SimVascular** — fully open-source: segmentation -> 3D model -> meshing -> patient-specific
  simulation, incl. 0D/1D reduced-order solvers. Originated in **Charles Taylor's Stanford lab**
  — Taylor being HeartFlow's own founder/CTO. The open-source descendant of their own
  scientific lineage is free.
- Siemens holds granted US patents on ML-based CAD assessment (US 11,386,563; US 11,861,851).
  The ML-FFR IP landscape is contested, not HeartFlow's alone.

## Turnaround time gap is structural
- HeartFlow: median <1.5h (Plaque 90 min), 96% scan acceptance.
- HeartLung AutoChamber: 15-20 SECONDS. Circle CVI cvi42|Plaque: on-premise. Shukun: minutes.
- Where 90 min hurts: same-session decisions (chest pain unit, cath lab triage-and-discharge).

## PHOTON-COUNTING CT — the underrated engineering opportunity
Radiology (2025): PCD CT reduces measured total plaque volume by ~1/3 vs EID CT
(median 723.5 vs 1,084.7 mm3), higher low-attenuation plaque, much better reproducibility
(ICC 0.84-0.89 vs 0.47-0.62). Concluded **"previously published EID CT-specific Hounsfield
unit ranges cannot be directly translated."**
=> The QCI consensus 70th-percentile total-plaque-volume treatment threshold is
   DETECTOR-DEPENDENT. Every plaque vendor faces a re-validation tax.
=> First vendor to build PCD-native normative data gets a durable lead.
=> This is a cross-scanner harmonization + validation problem = test infrastructure +
   synthetic phantom simulation. Directly in the user's wheelhouse.

## Other competitor notes
- Cleerly: ~$578M raised, 5/7 Medicare MACs, 86M+ commercial lives, TRANSFORM RCT n=7,500
  asymptomatic (reads out ~late 2028). Cleerly ISCHEMIA (K231335, Jan 2024) delivers an
  ischemia answer WITHOUT CFD, from the plaque model.
- Elucid: PlaqueIQ cleared Oct 2024, only one validated against **histology** ground truth.
  FFRCT pending FDA, launch targeted 2026, derived FROM the plaque algorithm (guarantees
  plaque/FFR concordance — HeartFlow's two models can disagree).
- Artrya (ASX:AYA): Salix Anatomy+Plaque cleared Aug 2025; Coronary Flow FDA submission
  imminent, launch 2H CY2026. FY26 SaaS revenue only A$177k — pre-revenue.
- Medis QFR: **FAVOR III Europe FAILED non-inferiority** vs FFR (6.7% vs 4.2% MACE).
  Effectively removed as a threat; useful to HeartFlow as evidence CFD fidelity matters.
- Pie Medical CAAS vFFR: **FAST III non-inferior**, n=2,235, NEJM Mar 2026.
- CathWorks FFRangio: **ALL-RISE non-inferior**, NEJM ACC.26. **Medtronic acquired,
  completed Apr 20 2026, up to $585M** — global cath-lab salesforce now carries it.
  => Two wire-free invasive physiology platforms landed positive NEJM RCTs in one ACC cycle.
     Narrows the cost delta FFRCT arbitrages.
- Caristo CaRi-Heart: **FDA De Novo July 29 2026** — coronary INFLAMMATION (FAI-Score).
  In patients with no/minimal plaque: abnormal FAI -> 9.5x cardiac mortality. Third reframing.
- Circle CVI cvi42|Plaque cleared Oct 2025, explicitly **on-premise**, "entirely in-house
  rather than requiring external cloud-based processing." Attacks the send-out model.
- Keya DeepVessel FFR: FDA cleared Apr 2022 (2nd FFR-CT in US), + CE, NMPA, Singapore HSA.
- Shukun skCT-FFR: NMPA 2022, ~89% agreement w/ invasive FFR, fully automated on-site,
  reduced-order 3D CFD, 3,000+ hospitals.

## Market phase
No documented case of a health system switching FROM HeartFlow found. Land-grab, not
displacement. Sites run HeartFlow AND Cleerly side by side. Displacement risk arrives when
reimbursement tightens and sites consolidate to one vendor.

## Other financial details
- Q1'26 GAAP GM 80.2%; net operating loss $29.5M incl. $7.5M impairment; net loss $27.4M
- Q2'26 net operating loss $17.9M
- FFRCT was ~99% of revenue as of March 2026 — concentration risk
- 1,250 Plaque-activated accounts in 2 years vs 8 years for the FFRCT base
- International Q2'26 +12% only (vs +51% US)
- Market cap ~$4.1B
