-- Function: get_app_status_summary
-- Purpose: Dashboard metric "Summary of applications configured and their status" — one row
-- per application, its most recent poll only. Companion/inventory view to get_app_uptime.sql
-- (which answers "how much uptime has this app had"); this answers "what apps exist and what
-- are they doing right now."
--
-- status_bucket reuses get_app_uptime.sql's EXACT status mapping, so colour-coding stays
-- consistent across this whole function suite:
--   RUNNING                            -> UP
--   STOPPED, HALT, CRASH, CREATED      -> DOWN
--   anything else (DEPLOYED, COMPLETED,
--   QUIESCED, UNKNOWN, etc.)          -> OTHER
--
-- Requires: Include App Detail (IncludeAppDetail, default true). isRecoveryEnabled /
-- checkpointStatus / deploymentOn additionally need Include App Describe Detail / Include App
-- Status Detail for full accuracy (see striim_mon_appdetail's own column docs) — if those are
-- off, the columns simply come through NULL, not wrong.
--
-- sourceTypes / targetTypes — READ THIS BEFORE EXPECTING FULL COVERAGE.
-- StriimWatcher does not capture one clean "adapter type" field keyed directly by appName.
-- Every table in this deployment's schema was checked against real data in this `Vivek`
-- dataset before writing this — four signals are combined, each real and structured, none
-- guessed from names:
--   1. striim_mon_lee.sourceType/targetType — a real adapter-type STRING when present (e.g.
--      'MSJet', 'BigQueryWriter'), but only 541/9182 rows (90d) have a non-empty sourceType
--      and 2727/9182 a non-empty targetType, across 11 distinct component names total.
--      Bridged to appName via (appName, componentName) from striim_mon_source_information /
--      striim_mon_target_information — NOT via LEE's own sourceApp/targetApp, separately
--      confirmed near-useless here (541/9182 populated, resolving to exactly 1 distinct app)
--      — same bridging technique get_app_table_denormalized_view.sql /
--      get_kafka_io_rate_summary.sql already use for the identical reason.
--   2. striim_mon_ojet_metrics presence — StriimWatcher only ever populates this table for
--      apps whose source actually uses the OJet (Oracle JET / LogMiner) reader, so an app
--      having ANY row here is itself a reliable "source type = OJet" signal, not an
--      inference from naming. Adds 10 distinct apps in this dataset (vs. 1 from LEE alone).
--   3. striim_mon_oracle_open_trx presence — same idea, one level less specific: populated
--      for Oracle CDC sources generally. In this dataset its 8 apps are already a subset of
--      (2)'s 10, so it only contributes when an app has open Oracle transactions tracked but
--      didn't also get an OJet-metrics row — kept for deployments where that isn't true,
--      labelled the more conservative 'Oracle CDC' rather than 'OJet' since it doesn't
--      confirm the specific reader variant.
--   4. striim_mon_datawarehouse_detail.target_adaptername — reliable where present (confirmed
--      'BigQueryWriter'/'SnowflakeWriter' values), the same field
--      get_bq_writer_status_summary.sql already keys off. 5 apps in this dataset.
-- Checked and ruled out: striim_mon_component_output / striim_mon_tql_history /
-- striim_mon_table_column_detail / striim_mon_file_lineage don't exist in this deployment
-- (their Include* settings are off); striim_mon_source_information/target_information are
-- fully populated but carry no type field at all (jsonoutput is the `mon` command's status
-- tree, not a `describe` with an adapter class); striim_mon_checkpoint_history's
-- sourcePositionSummary/targetPositionSummary are NULL for every row checked here.
-- Net result in this dataset: ~16 of 57 apps get at least one detected type, up from 6 with
-- LEE/datawarehouse alone — real progress, not full coverage. A NULL here means "not detected
-- from any of the four signals above," never "no source/target configured." Closing the
-- remaining gap would need Striim itself to expose adapter type in StriimWatcher's output;
-- nothing else currently collected in this project's dataset carries it.
--
-- Usage: SELECT * FROM `Vivek.get_app_status_summary`(1);   -- latest poll within the last day
-- Dataset: Vivek

CREATE OR REPLACE TABLE FUNCTION `Vivek.get_app_status_summary`(days_back INT64)
RETURNS TABLE<
  clusterName STRING,
  appName STRING,
  appStatus STRING,
  status_bucket STRING,
  isBackpressured BOOL,
  checkpointStatus STRING,
  isRecoveryEnabled BOOL,
  totalInput INT64,
  totalOutput INT64,
  deploymentOn STRING,
  latestActivity TIMESTAMP,
  latest_batchdate TIMESTAMP,
  sourceTypes STRING,
  targetTypes STRING
>
AS (
WITH AppHistory AS (
  SELECT
    smd.appName,
    rh.clusterName,
    smd.batchdate,
    smd.appStatus,
    smd.isBackpressured,
    smd.checkpointStatus,
    smd.isRecoveryEnabled,
    smd.totalInput,
    smd.totalOutput,
    smd.deploymentOn,
    smd.latestActivity,
    ROW_NUMBER() OVER (PARTITION BY smd.appName ORDER BY smd.batchdate DESC) AS rn
  FROM `Vivek.striim_mon_appdetail` AS smd
  INNER JOIN `Vivek.striim_mon_table_runhistory` AS rh
    ON smd.batchdate = rh.batchdate
  WHERE smd.batchdate >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL days_back DAY)
),
-- Bridge: component name -> appName, from the platform's own per-app polling (reliable),
-- not from LEE's own best-effort sourceApp/targetApp (confirmed unreliable above).
SourceComponentApp AS (
  SELECT DISTINCT appName, componentName
  FROM `Vivek.striim_mon_source_information`
  WHERE batchdate >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL days_back DAY)
),
TargetComponentApp AS (
  SELECT DISTINCT appName, componentName
  FROM `Vivek.striim_mon_target_information`
  WHERE batchdate >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL days_back DAY)
),
LeeTypes AS (
  SELECT sourceName, sourceType, targetName, targetType
  FROM `Vivek.striim_mon_lee`
  WHERE batchdate >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL days_back DAY)
),
-- Signal 2: OJet-reader presence — see header comment.
OjetApps AS (
  SELECT DISTINCT appName
  FROM `Vivek.striim_mon_ojet_metrics`
  WHERE batchdate >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL days_back DAY)
),
-- Signal 3: generic Oracle-CDC presence, only for apps signal 2 didn't already cover (avoids
-- double-labelling the same app as both 'OJet' and the less-specific 'Oracle CDC').
OracleOpenTrxOnlyApps AS (
  SELECT DISTINCT appName
  FROM `Vivek.striim_mon_oracle_open_trx`
  WHERE batchdate >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL days_back DAY)
    AND appName NOT IN (SELECT appName FROM OjetApps)
),
SourceTypesFromLee AS (
  SELECT sca.appName, lt.sourceType AS sourceType
  FROM SourceComponentApp sca
  INNER JOIN LeeTypes lt ON sca.componentName = lt.sourceName
  WHERE lt.sourceType IS NOT NULL AND lt.sourceType != ''
),
SourceTypesFromOjet AS (
  SELECT appName, 'OJet' AS sourceType FROM OjetApps
),
SourceTypesFromOracleTrx AS (
  SELECT appName, 'Oracle CDC' AS sourceType FROM OracleOpenTrxOnlyApps
),
SourceTypesByApp AS (
  SELECT appName, STRING_AGG(DISTINCT sourceType, ', ' ORDER BY sourceType) AS sourceTypes
  FROM (
    SELECT * FROM SourceTypesFromLee
    UNION ALL SELECT * FROM SourceTypesFromOjet
    UNION ALL SELECT * FROM SourceTypesFromOracleTrx
  )
  GROUP BY appName
),
-- Target type: LEE-bridged (signal 1) and datawarehouse_detail (signal 4) — unioned per app
-- since either being present is useful and they don't overlap in practice.
TargetTypesFromLee AS (
  SELECT tca.appName, lt.targetType AS targetType
  FROM TargetComponentApp tca
  INNER JOIN LeeTypes lt ON tca.componentName = lt.targetName
  WHERE lt.targetType IS NOT NULL AND lt.targetType != ''
),
TargetTypesFromDW AS (
  SELECT appName, target_adaptername AS targetType
  FROM `Vivek.striim_mon_datawarehouse_detail`
  WHERE batchdate >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL days_back DAY)
    AND target_adaptername IS NOT NULL AND target_adaptername != ''
),
TargetTypesByApp AS (
  SELECT appName, STRING_AGG(DISTINCT targetType, ', ' ORDER BY targetType) AS targetTypes
  FROM (
    SELECT * FROM TargetTypesFromLee
    UNION ALL SELECT * FROM TargetTypesFromDW
  )
  GROUP BY appName
)
SELECT
  ah.clusterName,
  ah.appName,
  ah.appStatus,
  CASE
    WHEN UPPER(TRIM(ah.appStatus)) = 'RUNNING' THEN 'UP'
    WHEN UPPER(TRIM(ah.appStatus)) IN ('STOPPED', 'HALT', 'CRASH', 'CREATED') THEN 'DOWN'
    ELSE 'OTHER'
  END AS status_bucket,
  ah.isBackpressured,
  ah.checkpointStatus,
  ah.isRecoveryEnabled,
  ah.totalInput,
  ah.totalOutput,
  ah.deploymentOn,
  ah.latestActivity,
  ah.batchdate AS latest_batchdate,
  st.sourceTypes,
  tt.targetTypes
FROM AppHistory ah
LEFT JOIN SourceTypesByApp st ON ah.appName = st.appName
LEFT JOIN TargetTypesByApp tt ON ah.appName = tt.appName
WHERE ah.rn = 1
ORDER BY ah.clusterName, ah.appName
);

-- Example:
-- SELECT * FROM `Vivek.get_app_status_summary`(1);
