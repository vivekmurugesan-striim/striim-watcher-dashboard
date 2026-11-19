-- Function: get_app_status_history
-- Purpose: Dashboard metric "Historical data and trends on application status" — one row per
-- application per HOUR (same hourly-downsampling technique as
-- get_non_running_hourly_status.sql), but UNSCOPED (any adapter type, not just
-- OJet/BigQueryWriter) and INCLUDING RUNNING hours — this is what actually draws a
-- continuous status-over-time timeline for one app, where get_non_running_hourly_status.sql
-- deliberately only logs problem states for a narrower app scope.
--
-- Pass a specific app_name to scope to one application (the normal dashboard drill-down use),
-- or NULL to return every application's hourly status history (same NULL-means-all convention
-- get_tables_by_app.sql already uses) — be mindful of result size with NULL over a long
-- days_back window.
--
-- Caveat: an hour where StriimWatcher itself didn't poll produces no row for that hour — this
-- doesn't fill gaps with a placeholder, same caveat get_non_running_hourly_status.sql carries.
--
-- Usage:
--   SELECT * FROM `Vivek.get_app_status_history`('admin.NAV_CDC', 7);  -- one app, last 7 days
--   SELECT * FROM `Vivek.get_app_status_history`(NULL, 7);              -- every app
-- Dataset: Vivek

CREATE OR REPLACE TABLE FUNCTION `Vivek.get_app_status_history`(app_name STRING, days_back INT64)
RETURNS TABLE<
  clusterName STRING,
  appName STRING,
  hour TIMESTAMP,
  appStatus STRING,
  batchdate TIMESTAMP
>
AS (
WITH AppHistory AS (
  SELECT
    smd.appName,
    rh.clusterName,
    smd.batchdate,
    TIMESTAMP_TRUNC(smd.batchdate, HOUR) AS hour,
    UPPER(TRIM(smd.appStatus)) AS appStatus,
    ROW_NUMBER() OVER (
      PARTITION BY smd.appName, TIMESTAMP_TRUNC(smd.batchdate, HOUR)
      ORDER BY smd.batchdate DESC
    ) AS rn
  FROM `Vivek.striim_mon_appdetail` AS smd
  INNER JOIN `Vivek.striim_mon_table_runhistory` AS rh
    ON smd.batchdate = rh.batchdate
  WHERE smd.batchdate >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL days_back DAY)
    AND (app_name IS NULL OR smd.appName = app_name)
)
SELECT
  clusterName,
  appName,
  hour,
  appStatus,
  batchdate
FROM AppHistory
WHERE rn = 1
ORDER BY appName, hour
);

-- Example:
-- SELECT * FROM `Vivek.get_app_status_history`('admin.NAV_CDC', 7);
