-- Site dimension.
--
-- Slowly-changing in one respect that matters: detector generation. A site that
-- migrates from an energy-integrating detector to photon-counting changes the
-- meaning of every plaque measurement it produces afterwards, with no error
-- surfaced anywhere. `detector_switch_day` is what lets the case fact resolve
-- detector-at-scan-time rather than detector-today.
--
-- Redshift note: this is a small dimension. DISTSTYLE ALL, SORTKEY(site_id).

CREATE OR REPLACE TABLE dim_site AS
SELECT
    site_id,
    site_name,
    region,
    scanner_make,
    scanner_model,
    detector_default,
    detector_switch_day,
    is_office,
    CASE WHEN is_office = 1 THEN 'office' ELSE 'hospital' END AS site_class,
    len(field_visit_days)                                     AS field_visit_count,
    CASE WHEN len(field_visit_days) > 0
         THEN field_visit_days[1] END                         AS first_field_visit_day
FROM raw_sites;
