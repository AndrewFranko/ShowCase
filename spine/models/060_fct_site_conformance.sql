-- Site acquisition conformance: expected vs observed rejection.
--
-- Ranking sites by raw rejection rate is unfair and misleading. A site serving
-- heavier patients with more calcified arteries rejects more regardless of how good
-- its technique is; sending a field specialist there wastes the visit and damages
-- the relationship, because the site knows its patients are harder.
--
-- This model computes the rejection rate each site's CASE MIX would predict if it
-- performed like the network, then reports the residual.
--
--     expected_i = SUM over strata of  network_reject_rate(s) * site_share(s)
--     excess_i   = observed_i - expected_i
--
-- Stratification is on bmi_band x calcium_band - patient-intrinsic factors the site
-- cannot control. Motion score and nitroglycerin administration are deliberately
-- EXCLUDED from the stratification, because those are the technique signal itself;
-- adjusting for them would subtract the very thing being measured. Same trap as the
-- confidence column in the release comparison, and just as easy to get backwards.
--
-- Sites below 25 cases are suppressed: a site with 9 cases and 2 rejections has a
-- 22% rate and no information.

CREATE OR REPLACE TABLE fct_site_conformance AS
WITH network AS (
    -- network-wide rejection rate per patient-intrinsic stratum
    SELECT bmi_band, calcium_band,
           1.0 - avg(accepted) AS network_reject_rate,
           count(*)            AS network_n
    FROM fct_case_spine
    GROUP BY 1, 2
),
site_mix AS (
    SELECT site_id, bmi_band, calcium_band,
           count(*)            AS cell_n,
           1.0 - avg(accepted) AS cell_reject_rate
    FROM fct_case_spine
    GROUP BY 1, 2, 3
),
site_totals AS (
    SELECT site_id,
           count(*)                         AS cases,
           sum(1 - accepted)                AS rejections,
           1.0 - avg(accepted)              AS observed_reject_rate,
           median(heart_rate)               AS median_heart_rate,
           avg(nitro_given)                 AS nitro_rate,
           median(motion_score)             AS median_motion,
           avg((motion_score >= 1.4)::INT)  AS high_motion_share
    FROM fct_case_spine
    GROUP BY 1
),
expected AS (
    SELECT m.site_id,
           sum(n.network_reject_rate * m.cell_n) / sum(m.cell_n) AS expected_reject_rate
    FROM site_mix m
    JOIN network n USING (bmi_band, calcium_band)
    GROUP BY 1
)
SELECT
    t.site_id,
    d.site_name,
    d.region,
    d.site_class,
    d.scanner_make,
    d.scanner_model,
    d.first_field_visit_day,
    t.cases,
    t.rejections,
    t.observed_reject_rate,
    e.expected_reject_rate,
    t.observed_reject_rate - e.expected_reject_rate           AS excess_reject_rate,
    -- ratio form, easier to rank on and to explain in a field conversation
    CASE WHEN e.expected_reject_rate > 0
         THEN t.observed_reject_rate / e.expected_reject_rate END AS conformance_ratio,
    t.median_heart_rate,
    t.nitro_rate,
    t.median_motion,
    t.high_motion_share,
    -- how many rejections would be avoided if the site performed to its own case mix
    greatest(0.0, (t.observed_reject_rate - e.expected_reject_rate) * t.cases)
                                                              AS recoverable_cases
FROM site_totals t
JOIN expected  e USING (site_id)
JOIN dim_site  d USING (site_id)
WHERE t.cases >= 25
ORDER BY excess_reject_rate DESC;
