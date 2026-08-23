-- THE SPINE.
--
-- One immutable row per case. Six conformed keys plus the facts each lens needs.
-- Everything else in this project is a projection over this table.
--
--   case_id · site_id · scanner_key · model_version · case_day · stratum
--
-- Two derivations here carry the weight of the whole design:
--
--   detector_at_scan  Resolved against the site's switch day, not the site's
--                     current detector. Without this, a scanner migration silently
--                     rewrites history.
--
--   delta_ffr /       The counterfactual. `ffr_pre` is FFR recomputed on the
--   crossed_threshold PRE-correction geometry. It is not stored by any upstream
--                     system because nothing ever needed it - the pipeline solves
--                     CFD once, on the final model, because that is the
--                     deliverable. Producing it is a batch re-solve over the label
--                     store. `crossed_threshold` is then the only metric that
--                     answers "did the human change the answer?" rather than
--                     "how long did the human take?".
--
-- Redshift note: DISTKEY(case_id), SORTKEY(case_day, model_version).
-- No PHI: no pixel data, no DICOM UIDs, no accession numbers, no patient
-- identifiers, no raw mesh geometry. No analyst identity, by design.

CREATE OR REPLACE TABLE fct_case_spine AS
SELECT
    c.case_id,
    c.case_day,
    c.site_id,
    s.scanner_make || ' ' || s.scanner_model                    AS scanner_key,
    c.model_version,

    -- detector generation as it was on the day of the scan
    CASE
        WHEN s.detector_switch_day IS NOT NULL
         AND c.case_day >= s.detector_switch_day THEN 'PCD'
        WHEN s.detector_switch_day IS NOT NULL                  THEN 'EID'
        ELSE s.detector_default
    END                                                          AS detector_at_scan,

    -- acquisition
    c.agatston,
    c.heart_rate,
    c.bmi,
    c.stent_present,
    c.nitro_given,
    c.motion_score,

    -- ingest gate
    c.accepted,
    c.reject_reason,

    -- segmentation
    c.autoseg_confidence,

    -- correction (null on rejected cases - they never reach an analyst)
    e.edit_count,
    e.active_min,
    e.idle_min,
    e.active_min + e.idle_min                                    AS analyst_min,
    e.segments_touched,

    -- result and counterfactual
    e.ffr_pre,
    e.ffr_post,
    e.ffr_post - e.ffr_pre                                       AS delta_ffr,
    abs(e.ffr_post - e.ffr_pre)                                  AS abs_delta_ffr,
    CASE WHEN e.ffr_pre IS NULL THEN NULL
         WHEN (e.ffr_pre > 0.80) <> (e.ffr_post > 0.80) THEN 1
         ELSE 0 END                                              AS crossed_threshold,
    CASE WHEN e.ffr_post BETWEEN 0.75 AND 0.80 THEN 1 ELSE 0 END AS grey_zone,
    c.total_plaque_volume_mm3,
    c.turnaround_min,

    -- did the analyst touch a segment where a correction can plausibly move FFR?
    CASE WHEN e.segments_touched IS NULL THEN NULL
         WHEN len(list_filter(e.segments_touched,
              x -> x IN ('LM','pLAD','mLAD','pLCx','pRCA'))) > 0 THEN 1
         ELSE 0 END                                              AS proximal_touched,

    -- Subgroup axes as first-class columns.
    --
    -- These also compose into `stratum` below, but they are materialised
    -- separately so subgroup analysis can query one axis at a time. The
    -- alternative - parsing the composite `stratum` string to recover a band - is
    -- the kind of shortcut that works until someone changes a label.
    CASE WHEN c.agatston < 100  THEN 'CAC<100'
         WHEN c.agatston < 400  THEN 'CAC 100-400'
         WHEN c.agatston < 1000 THEN 'CAC 400-1k'
         ELSE 'CAC>1k' END                                        AS calcium_band,
    CASE WHEN c.motion_score < 0.6 THEN 'motion lo'
         WHEN c.motion_score < 1.4 THEN 'motion md'
         ELSE 'motion hi' END                                      AS motion_band,
    CASE WHEN c.bmi < 25 THEN 'BMI<25'
         WHEN c.bmi < 30 THEN 'BMI 25-30'
         WHEN c.bmi < 35 THEN 'BMI 30-35'
         ELSE 'BMI>=35' END                                        AS bmi_band,
    s.site_class,

    -- stratum: the unit of analysis for the automation frontier
    CASE WHEN c.agatston < 100  THEN 'CAC<100'
         WHEN c.agatston < 400  THEN 'CAC 100-400'
         WHEN c.agatston < 1000 THEN 'CAC 400-1k'
         ELSE 'CAC>1k' END
    || ' / ' ||
    CASE WHEN c.motion_score < 0.6 THEN 'motion lo'
         WHEN c.motion_score < 1.4 THEN 'motion md'
         ELSE 'motion hi' END
    || CASE WHEN c.stent_present = 1 THEN ' / stent' ELSE '' END  AS stratum

FROM raw_cases          c
JOIN dim_site           s USING (site_id)
LEFT JOIN raw_analyst_events e USING (case_id);
