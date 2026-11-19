# Dashboard-Queries additions

Three new BigQuery table functions this app depends on, written in the exact style and
conventions of the existing [`Dashboard-Queries/`](../../Dashboard-Queries/) suite (same
dataset, same docstring format, same `CREATE OR REPLACE TABLE FUNCTION` pattern). They are
kept here, inside `striim-watcher-dashboard/`, so this whole feature reviews and ships as one
unit — promote them once reviewed:

1. Deploy each file the same way as every other file in the suite:
   ```bash
   bq query --use_legacy_sql=false < get_node_resource_trend.sql
   bq query --use_legacy_sql=false < get_app_status_summary.sql
   bq query --use_legacy_sql=false < get_app_status_history.sql
   ```
2. Copy the three `.sql` files up into `../../Dashboard-Queries/` so they live alongside their
   siblings.
3. Append a row for each to `../../Dashboard-Queries/README.md`'s tile-mapping table and
   summary table, and a short section each, matching the format already used there.

## What each one adds (none of this exists in the base suite)

| Function | Fills the gap in | Depends on |
|---|---|---|
| `get_node_resource_trend(days_back)` | `get_node_status`/`get_node_status_summary` are latest-poll snapshots only — no numeric trend over time | `striim_mon_node_cluster`, `striim_mon_table_runhistory` |
| `get_app_status_summary(days_back)` | No existing function is a plain "every app + its current status" inventory (Uptime and Tables-Configured are adjacent, not this) | `striim_mon_appdetail`, `striim_mon_table_runhistory` |
| `get_app_status_history(app_name, days_back)` | `get_non_running_hourly_status` only logs non-RUNNING hours, and only for OJet/BigQueryWriter-scoped apps — no function draws a full continuous status timeline for an arbitrary app | `striim_mon_appdetail`, `striim_mon_table_runhistory` |

See each file's own header comment for full column docs and caveats (same format as the rest
of the suite), and `striim-watcher-dashboard/README.md` for how the web app calls them.
