-- Complaints, resolved onto the spine.
--
-- This join is the one that costs Heartflow a week today: a complaint lives in
-- Smarteeva, the case lives in the ops store, the correction lives in the label
-- store, and the hazard lives in Ketryx. Landing them on one grain means a
-- complaint arrives already carrying its stratum, its model version, and the
-- hazard it realised - so the question "is this an anecdote or a signal?" is
-- answered on arrival rather than after an investigation.
--
-- Note the re-identification boundary: `case_id` here is a surrogate. Mapping it
-- back to a patient requires the separate, access-controlled key store that only
-- Post-Market Quality can traverse, because complaint investigation legally
-- requires it and nothing else does.

CREATE OR REPLACE TABLE fct_complaint AS
SELECT
    k.complaint_id,
    k.case_id,
    k.complaint_day,
    k.complaint_type,
    k.mdr_reportable,
    k.status,
    k.complaint_day - s.case_day        AS reporting_lag_days,
    s.case_day,
    s.site_id,
    s.model_version,
    s.stratum,
    s.detector_at_scan,
    s.ffr_pre,
    s.ffr_post,
    s.crossed_threshold,
    -- the hazard this complaint's case realised, if any
    (SELECT MIN(h.hazard_id)
       FROM fct_hazard_match h
      WHERE h.case_id = k.case_id)      AS hazard_id
FROM raw_complaints k
JOIN fct_case_spine s USING (case_id);
