-- Model version dimension.
--
-- A released model version is not just a build artifact, it is a cohort of
-- patients. Giving it a first-class dimension is what makes "did this release
-- change clinical behaviour" a joinable question rather than an archaeology
-- project across Harness, the label store and Smarteeva.

CREATE OR REPLACE TABLE dim_model_version AS
WITH releases(model_version, released_day) AS (
    VALUES ('v4.0.2', 0), ('v4.1.0', 95), ('v4.1.3', 148)
)
SELECT
    model_version,
    released_day,
    LEAD(released_day) OVER (ORDER BY released_day) AS superseded_day,
    ROW_NUMBER()       OVER (ORDER BY released_day) AS release_seq
FROM releases;
