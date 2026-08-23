# Unit economics of the production line (derived estimates — label as estimates)

## Inputs (reported)
- Q2 2026 revenue: $64.1M; GAAP gross margin 83.0% => cost of revenue ~= $10.9M
- Q2 2026 global revenue cases: 84,491 (+74% YoY)
- Median turnaround time: < 1.5 hours (company claim, "90 minutes")
- Case acceptance rate: ~95% of submitted CCTAs accepted (=> ~5% rejected, image quality)
- Cost of revenue is "personnel and related expenses, primarily related to the production team"
- Imaging Analyst wage: $24.50-$25.50/hr (Austin)
- Midterm gross margin target: 85%

## Derived
- Revenue per revenue-case: Q2'26 $64.1M / 84,491 = **~$759**
  Q2'25 implied: ($64.1/1.48)M / (84,491/1.74) = $43.3M / 48,558 = **~$891**
  => revenue per case fell **~15% YoY**. Bundling (HeartFlow ONE), free PCI Navigator,
     and multi-product cases on one scan. NOTE: "revenue cases" may count FFRCT and Plaque
     separately on the same patient scan, so this is a mix effect, not a price cut.
- Cost per revenue-case: $10.9M / 84,491 = **~$129**
- Throughput: 84,491 / ~91 days = **~930 cases/day**, sustained, against a 90-minute median SLA.
  => explains "flexibility of work hours... including some holidays and weekends" in the
     Imaging Analyst posting. This is a 24/7 real-time production line, not a batch shop.

## What 85% gross margin actually demands
- At 85% GM, cost of revenue = 15% of revenue = $9.6M on Q2'26 revenue
- => cost per case must fall from ~$129 to **~$114**, a **~12% reduction**
- But revenue per case is *also* falling (~15% YoY). If that continues, holding 85% GM
  requires cost-per-case to fall roughly in step with revenue-per-case **on top of** the
  12%. The real target is closer to a **25-30% reduction in cost per case over ~18 months**,
  while case volume grows ~70%/yr.
- You cannot hire your way to that. It has to come out of automation — which is exactly
  what the company has told investors.

## The 5% rejection rate is a second, unclaimed pool of value
- ~5% of submitted CCTAs are rejected for image quality.
- Every rejection = wasted analyst triage time + a customer-visible failure + a lost
  billable case + a patient who may need a repeat scan or a different test.
- At ~930 accepted cases/day, ~49 rejected cases/day are being triaged and bounced.
- A **pre-flight image-quality check that runs at the imaging site before upload** converts
  a post-hoc rejection into a re-scan while the patient is still on the table.
  This is a well-bounded, non-diagnostic, low-regulatory-risk ML problem.
