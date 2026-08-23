# Clinical / regulatory / reimbursement gaps (agent 2)

## FDA CLEARANCES — all eight, product code PJA, 21 CFR 870.1415, Class II
Queried against openFDA 510(k) API (`applicant:"heartflow"`).

| Submission | Device | Decision date | Type |
|---|---|---|---|
| **DEN130045** | HEARTFLOW FFRCT | 2014-11-26 | De Novo (created PJA classification) |
| K152733 | FFRCT | 2016-01-13 | Traditional |
| K161772 | FFRCT | 2016-08-24 | Traditional |
| K182035 | FFRCT | 2018-12-06 | Special |
| K190925 | HeartFlow FFRCT Analysis | 2019-08-15 | Traditional |
| K203329 | HeartFlow Analysis | 2021-01-08 | Traditional |
| **K213857** | HeartFlow Analysis | 2022-10-14 | Traditional — Plaque + RoadMap |
| **K250902** | HeartFlow Analysis | 2025-07-18 | Traditional — next-gen Plaque |

Corrections to circulating claims: the De Novo is DEN130045, NOT DEN130025. The pivotal
trial for the De Novo was **NXT**, not DeFACTO (which missed its primary endpoint).

## MAUDE — THE MOST UNDER-REPORTED PART OF THE STORY
`api.fda.gov/device/event.json?search=device.manufacturer_d_name:"heartflow"` returns
**127 MDRs**, 2017-05-24 through 2026-07-08. The 10-K characterizes the 2017-2025 subset as
**116 reports, of which 104 were false negatives** and 11 incorrect/imprecise results.

**Dominant failure mode: the model renders a vessel LARGER than the CT data supports ->
flow simulation under-detects the stenosis -> false negative FFRCT >0.80 -> patient not
referred.**

Representative reports:
- 3021637148-2023-00008 (2023-12-20, Injury): distal left main modeled larger than CT
  indicated; **patient underwent urgent CABG.**
- 3021637148-2023-00007 (2023-11-17, Injury): proximal RCA oversized vs angiography;
  patient developed unstable angina.
- 3021637148-2025-00009 (2025-07-22, Injury): registry participant, RCA FFRCT >0.80,
  cardiac arrest 178 days post-enrollment; **death**.
- 3021637148-2026-00003 (2026-03-06, Injury): no significant LAD stenosis reported; patient
  subsequently had **NSTEMI with severe stenosis confirmed on ICA**.
- Repeated cluster (2023-05-11, 2023-10-06, 2023-10-20, 2025-05-06, 2025-08-07):
  **"CT dataset incorrectly accepted"** despite failing image-quality requirements — one
  dataset incorrectly accepted on the FOURTH submission; another notes "validity of negative
  analysis results cannot be confirmed."
- Stent/contraindication misses (2025-00006, 2025-00013, 2026-00005): analyses released with
  FFRCT values in vessels containing undetected stents — a labeled contraindication.

**!! THE ROOT-CAUSE SHIFT — the single most important finding for the pitch !!**
Through 2023, MDR narratives attribute failures to **"analyst error"** in the human QC step.
From 2025 onward they attribute them to **"automated technology" misinterpretation** and
"inspection process" failure.
=> As Heartflow migrated from analyst-mediated segmentation to deep-learning automation,
   **the automation did not eliminate the failure mode — it changed its label.**
   This is direct, primary-source evidence that automating the human out of the loop
   transfers risk rather than removing it, and that the current evidence apparatus is not
   catching it prospectively.

## RECALLS / WARNING LETTERS
- **Recalls: none.** openFDA returns no records; 10-K states affirmatively that no MAUDE
  report "resulted in a mandated or voluntary correction, field safety action, removal or a
  recall."
- **Warning letters / 483s: none found.** Verified-negative to the limits of public search
  (accessdata.fda.gov rate-limited).
- 10-K discloses "software code defects and software release process defects that have
  resulted in intermittent interruptions to the physician's ability to use our Heartflow
  Platform."

## EX-US
| Jurisdiction | Status |
|---|---|
| EU | CE cert TÜV Nord 2011-07-26; **Notified Body changed TÜV Nord -> BSI in H2 2024**. MDSAP (AU, CA, US, JP) |
| Japan | PMDA application Feb 2015, SHONIN approval Nov 2016. **National reimbursement effective 2018-12-01** |
| Canada | MDL Aug 2015, current |
| UK | NICE **MTG32**, published 2017-02-13, updated 2021-05-19. "Should be considered", modelled saving £159/patient |

NICE MTG32 -> HealthTech guidance 429 migration: UNVERIFIED (nice.org.uk 403).

## CLINICAL EVIDENCE — AND THE CRITIQUES

### Structural criticisms applying to the whole chain
1. **Sponsorship saturation.** "All 3 of the included trials were supported by funding from
   Heart Flow" (pooled pivotal analysis). 10-K: Heartflow sponsored 50 of ~200 studies in
   its dossier — and the sponsored ones are the pivotal ones.
2. **Circular validation.** Invasive FFR is itself an imperfect reference with its own
   reproducibility problems.
3. **Surrogate endpoints throughout.** Nearly every positive trial measures test utilization
   or management change, not hard outcomes. Where hard outcomes were measured (FORECAST,
   TARGET, UK audit), FFRCT did not improve them.

### Trial-by-trial
- **DISCOVER-FLOW (2011)**, n~70 patients / 103 vessels. First-in-human accuracy vs FFR.
- **DeFACTO (2012)**, n~407 / 664 vessels, 17 centers, JAMA.
  **MISSED its prespecified primary endpoint for per-patient diagnostic accuracy.**
  The "AUC 0.81 vs 0.68" salvage is a secondary discrimination measure. Most consistently
  omitted from company materials.
- **NXT (2014)**, n=254 / 484 vessels, JACC. Basis for the De Novo. Per-vessel accuracy 86%
  vs 65% CCTA alone. Per-patient sens 86% / spec 79%; CTA alone sens 94% / spec 34%.
  **Critique: the specificity gain costs sensitivity (94%->86%)** — it trades away exactly
  the rule-out property that makes CCTA valuable.
- **Pooled pivotal (609 patients / 1,050 vessels)**:
  Per-vessel: sens 82.8%, spec 77.7%, **PPV 60.8%**, NPV 91.6%, accuracy 79.2%.
  Per-patient: sens 89.4%, spec 70.5%, PPV 69.7%, NPV 89.7%, accuracy 78.7%.
  **A positive per-vessel FFRCT is wrong ~39% of the time** against invasive FFR.
- **PLATFORM (2015)**, n=584. Company-sponsored, **sequential cohorts, NOT randomized**.
  Comparator was an invasive-first pathway, inflating apparent benefit vs a modern CCTA-first
  standard.
- **ADVANCE registry (2018)**, n=5,083, 38 centers. Management change 67% at 90 days.
  Critiques: not randomized, referral bias; accompanying editorial called the primary
  endpoint **"a simulation exercise that is not reflective of guidelines or routine clinical
  care"**; **no central event adjudication committee**; studies "almost exclusively sponsored
  by or conducted by investigators connected to the company."
  ADVANCE-DK 7-year (TCT 2024): MACE 16.2% / 7.8% / 5.7%. Prognostic stratification, not
  proof of treatment benefit.
- **FORECAST (2021)**, n=1,400, 11 UK centers, EHJ — **THE KEY NEGATIVE RCT**:

  | Endpoint | FFRCT | Standard care | Result |
  |---|---|---|---|
  | Primary: 9-mo total cardiac cost | £1,605 | £1,491 | **+£114 (+8%), P=0.10 — MISSED** |
  | MACCE @ 9 mo | 10.2% | 10.6% | P=0.80 — no difference |
  | ICA use | 19% | 25% | P=0.01 — reduced |
  | Angina / QoL | — | — | No significant difference |

  Also: **39 of 259 referred scans (15%) could not be analysed for technical reasons.**
  Directly contradicts NICE MTG32's modelled £159/patient saving — same health system.
- **PRECISE (2023)**, n=2,103, 65 centers, JAMA Cardiology. Company-sponsored.
  Headline: 70% reduction in composite of death/MI/ICA-without-obstructive-CAD.
  **Raymond J. Gibbons (Mayo), editorial:** the ICA-without-obstructive-CAD component
  **"is not a measure of patient safety, but rather a measure of physician preference"**;
  its use in the primary endpoint was **"not justified and potentially misleading."**
  The composite is essentially entirely driven by that soft component. No difference in
  all-cause death, MI, or symptoms. The trial also confounds FFRCT with a deferred-testing
  protocol — much of the ICA reduction may come from not testing low-risk people at all.
  10-K's own commercial framing: internal analysis showing **"a 20% increase in net revenue
  for the cardiac catheterization lab."** The pitch to the cath lab is higher margin — which
  is precisely the argument that undercuts the utilization-reduction case made to payers.
- **TARGET (2023)**, n=1,216, Circulation — on-site CT-FFR, not Heartflow.
  Reduced ICA-without-obstructive-disease, **but increased overall revascularization without
  improving symptoms, QoL, or MACE.** Independently reproduces the pattern AND demonstrates
  on-site ML CT-FFR as a structural threat to the off-site cloud model.
- **PACIFIC (2019)**, n=208, single site. Company-funded; FFRCT was **not in the original
  design — added as a retrospective sub-study.** AUC 0.94 vs PET 0.87, CTA 0.83, SPECT 0.70.
  This retrospective single-center add-on is the primary basis for "best non-invasive test"
  marketing.

### Plaque Analysis evidence — thinner than FFRCT
- REVEALPLAQUE (2024), n=237, 432 lesions: 95% agreement with IVUS. An **agreement study
  against an imaging reference, not an outcomes study.**
- DECODE (2024): management-change study, framed because "its utility in terms of impact on
  patient management remains unclear."
- DECIDE Registry (2025): ~20,000 patients, >30 US sites. Primary endpoint = **change in
  medical management**. Mean LDL reduction 18.7 mg/dL, translated into "an estimated 15%
  decrease in risk" — **that risk reduction is MODELLED from LDL, not observed.**
- Next-gen "21% improvement in plaque detection": UNVERIFIED, company-reported.

**Central critique: there is no randomized trial showing that quantifying plaque improves
outcomes.** Every endpoint is agreement-with-reference or management-change. ACC and AHA
scientific statements specifically call out "the need for rigorous validation and
standardization" of AI-enabled CCTA plaque evaluation. The 10-K concedes Heartflow expects
to *begin* enrollment in three RCTs in high-risk asymptomatic populations.

### Independent HTA verdict — VA Evidence Synthesis Program (NCBI NBK572556)
- Specificity 73-76% (Heartflow) vs 61-64% (CCTA alone); sensitivity similar.
- **"No randomized controlled trials investigated the impact of HeartFlow on diagnostic or
  clinical outcomes."**
- Short-term cardiac event rates similar. **"Our confidence in these findings is very low."**
- Effect on ICA use was **directionally inconsistent**: reduced ICA when patients were headed
  straight to cath (100%->40%), but **increased** ICA when substituted for other testing
  (12.5% vs 10%).
- "New evidence did not resolve the evidence gaps identified in the 2019 ESP report."

## THE GREY ZONE (FFR 0.75-0.80)
- Lesions in the grey zone are ischemic on invasive FFR only ~50-60% of the time.
- Mean CT-FFR in the grey zone was **0.72** — systematic overestimation of severity exactly
  where decisions are hardest.
- Scatter vs invasive FFR widens at lower FFRCT values, biased toward overestimating severity.
- **Measurement-location artifact:** values at the terminal vessel decline physiologically
  even without disease. The 2026 SCCT/SCAI consensus now MANDATES reporting the value
  **2 cm distal to the lesion** — and lead author Weir-McCall conceded this is the document's
  most controversial recommendation precisely because distal focus **produces false positives.**
- One institution's independent calibration found optimal threshold **<=0.78, not 0.80**, and
  argued for institution-specific cutoffs.
- High calcium burden may cause overestimation of stenosis severity.

## GUIDELINES
- **2021 ACC/AHA Chest Pain Guideline: FFR-CT is Class 2a.** Population: 40-90% stenosis in
  a proximal or mid vessel. **CCTA itself is Class 1, Level A** — the only non-invasive test
  with that rating.
  => The guideline elevated CCTA, not FFRCT. The 10-K framing that guidelines "support CCTA
     plus Heartflow FFRCT Analysis as the preferred pathway" overstates a 2a add-on.
- **2024 ESC Chronic Coronary Syndromes:** CT-FFR "may be considered" — standard Class IIb
  phrasing, weaker than ACC/AHA 2a. (Formally UNVERIFIED — full text inaccessible.)
  European commentary describes it as "a costly technique with limited availability and
  certain drawbacks."
- **NICE MTG32:** "should be considered."
- **2026 SCCT/SCAI Expert Consensus (published June 3 2026, JCCT, led by Jonathan
  Weir-McCall, endorsed by ACC)** — the most consequential recent document:
  - **Narrows the primary indication to 50-90% stenosis** (from the guideline's 40-90%).
  - Mandates reporting the post-lesional value 2 cm distal; acknowledges this generates
    false positives.
  - Nitroglycerin and heart-rate control required; **motion artifact named as the most common
    cause of failed analyses.**
  - Anti-overuse language: "If after the test, you're going to give antianginals whether it's
    positive or negative... this is layering tests, layering costs, and providing noise
    without additional benefit."
  - Concedes stress MRI remains necessary where stents, bypass grafts, or complex anatomy
    limit CT-FFR.
  => Two guideline-level HEADWINDS ON VOLUME, from the societies most favorable to cardiac CT.

## REIMBURSEMENT — THE DECISIVE VARIABLE

### Coding history
| Period | Codes |
|---|---|
| 2018-2023 | Category III: 0501T-0504T |
| **Jan 1 2024 ->** | **Category I: 75580** (FFRCT) |
| **Jan 1 2026 ->** | **Category I: 75577** (AI-enabled coronary plaque analysis), 0.85 work RVU, 4.00 total RVUs |

### The payment-vs-price gap — the crux
| Year | Event | Amount |
|---|---|---|
| 2018 | Initial OPPS rate set | ~$1,500 |
| Jul 2019 (final Nov 2019) | **Cut** based on hospital discounted-charge data | ~$900 |
| 2019-2023 | Held flat | ~$900 |
| Jan 2023 | **AMA RUC valued the service at $1,100** | $1,100 |
| Jul 13 2023 | **CMS REJECTED the RUC value**, citing discomfort with per-click software-as-a-service pricing | ~$900 |

**CMS's objection is STRUCTURAL, NOT CLINICAL** — it does not want to price per-click SaaS.
Durable risk with no evidentiary remedy. Heartflow's list price to hospitals has been
reported at ~$1,100/case — i.e. for years the Medicare hospital rate sat BELOW the vendor's
price, making each Medicare case a potential loss.

### Current rates
- **FFRCT (75580), APC 5724:** CY2025 OPPS $1,017; CY2025 PFS $839.
- **CY2026: APC 5724 cut ~14-15%.** 10-K flagged "a reduction of up to 15%."
- **!! ROOT CAUSE IS A BILLING-DATA DEFECT, NOT A POLICY JUDGMENT !!**
  CMS acknowledged an "outdated edit may have impacted the geometric mean for CPT code
  75580." Braid-Forbes: 75580 had frequency 17,813 with a geometric mean cost of only
  **$278.51**, and **75580 alone drove a 5.5% reduction in the CY2026 proposed APC geometric
  mean cost.** SCCT asked CMS to keep FFRCT in APC 5724 for three years as a buffer while
  hospitals fix their billing.
  => Because OPPS rates are set from hospitals' own reported charges, and hospitals are
     mis-reporting 75580 at ~$278 against a ~$1,000 rate, **the payment rate is being dragged
     down by customers' billing errors.** Heartflow cannot fix this directly, and each
     downward step compounds: lower rate -> weaker hospital margin -> less usage.
     **This is a data-quality problem masquerading as a policy problem, and it is
     addressable with tooling.**
- **Plaque (75577):** national rate finalized Nov 2025, effective Jan 1 2026. ~$951 OPPS /
  $1,012 PFS non-facility.
- **CCTA (75574):** ~$357 OPPS / $318 PFS. FFRCT pays ~3x the scan that generates it — an
  economic oddity payers notice.
- **NTAP:** none identified. NTAP is inpatient-only, so absence is structurally expected.

### Coverage breadth
| Product | Medicare | Commercial |
|---|---|---|
| FFRCT | Established; MAC LCDs (Noridian L38613 JE/JF) | ~99% of US covered lives |
| Plaque | 5 of 7 MACs at 10-K; **all 7 as of Jan 2026** | ~75% of covered lives. Aetna (Jan 2026) was the 4th national payer, after UnitedHealthcare and Cigna (Oct 1 2025) and Humana |

**Note the dependency:** commercial plaque coverage was gated on a **radiology benefit
manager (EviCore)** guideline update, not individual payer science reviews. Single point of
failure — and it applies to competitors equally (Cleerly, Elucid, Circle all got coverage on
the same EviCore change), so **it confers no competitive moat.**

**Coverage criteria are restrictive.** Carelon (updated 2026-05-01) requires ALL of:
symptoms consistent with myocardial ischemia; **symptoms persist despite maximal GDMT**;
CCTA within the preceding 90 days; and >=1 stenosis of 40-90% in a proximal/mid segment.
The "despite maximal GDMT" clause excludes many first-presentation patients.
Noridian L38613 covers FFR-CT "as an alternative to stress testing, not alongside it" —
so the layered use pattern the SCCT consensus warns about is also NON-COVERED.

Documented denial failure points: authorization mismatches, missing ordering-provider NPI,
incomplete documentation, component-billing errors.
CAUTION: the commonly cited "45-50% of denials are 'not medically necessary'" figure comes
from a generic prior-auth blog and is **NOT Heartflow-specific.**

## REAL-WORLD COST EVIDENCE CONTRADICTS THE VALUE CASE
Nicol et al., JACC: Cardiovascular Imaging, Aug 2023 — multicenter UK audit covering the
three years FFR-CT was centrally funded in England:
- **FFR-CT strategy £2,102/patient vs £1,411 for stress imaging — ~49% MORE expensive.**
- 46 events (2%) over mean 17-month follow-up; **FFR-CT at the 0.80 cutoff was NOT predictive
  of events.**
- Companion Bristol audit (1,145 CCTAs): adding FFR-CT to CAD-RADS **dropped specificity
  92.7% -> 75.5% and accuracy 91% -> 78.4%** (both p<0.001), with a non-significant
  sensitivity gain. In CAD-RADS 4, **89.8% of FFR-CT exams were positive with only 26.7%
  specificity.**
- Authors: "Supplementing a sensitive but non-specific test (CT) with another (FFR-CT) is
  unlikely to be beneficial except to those who overemphasize the benefits of sensitivity
  over accuracy" — routine FFR-CT is "unhelpful" in their practice.

## TECHNICAL FAILURE / REJECTION RATES
| Setting | Rejection rate |
|---|---|
| ADVANCE registry (controlled) | **2.9%** (80/2,778) |
| DeFACTO / NXT / PLATFORM | 11% / 13% / 12% |
| **FORECAST RCT** | **15%** (39/259) |
| Real-world consecutive (n=10,621) | **8.4%** |
| Reported range across series | **2.9% - 33%** |
| Fully automated CT-FFR, unselected | ~9% |
| Automated, post-stent-enriched cohorts | **>25%** |

Dominant cause: **motion artifact** (78% of rejections in ADVANCE, 64% in the clinical
cohort). Predictors of automation failure: **presence of stents (P=0.001)** and
**Agatston >967 (P=0.039)**.

=> A rejected case is a DOUBLE loss: no revenue, plus a clinician who waited hours for
   nothing. Repeated rejection destroys ordering habit faster than any single failure.
   Marketing claims ~95-96% acceptance; controlled-trial data says 2.9%; real-world says
   8.4-15%. **The gap between the marketed number and the real-world number is itself a
   measurable, fixable problem.**

## ADOPTION BARRIERS — SYNTHESIS
1. **Reimbursement adequacy is the binding constraint.** ~$1,017 (2025, falling ~14% in 2026)
   against a ~$1,100 list price. England is the natural experiment: centrally funded,
   adoption happened, and the audit found it cost 49% more with no predictive value.
2. **Technical failure rates far exceed trial conditions** (see table).
3. **Site readiness and prep burden.** >=64-detector CT, SCCT-compliant technique,
   nitroglycerin, heart-rate control. Contraindications exclude bypass grafts, stents in
   target vessels, fistulas >1.5mm. Contrast supply and CT capacity named in the 10-K as
   constraints independent of demand. => adoption is structurally capped at large,
   cardiac-CT-mature centers, and the 1,465-account base is growing into progressively
   less-ready sites.
4. **Turnaround time structurally disadvantaged.** Cloud median fell ~12h (2015) -> ~1.6h.
   But **on-site deep-learning models now run in under 8 minutes.** The ~1.6h window rules
   out acute/ED use. 10-K names Siemens, Philips, Canon as having prototyped workstation-based
   CT flow analysis they could bundle with scanner sales.
5. **Workflow friction is per-case, not one-time.** Separate order after CCTA interpretation,
   separate consent in some systems, prior authorization, separate reimbursement processing.
   Giving RoadMap away free with an auto-delivered "case list" flagging candidates is a
   direct admission that ordering friction is the bottleneck.
6. **Cardiologist vs radiologist turf.** Radiologists acquire and interpret the CCTA;
   cardiologists own the referral and the revascularization decision. The sales motion must
   satisfy three constituencies whose economic interests diverge — and the cath-lab pitch
   (+20% net cath lab revenue) is the argument that alienates the payer pitch.
7. **Clinical skepticism is not fringe.** Gibbons (Mayo), the ADVANCE editorialist, Nicol's
   UK audit group, the VA ESP. The 2026 SCCT/SCAI consensus, from FFRCT's most sympathetic
   constituency, NARROWED the indication and warned against test-layering.
8. **Practitioner forum evidence NOT FOUND** — no substantive Reddit/LinkedIn commentary
   retrievable. UNVERIFIED, absence of found evidence only.
9. **Competitive price compression.** 10-K states competitors "commercially launched competing
   plaque analysis products PRIOR TO our launch" and have first-mover advantage — Heartflow
   is the FOLLOWER in plaque.

## BOTTOM LINE (agent's)
Regulatory position solid but unremarkable. The genuine regulatory finding is the MAUDE
record and the root-cause migration from "analyst error" to "automated technology."
Clinical evidence is broad, company-sponsored, and endpoint-soft: it establishes that FFRCT
beats CCTA alone on specificity and reduces diagnostic-only cath. It does NOT establish
improvement in death, MI, angina, or quality of life.
**Payment adequacy — not clinical skepticism, and not FDA — is what actually caps adoption.**
