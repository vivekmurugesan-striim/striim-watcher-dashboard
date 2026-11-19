-- Function: get_node_resource_trend
-- Purpose: Dashboard metric "Striim VM node — Status (Up/Down), CPU, Memory" — TREND chart
-- (hourly CPU + free-memory trend per node, companion to get_node_status.sql's latest-poll
-- snapshot).
--
-- CPU is cpurate (per-core, not normalized to 100% total — an 8-core node can show up to
-- 800%, same convention used everywhere else in StriimWatcher, see get_node_status.sql).
-- Hourly-bucketed AVG(cpurate) so a multi-day window doesn't return one point per 5-minute
-- poll.
--
-- Memory (freemem): confirmed against real data in this project's own `Vivek` dataset that
-- every non-empty reading is formatted as a plain `<number>Gb` string (5556/5556 non-empty
-- rows checked — no Mb/Tb/KB variants observed here). avg_freemem_gb parses that with
-- SAFE.PARSE_NUMERIC + REGEXP_REPLACE to strip the unit, returning NULL (not an error) for
-- anything that doesn't match — including the empty string this table sometimes has — rather
-- than assuming the format is universal across every StriimWatcher deployment. latest_freemem
-- is still returned as the raw string too, for display when the parse comes back NULL.
--
-- Requires: Include Node Monitor + Include Node Cluster (both default true).
--
-- Usage: SELECT * FROM `Vivek.get_node_resource_trend`(1);   -- last 1 day, hourly buckets
-- Dataset: Vivek

CREATE OR REPLACE TABLE FUNCTION `Vivek.get_node_resource_trend`(days_back INT64)
RETURNS TABLE<
  clusterName STRING,
  nodeName STRING,
  hour TIMESTAMP,
  avg_cpurate FLOAT64,
  avg_freemem_gb FLOAT64,
  sample_count INT64,
  latest_freemem STRING
>
AS (
WITH NodeHistory AS (
  SELECT
    nc.nodename AS nodeName,
    rh.clusterName,
    nc.batchdate,
    TIMESTAMP_TRUNC(nc.batchdate, HOUR) AS hour,
    nc.cpurate,
    nc.freemem,
    -- NULL (not 0, not an error) whenever freemem isn't exactly `<number>Gb` — e.g. the
    -- empty-string rows this table has, or any future unit this project hasn't seen yet.
    SAFE_CAST(
      REGEXP_EXTRACT(nc.freemem, r'^([0-9]+\.?[0-9]*)Gb$') AS FLOAT64
    ) AS freemem_gb
  FROM `Vivek.striim_mon_node_cluster` AS nc
  INNER JOIN `Vivek.striim_mon_table_runhistory` AS rh
    ON nc.batchdate = rh.batchdate
  WHERE nc.batchdate >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL days_back DAY)
)
SELECT
  clusterName,
  nodeName,
  hour,
  -- cpurate is NUMERIC; explicit CAST to FLOAT64 to match the declared return type rather
  -- than relying on implicit coercion at the table-function boundary.
  CAST(ROUND(AVG(cpurate), 2) AS FLOAT64) AS avg_cpurate,
  ROUND(AVG(freemem_gb), 2) AS avg_freemem_gb,
  COUNT(*) AS sample_count,
  ARRAY_AGG(freemem ORDER BY batchdate DESC LIMIT 1)[OFFSET(0)] AS latest_freemem
FROM NodeHistory
GROUP BY clusterName, nodeName, hour
ORDER BY nodeName, hour
);

-- Example:
-- SELECT * FROM `Vivek.get_node_resource_trend`(1);
