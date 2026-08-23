-- Hazard signature evaluation.
--
-- This is the table that turns ISO 14971 residual risk from an assertion in a
-- document into a measurement against production.
--
-- Each hazard in the risk file carries a `signature`: a predicate over case facts,
-- authored by Quality, reviewed, and version-controlled alongside the hazard text.
-- Evaluating it continuously means "residual risk after controls" has a number and
-- a trend, per model version, instead of a paragraph.
--
-- A match is NOT a harm. It means the case realised the conditions the hazard
-- describes. The ratio of matches to complaints is itself informative: a signature
-- matching thousands of cases and zero complaints is probably too loose and should
-- go back to Quality.

CREATE OR REPLACE TABLE fct_hazard_match AS
WITH sigs AS (
    SELECT
        s.case_id,
        s.model_version,
        s.case_day,
        s.site_id,
        s.stratum,
        -- H-014: correction widened a proximal vessel and the case was released
        --        as non-ischemic. The dominant real-world MAUDE mechanism.
        CASE WHEN s.accepted = 1
              AND s.proximal_touched = 1
              AND s.delta_ffr > 0.045
              AND s.ffr_post > 0.80 THEN 1 ELSE 0 END AS "H-014",
        -- H-022: analysed despite image quality that should have gated it
        CASE WHEN s.accepted = 1
              AND s.motion_score >= 1.6 THEN 1 ELSE 0 END AS "H-022",
        -- H-031: stent in a target vessel, material correction, released anyway
        CASE WHEN s.accepted = 1
              AND s.stent_present = 1
              AND s.proximal_touched = 1
              AND abs(s.delta_ffr) > 0.04 THEN 1 ELSE 0 END AS "H-031",
        -- H-047: plaque reported after a detector migration at the site
        CASE WHEN s.accepted = 1
              AND ds.detector_switch_day IS NOT NULL
              AND s.case_day >= ds.detector_switch_day THEN 1 ELSE 0 END AS "H-047"
    FROM fct_case_spine s
    JOIN dim_site ds USING (site_id)
)
SELECT case_id, model_version, case_day, site_id, stratum, hazard_id
FROM sigs
UNPIVOT (matched FOR hazard_id IN ("H-014", "H-022", "H-031", "H-047"))
WHERE matched = 1;
