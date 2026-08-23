# HeartFlow — Primary Research Notes (own pass)
Date: 2026-08-22

## Corporate / financial
- Nasdaq: HTFL. IPO August 2025.
- FY2025 revenue $176.0M (+40%). US $160.6M (+41%), intl $15.4M (+26%).
- Q1 2026 revenue $52.6M (+41%); non-GAAP GM 80.5% vs 75.3% PY.
- Q2 2026 revenue $64.1M (+48%); US $59.6M (+51%); OUS $4.5M (~7% of revenue).
  GAAP GM 83.0% vs 75.5% PY. Non-GAAP GM 83.3% vs 75.6%.
- FY2026 guidance raised to $246-250M (+40-42%); non-GAAP GM ~82%.
- Plaque FY26 guidance $29-31M. Q2 Plaque revenue $7.8M (~$4M above expectations).
  Plaque reimbursement coverage ~78%.
- Q2 total global revenue cases 84,491 (+74% YoY). US ~70% of volume.
  NOTE: cases +74% vs revenue +48% => ASP per case is falling. Mix/bundling pressure.
- Cash & equivalents $246.8M at Q2 end. Profitability targeted mid-2028.
- Midterm gross margin target 85%.
- CEO: John Farquhar. CFO: Vikram Verghese.

## THE central strategic thread: "autonomous processing"
- CFO Verghese: "The autonomous processing initiative...underpins our midterm gross margin
  target of 85%, but that is more of a 2027 driver."
- SEC risk language: gross margin expected to increase "as it leverages the AI-based nature of
  its software platform to automate an increasing number of the manual components of its
  production team's process, thereby lowering the cost of revenue per analysis."
- Cost of revenue = "personnel and related expenses, primarily related to the production team."
- => COGS is literally human labor. Margin story = automating humans out of the loop.

## Product line
- RoadMap Analysis (stenosis identification)
- FFRCT Analysis (blood flow / ischemia, CFD-derived)
- Plaque Analysis (plaque characterization/quantification)
- Plaque Staging — launched July 2026, validated in >23,000 patients, up to 16y follow-up
- PCI Navigator — gaining traction, NOT currently charged for, broader 2027 rollout
- Plaque Tracker — 2027 launch, serial CCTA plaque change
- HeartFlow ONE bundle

## TAM expansion into asymptomatic
- US TAM ~$5B -> ~$11B claimed
- 3 RCTs: calcium score population ($3B, Q4 2026 enrollment); prior MI/PCI ($1B, Q4 2026);
  prior plaque ($2B, Q1 2027)
- Exclusive plaque provider for NIH-funded PREEMPT study (1,500 patients)
- CCTA penetration only ~11% of non-invasive testing market

## RISK: DOJ investigation
- October 2025: HeartFlow AND certain employees received Civil Investigative Demands from
  DOJ Civil Division.
- Investigation under federal Anti-Kickback Statute and Civil False Claims Act.
- Focus: "financial and contractual arrangements with providers" and "sales and marketing
  activities."
- Company cooperating; cannot predict duration or outcome; may be material.

## Sites
- Rohnert Park, CA — corporate / IT / ops analytics (4 days/wk in office)
- San Francisco, CA — engineering
- Austin, TX — Operations/Production hub (Imaging Analysts), Post-Market Quality
- (Mountain View is legacy)

## Hiring posture (Greenhouse board, ~68 open roles, Aug 2026)
- OVERWHELMINGLY commercial: ~25 sales/territory roles, clinical field specialists,
  implementation managers, payer relations, medical affairs.
- Engineering roles are scarce / mostly closed. Post-IPO commercial land grab.
- Notable non-sales openings:
  - IT Director, Data Services and AI Enablement (Rohnert Park, $220-270k)
  - Operations Data Analyst (Rohnert Park/Austin, $108-141k / $89-116k)
  - Imaging Analyst - Remote, Austin ($24.50-25.50/hr)
  - Product Investigator (Austin)
  - Director - Post Market Quality (Austin)
  - Senior Device Quality Engineer (Bay Area)
  - Associate Clinical SAS Programmer/Junior Statistician

## STACK EVIDENCE (from job postings — quoted)

### Senior Test Engineer (SF, $165-205k) — the closest match to the user
- "WebGL-based 3D Web Viewer and Clinical/CaseOps UIs using Playwright"
- Selenium, WebDriver, Playwright; Python + TS/JS/Java/C#
- API testing: REST Assured, Postman, Karate, Pact.io
- "DICOM and HL7 validation"
- CI/CD: GitHub Actions, Harness. Cloud: AWS.
- "Creating regression tests for the ML pipeline with golden-dataset validation"
- "Performing tool validation per internal QMS procedures"
- "Leading post-deployment testing including production verification"
- "Champion an AI-first automation strategy" using AI-assisted authoring and triage
- Traceability tooling: Ketryx, Jama, Polarion
- "Coordinating offshore/contractor test engineers"
- Standards: ISO 13485, IEC 62304, ISO 14971, 21 CFR Part 820
- Desired: "Complex visualization validation (3D models, overlays, measurements)",
  "Test dataset generation (synthetic, anonymized, adversarial)",
  perf tools k6/Locust/JMeter/Gatling

### Staff Software Engineer, Algorithms ($146-241k)
- C++ and Python, 10+ yrs
- AWS; Terraform, Chef/Ansible, GitHub Actions
- "Strong hands-on experience with containerization (Docker, Kubernetes)"
- "Architect scalable and performant algorithmic solutions... focus on image processing"
- Preferred: medical imaging, computer vision, 3D computational geometry

### Senior Software Engineer, Scientific Computing & Algorithms (SF, $170-220k)
- 8+ yrs modern C++ (C++11+), 5+ yrs Python, 3+ yrs AWS
- CI/CD: Jenkins, GitHub, AWS CodeBuild/CodePipeline
- "algorithmic pipelines, test frameworks and CI/CD pipelines"
- Desired: TypeScript, Rust, **"interactive 3D graphics (C++/Windows)"**
- "cross-functional efforts with Product team, Process Engineering team"
- => STRONG SIGNAL: an internal C++/Windows interactive 3D desktop app exists.
     Almost certainly the Imaging Analyst segmentation/mesh-editing tool.

### Senior Software Engineer (backend) / Software Engineer III
- "cloud-based services and modern web applications that power the next generation of
  Heartflow technologies, including a new orchestration pipeline"
- Cross-functional with SW Eng, PM, QA, Usability Designers, Process Engineers, Regulatory

### IT Director, Data Services and AI Enablement (Rohnert Park, $220-270k)
- AWS + Redshift; orchestration via **Dagster**; semantic layer **Cube Cloud**
- Enterprise apps: Salesforce, NetSuite, ADP
- BI: migrating **Domo -> Power BI**
- "ingestion (batch, streaming, APIs), transformation (ETL/ELT), modeling, storage,
  integration, and delivery of data products"
- drives internal "AI-readiness" for ML and generative AI workloads

### Operations Data Analyst
- Tools: **Tableau, Excel, Google Sheets** (no SQL/Python/Snowflake mentioned)
- Integrates **ADP** and **Smarteeva** (complaint mgmt / post-market surveillance)
- "identifying process bottlenecks and monitoring changes with Process Engineering"
- => Ops analytics is running on spreadsheets. Three BI tools in play (Domo, Power BI,
     Tableau). Fragmented.

### Imaging Analyst (Austin, $24.50-25.50/hr, Operations - Production)
- "generate custom 3D computer models that are used for fluid dynamic simulations"
- "Visual inspection and verification of image data quality and 3D models"
- "Testing new product versions and process updates"
- Application asks about AutoCAD, Blender, Maya, CAD proficiency
- "flexibility of work hours... including some holidays and weekends"
- Must live within 1 hour of Austin office
- => Confirms human-in-the-loop 3D model production line. This is the COGS.
