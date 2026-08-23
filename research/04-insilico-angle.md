# The in-silico / virtual imaging trial angle (own research)
This is the differentiated pitch — it fuses the user's 3D simulator background with
Heartflow's two hardest live problems (autonomous processing validation, PCD-CT revalidation).

## Prior art that makes it credible (not speculative)
- **XCAT phantom** (4D extended cardiac-torso, Duke): anatomically accurate human anatomy
  with physiologically plausible cardiac and respiratory motion; generates time-resolved
  volumetric CT data with **known ground truth**.
- **Sauer et al., Medical Physics 2024** — "Development of physiologically-informed
  computational coronary artery plaques for use in virtual imaging trials."
  Micron-resolution plaque histology -> synthesized plaques validated for anatomical and
  physiological realism -> inserted into XCAT cardiac models to simulate CAD states.
  https://aapm.onlinelibrary.wiley.com/doi/10.1002/mp.16959
- **DukeSim** — physics-based CT simulator. "Cardiac CT reconstruction for **vendor-neutral**
  virtual imaging trials" (SPIE 2022): dynamic virtual patients + CT simulator -> realistic
  retrospectively-gated helical cardiac CT projection data.
- SPIE 2021: "Optimization of CT angiography using physiologically-informed computational
  plaques, dynamic XCAT phantoms, and physics-based CT simulation."
- Review: "Virtual clinical trials in medical imaging" (PMC7148435).

## Regulatory framework that makes it submittable
- **ASME V&V 40-2018** — FDA-recognized consensus standard; risk-based framework for
  establishing credibility requirements of physics-based computational models.
- **FDA final guidance: "Assessing the Credibility of Computational Modeling and Simulation
  in Medical Device Submissions"** — 8 categories of credibility evidence; three validation
  types incl. population-based validation.
- **In Silico Clinical Trials** — virtual cohorts of simulated patients with realistic
  anatomical/physiological variability representing the indicated population.

## Why this is exactly Heartflow's shaped hole
1. **Autonomous processing needs stratified evidence.** To remove the Imaging Analyst you
   must show the automated path is equivalent-or-better across case difficulty: calcium
   burden, motion, heart rate, stents, BMI, scanner vendor, dose. Real paired
   invasive-FFR data is scarce, expensive, and biased toward patients referred to cath.
   Synthetic cases give unlimited stratified coverage with known ground truth and no PHI.
2. **Photon-counting CT re-validation.** Radiology 2025 showed PCD CT measures ~1/3 less
   total plaque volume than EID CT and that EID-derived HU ranges "cannot be directly
   translated." The clean way to characterise that shift is to image the SAME synthetic
   anatomy through simulated EID vs PCD physics and measure the delta directly. Nobody can
   do that with real patients.
3. **Test data generation is already on their wish list.** The Senior Test Engineer JD lists
   "Test dataset generation (synthetic, anonymized, adversarial)" as a desired qualification.
4. **No PHI.** Synthetic cohorts sidestep the data-governance friction that slows every
   medical imaging ML team.
5. **It is a moat they can own.** The CFD algorithm is commoditized (SimVascular, Siemens
   cFFR, DL surrogates). Evidence infrastructure is not.
