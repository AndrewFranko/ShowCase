# Strategic analysis (own synthesis, pre-agent-integration)

## The one insight that drives everything

Heartflow's cost of revenue is **human labor**. Imaging Analysts in Austin at ~$25/hr
build and correct the 3D coronary models that feed the CFD simulation. The company has
told investors, in SEC filings and on the Q2'26 call, that its path from 83% to the
**85% midterm gross margin target** runs through the **"autonomous processing initiative"**
— automating the manual components of the production team's process.

That initiative is the single most investor-visible engineering program in the company,
and it is a **2027 driver**, i.e. it is being built right now.

### Why that is much harder than it sounds

Removing the analyst from the loop is not merely an ML accuracy problem. The analyst is
currently functioning as an **undocumented safety control**. Every case gets human visual
inspection of image quality and of the 3D model before a diagnostic result leaves the
building. Deleting that control means:

1. **Regulatory**: the automated path must be shown equivalent-or-better to the
   human-corrected path. Realistically this is a PCCP and/or new 510(k) evidence exercise,
   stratified by case difficulty (calcium burden, motion artifact, stents, heart rate,
   scanner vendor, BMI).
2. **Risk management (ISO 14971)**: the hazard analysis changes. A silently wrong mesh now
   propagates to a clinician-facing FFR value with no human gate. You need an
   **abstention / confidence mechanism** — the pipeline must know when it does not know and
   escalate to a human, and that triage must itself be validated.
3. **Measurement**: you cannot automate what you have not instrumented. Right now Ops
   analytics runs on **Tableau + Excel + Google Sheets**. There is no evident per-case,
   per-edit telemetry layer describing where analysts actually spend their time and where
   the auto-segmentation actually fails.

**Point 3 is the gap, and it is the wedge.** It is unglamorous, it is not on the critical
path of any product release, it is low regulatory risk (non-product software under the
FDA's Computer Software Assurance final guidance, Sept 2025), and *nothing else in the
autonomous processing program can be prioritized correctly without it.*

## Candidate weak spots (own observations, to be cross-checked against agent findings)

1. **COGS is people.** Cases +74% YoY (84,491 in Q2'26) while headcount-based COGS must
   scale sub-linearly to hit 85%. Also they must hire and train analysts to full
   productivity — a stated margin drag.
2. **Revenue per case is falling.** Q2'25 ~$891/case -> Q2'26 ~$759/case (~-15%).
   Bundling (HeartFlow ONE), free PCI Navigator, and Plaque-alongside-FFRCT counting.
   Monetisation per case down => unit cost reduction matters more, not less.
3. **DOJ CIDs (Oct 2025)** — Anti-Kickback Statute + False Claims Act, aimed at provider
   financial/contractual arrangements and sales & marketing conduct. Company and
   *individual employees* served. This is the largest non-operational risk on the books
   and it lands squarely on a commercial org that is simultaneously being scaled hard.
4. **Commercial-heavy hiring.** ~68 open roles, dominated by sales/territory/field.
   Very few open engineering seats. Engineering is being asked to deliver the margin
   story with a flat-ish team.
5. **Fragmented internal data stack.** Domo -> Power BI migration, Tableau in Ops,
   Excel/Sheets in the middle, Redshift + Dagster + Cube Cloud being stood up, Salesforce
   + NetSuite + ADP + Smarteeva around the edges. They are hiring an IT Director at
   $220-270k to fix exactly this. It is not fixed today.
6. **Three UI surfaces to test, one of them WebGL 3D.** Clinical viewer, CaseOps UI, and an
   internal C++/Windows interactive 3D tool. 3D/visual regression testing is the hardest
   thing to automate and the most likely to be under-covered.
7. **Test org leans on offshore contractors** ("coordinating offshore/contractor test
   engineers") — a classic signal of test coverage bought by headcount rather than by
   infrastructure.
8. **International is 7% of revenue** and growing slower than US. Effectively a US company.
9. **Free product as a strategic wedge (PCI Navigator)** — good land-grab, but it adds
   compute and support cost with no revenue line.
10. **Product surface is expanding fast** (Plaque Staging shipped Jul'26, Plaque Tracker
    2027, PCI Navigator 2027, 3 new RCTs enrolling) while the same pipeline and the same
    test infrastructure must carry all of it.

## Regulatory / standards context relevant to the pitch
- **FDA Computer Software Assurance final guidance, issued 23-24 Sept 2025** — risk-based,
  least-burdensome validation of *production and quality system software*. Supersedes
  Section 6 of the 2002 General Principles of Software Validation. This is what makes
  building internal tools cheap now. Explicitly relevant: the Test Engineer JD requires
  "tool validation per internal QMS procedures".
- **IEC 62304 / ISO 13485 / ISO 14971 / 21 CFR 820** — named in their own JDs.
- **Autonomy precedent**: IDx-DR (now LumineticsCore) De Novo, 2018, product code PIB —
  the only real FDA precedent for a fully autonomous AI diagnostic. Useful framing, but
  note Heartflow's autonomy question is *production-side* (removing an internal analyst),
  not *clinical-side* (the physician still reads the result).

## User -> Heartflow skill mapping (draft)

| User's background | Heartflow's live problem |
|---|---|
| 3D simulators for surgical robotics | Internal C++/Windows interactive 3D analyst tool; WebGL 3D web viewer; synthetic anatomy generation for test data |
| Python test infrastructure | Playwright/Selenium E2E, golden-dataset ML regression, CI/CD on GitHub Actions + Harness, AWS |
| Insulin pumps (closed-loop, Class C) | Removing a human from a loop safely: abstention/confidence gating, hazard analysis, fail-safe design |
| Deeply embedded / safety-critical | IEC 62304, ISO 14971, traceability, V&V discipline under audit |
| Surgical robotics HIL test rigs | "Case-in-the-loop" simulation rig: replay/synthesize cases through the pipeline at scale |
