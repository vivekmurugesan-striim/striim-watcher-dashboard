# StriimWatcher Dashboard — Design & Implementation Plan

## Context

CAMS needs a small interactive web app — not another Looker/BigQuery artifact — that a team
member can run locally or in a container and immediately see three things: Striim cluster
node health, which applications are configured and their current status, and how application
status has trended over time. This sits on top of StriimWatcher data already landing in
BigQuery.

**Scope: single cluster, not a multi-cluster fleet view.** Each deployment of this app
monitors one Striim cluster (e.g. one AMC). The underlying `Dashboard-Queries` functions are
still generic and `clusterName`-aware — unchanged — but the app itself is configured with
*which* cluster it's watching and filters every query down to just that cluster, rather than
presenting a cluster picker or any cross-cluster comparison UI. This simplifies both the UI
(one node-health panel, not a grid of per-cluster cards) and the config story (one
`CLUSTER_NAME` setting). Running against more than one cluster means running more than one
instance of this app, each pointed at its own cluster — consistent with "all required details
of BigQuery access/credentials should be configurable."

Critically, this project **already has** a deployed, documented, tested suite of BigQuery
table functions for exactly this kind of dashboard — `Dashboard-Queries/` (see its `README.md`
and `DASHBOARD_QUERIES_RUNBOOK.md`), all living in the `Vivek` BigQuery dataset. Five of those
functions already answer two of the three requirements outright. The implementation plan below
is built around **reusing that suite as the data layer**, adding only the small number of new
table functions that are genuinely missing, and writing a thin, modular Python web app on top —
rather than re-deriving BigQuery logic that's already been built, caveated, and hardened.

---

## 1. Data sources

### 1a. Reused as-is — no changes

| Requirement | Function | Returns | Notes |
|---|---|---|---|
| Node health (snapshot) | `get_node_status(days_back)` | `clusterName, nodeName, status, cpurate, freemem, striimversion, uptime, last_seen_batchdate, latest_cluster_batchdate, RAG_status` | Per-node detail. Status is inferred by presence at the latest poll. `RAG_status` is cluster-level, replicated per node (Red = all down, Green = all up, Amber = mixed). |
| Node health (cluster rollup) | `get_node_status_summary(days_back)` | `clusterName, total_nodes, nodes_up, nodes_down, latest_batchdate` | Built on `get_node_status`; the top-tile number. |
| App history/trends (% uptime) | `get_app_uptime(days_back)` | `clusterName, appName, up_minutes, down_minutes, total_observed_minutes, uptime_pct` | RUNNING→UP; STOPPED/HALT/CRASH/CREATED→DOWN; everything else excluded. |
| App history/trends (cluster rollup) | `get_cluster_uptime(days_back)` | `clusterName, app_count, up_minutes, down_minutes, total_observed_minutes, uptime_pct, avg_of_app_uptime_pct` | Use `uptime_pct` (time-weighted) as the headline number. |
| App history/trends (problem log) | `get_non_running_hourly_status(days_back)` | `clusterName, appName, batchdate, appStatus` | Hourly-downsampled non-RUNNING audit log. **Caveat carried into the UI:** scoped to OJet-source / BigQueryWriter-target apps only (same membership rule as the denormalized view) — won't show every app. |

Source tables underneath these: `striim_mon_appdetail`, `striim_mon_node_cluster`,
`striim_mon_table_runhistory` (all confirmed in `AllTables_BigQuery_StriimWatcherPartitioned.sql`).

### 1b. New — small additions, following the exact existing conventions

The existing suite has no function for (a) a numeric CPU/memory **trend over time** (only a
latest-poll snapshot), (b) a plain **app inventory + current status list** (Tables-Configured
and Uptime are adjacent but not this), or (c) a **full per-app status timeline including
RUNNING** (the hourly log only captures non-running, and is adapter-scoped). Three new table
functions close these, written in the same dataset (`Vivek`), same docstring/style, same
`CREATE OR REPLACE TABLE FUNCTION` pattern as every sibling file, and added to
`Dashboard-Queries/` with `README.md`/summary-table entries appended (not a new doc tree):

1. **`get_node_resource_trend(days_back INT64)`** — `clusterName, nodeName, hour, avg_cpurate, sample_count, latest_freemem`. Hourly-bucketed average `cpurate` from `striim_mon_node_cluster`, joined through `striim_mon_table_runhistory` for `clusterName`. `freemem` is intentionally **not** parsed to a number — this project's own docs are explicit that there's no established numeric parser for it (raw strings like `"3.2 GB"`, format not fully confirmed) — so `latest_freemem` is passed through as the last raw string reading in that hour, for display only, not charted. CPU is the only numeric trend line.
2. **`get_app_status_summary(days_back INT64)`** — `clusterName, appName, appStatus, status_bucket, isBackpressured, checkpointStatus, isRecoveryEnabled, totalInput, totalOutput, deploymentOn, latestActivity, latest_batchdate`. One row per app, latest poll only. `status_bucket` reuses `get_app_uptime`'s exact UP/DOWN/NULL mapping so status coloring is consistent across the whole suite rather than inventing a second taxonomy.
3. **`get_app_status_history(app_name STRING, days_back INT64)`** — `clusterName, appName, hour, appStatus, batchdate`. Same hourly-downsampling technique as `get_non_running_hourly_status`, but **unscoped** (any adapter type) and **includes RUNNING** — this is what actually draws a continuous status-over-time timeline for one selected app. `app_name = NULL` returns every app (same `NULL`-means-all convention `get_tables_by_app` already uses).

All three get deployed the same way as every other file here: `bq query --use_legacy_sql=false < Dashboard-Queries/get_node_resource_trend.sql`, etc.

### 1c. RAG convention reused, not reinvented

Per `RAG_STATUS_IMPLEMENTATION_PLAN.md`: node RAG = Red (all nodes down) / Green (all up) /
Amber (mixed); app RAG = Red (0% running) / Green (100% running) / Amber (in between). The UI
uses these exact bands for its status colors/badges.

---

## 2. Architecture

**Stack:** Python/FastAPI backend serving both a small REST API and a server-rendered
dashboard (Jinja2 templates + vanilla JS + Chart.js via CDN — no node build step). One Docker
image, one `docker-compose.yml` service. This matches the project's existing Python style
(`standalone_alert_poller.py`, `alert_notifier_function/`) rather than introducing a second
framework paradigm, and keeps "simple web application" literally true — no separate frontend
build pipeline.

**Why not split frontend/backend into two containers:** nothing here needs independent scaling
or a different release cadence; a second container would add compose complexity (networking,
CORS) for no benefit at this scope. Noted as a trade-off — easy to split later if needed.

**Why FastAPI over Streamlit:** FastAPI gives a clean `api/ → services/ → bigquery/` module
boundary (the "modularized" requirement) plus a real REST layer other tools could reuse later,
while staying just as easy to containerize. Streamlit would be faster to a first screen but
blurs the data/presentation boundary and is harder to unit-test.

**BigQuery access layer is a thin client, not a query engine.** `app/bigquery/queries.py`
contains only fully-qualified calls like `` SELECT * FROM `{project}.{dataset}.get_node_status`(@days_back) `` —
it does not re-implement logic the deployed functions already own. This keeps the SQL
single-sourced in `Dashboard-Queries/` and the Python layer trivially testable (mock the BQ
client, assert the generated SQL string + params).

**Caching:** StriimWatcher polls every 5 minutes by default — there's no value refreshing more
often than that. An in-memory TTL cache (`cachetools`) wraps every BigQuery call,
default TTL 60s, configurable.

**Single-cluster scoping.** A new `CLUSTER_NAME` setting (optional) names the one cluster this
instance watches. When set, the service layer filters every function's rows to
`clusterName = settings.cluster_name` before shaping the API response — the BigQuery functions
themselves stay untouched and still return every cluster, since other tooling in this project
depends on that. When unset, the app shows whatever clusters the dataset actually contains
unfiltered (useful for a dataset that's already scoped to one cluster, or for local testing) —
`GET /api/meta/clusters` becomes a diagnostic endpoint in this mode: if it ever returns more
than one name while `CLUSTER_NAME` is unset, that's a signal the deployment needs the setting
turned on, logged as a warning rather than silently mixing clusters in the UI.

---

## 3. Wireframe

Single page, top bar + 3 tabs, no routing framework needed. No cluster picker anywhere — the
top bar names the one cluster this instance is configured for (`CLUSTER_NAME`), and every
panel below is already scoped to it:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ StriimWatcher Dashboard — Bandhan                  Updated 09:41:02      │
│                                                     [⟳ Auto-refresh 60s] │
├──────────────────────────────────────────────────────────────────────────┤
│  [ Node Health ]   Applications    History & Trends                      │
├──────────────────────────────────────────────────────────────────────────┤
│  Summary (from get_node_status_summary, this cluster only)               │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐                  │
│  │ Total nodes    │ │ Nodes up      │ │ Status        │                  │
│  │ 3              │ │ 2 / 3         │ │ ● AMBER       │                  │
│  └───────────────┘ └───────────────┘ └───────────────┘                  │
│                                                                            │
│  Node detail (get_node_status)                                           │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ Node          Status   CPU (per-core)   Free Mem     Uptime         │ │
│  │ S10_50_2_11    ● UP     84%              1.1 GB        62d 4h       │ │
│  │ S10_50_2_12    ● UP     41%              3.8 GB        62d 4h       │ │
│  │ S10_50_2_13    ● DOWN   —                —             —            │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  CPU trend, last 24h (get_node_resource_trend) — one line per node       │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │      ╭╮        ╭─╮                                                  │ │
│  │  ───╯╰────────╯  ╰────╮          S10_50_2_11                        │ │
│  │  ·····················╰──        S10_50_2_12                        │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│  Node Health   [ Applications ]   History & Trends                       │
├──────────────────────────────────────────────────────────────────────────┤
│ Status mix: ● Running 39   ● Halt 5   ● Crash 2   ● Other 3              │
│ Search [___________]  Status:[All ▾]                                    │
│ ┌────────────────────────────────────────────────────────────────────┐ │
│ │ App Name            Status      Backpressure  Checkpoint   Recovery  │ │
│ │ admin.NAV_CDC        ● HALT       No            STALLED      Yes     │ │
│ │ admin.UnitHolder_IL  ● RUNNING    Yes (47m)      OK           Yes     │ │
│ │ admin.FolioMaster    ● RUNNING    No             OK           No     │ │
│ └────────────────────────────────────────────────────────────────────┘ │
│  (row click → History & Trends tab, pre-filtered to this app)           │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│  Node Health   Applications   [ History & Trends ]                       │
├──────────────────────────────────────────────────────────────────────────┤
│ App: [admin.NAV_CDC ▾]   Range: [Last 7 days ▾]                         │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐                  │
│  │ App uptime     │ │ Up / Down     │ │ Cluster uptime│                  │
│  │ 92.4%          │ │ 6d3h / 11h12m │ │ 94.2% (7d)    │                  │
│  └───────────────┘ └───────────────┘ └───────────────┘                  │
│  (app uptime: get_app_uptime · cluster uptime: get_cluster_uptime)       │
│                                                                            │
│ Status timeline — get_app_status_history(app, 7)                         │
│ ┌────────────────────────────────────────────────────────────────────┐ │
│ │ RUNNING   ████████████░░░░████████████████░░░░████████████████████  │ │
│ │ HALT      ░░░░░░░░░░░░████░░░░░░░░░░░░░░░░████░░░░░░░░░░░░░░░░░░░░  │ │
│ │           Mon      Tue      Wed      Thu      Fri      Sat     Sun  │ │
│ └────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

Dropped from the earlier multi-cluster draft: the cluster-picker dropdown, the grid of
per-cluster summary cards (now one set of stat tiles), the "Cluster" column in the app table,
and the cluster-uptime comparison bar chart (now one stat tile — comparing a single cluster
against itself isn't meaningful; `get_cluster_uptime`'s number is folded into the History tab's
stat row instead).

---

## 4. Directory layout

```
striim-watcher-dashboard/
├── README.md                    # setup, config reference, how to run
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── requirements.txt
├── app/
│   ├── main.py                  # FastAPI app, mounts routers + templates
│   ├── config.py                # pydantic-settings: all env-configurable values
│   ├── cache.py                 # TTLCache wrapper
│   ├── bigquery/
│   │   ├── client.py            # BQ client factory (ADC or service-account key)
│   │   └── queries.py           # thin wrappers calling the deployed Vivek.* functions
│   ├── services/
│   │   ├── node_health.py
│   │   ├── app_summary.py
│   │   └── app_history.py
│   ├── models/
│   │   └── schemas.py           # Pydantic response models
│   ├── api/
│   │   ├── routes_nodes.py
│   │   ├── routes_apps.py
│   │   └── routes_meta.py       # /clusters, /health
│   └── web/
│       ├── templates/
│       │   ├── base.html
│       │   └── index.html       # the 3-tab single page
│       └── static/
│           ├── css/style.css
│           └── js/
│               ├── api.js
│               ├── nodeHealth.js
│               ├── appSummary.js
│               └── appHistory.js
├── tests/
│   ├── test_queries.py          # BQ client mocked; assert SQL + params
│   └── test_api.py              # FastAPI TestClient, services mocked
├── secrets/                     # gitignored; local service-account key mount point
│   └── .gitkeep
└── Dashboard-Queries-additions/ # the 3 new .sql files, deployed into Dashboard-Queries/
    ├── get_node_resource_trend.sql
    ├── get_app_status_summary.sql
    └── get_app_status_history.sql
```

The three new `.sql` files are drafted here but are meant to be deployed alongside (and
documented in) the existing `Dashboard-Queries/` suite one level up — the plan keeps them in a
clearly-labeled subfolder inside `striim-watcher-dashboard/` so this whole feature ships as one
self-contained unit the user can review before copying the `.sql` files up into
`Dashboard-Queries/` and appending the corresponding rows to its `README.md`.

---

## 5. Configuration (all env-driven, per `.env.example`)

| Variable | Default | Purpose |
|---|---|---|
| `PROJECT_ID` | *(required)* | GCP project — same name the rest of this project's scripts already use |
| `BQ_DATASET` | `Vivek` | Dataset the `Dashboard-Queries` functions live in |
| `CLUSTER_NAME` | *(unset)* | The one cluster this instance watches; every API response is filtered to `clusterName = CLUSTER_NAME` when set. Unset = unfiltered (see §2's single-cluster-scoping note) |
| `BQ_AUTH_MODE` | `adc` | `adc` (Application Default Credentials) or `service_account` |
| `GOOGLE_APPLICATION_CREDENTIALS` | *(unset)* | Path to a mounted service-account JSON key; only read when `BQ_AUTH_MODE=service_account` |
| `NODE_TREND_DAYS_BACK` | `1` | Default lookback for the CPU trend chart |
| `APP_HISTORY_DEFAULT_DAYS` | `7` | Default lookback for the status timeline tab |
| `APP_UPTIME_DEFAULT_DAYS` | `30` | Default lookback for uptime %/cluster rollup |
| `QUERY_CACHE_TTL_SECONDS` | `60` | In-memory cache TTL for all BigQuery calls |
| `AUTO_REFRESH_SECONDS` | `60` | Frontend polling interval; `0` disables |
| `APP_PORT` | `8080` | Container listen port |
| `LOG_LEVEL` | `INFO` | — |

`docker-compose.yml` reads `.env`, exposes `${APP_PORT}:8080`, and (when
`BQ_AUTH_MODE=service_account`) mounts `./secrets:/secrets:ro` with
`GOOGLE_APPLICATION_CREDENTIALS=/secrets/key.json`.

---

## 6. API surface

Every route below applies the `CLUSTER_NAME` filter (when set) server-side, in the service
layer — the frontend never passes a cluster parameter, there is nothing for it to pick.

- `GET /api/meta/clusters` — distinct cluster list, **unfiltered** even when `CLUSTER_NAME` is set — this is the diagnostic endpoint that catches a dataset actually holding more than one cluster (see §2)
- `GET /api/meta/health` — liveness probe, runs a trivial BQ query to confirm connectivity
- `GET /api/nodes/status?days_back=` → `get_node_status` + `get_node_status_summary`, filtered
- `GET /api/nodes/trend?days_back=` → `get_node_resource_trend`, filtered
- `GET /api/apps/summary?days_back=` → `get_app_status_summary`, filtered
- `GET /api/apps/{app_name}/history?days_back=` → `get_app_status_history`
- `GET /api/apps/{app_name}/uptime?days_back=` → `get_app_uptime`, filtered to one app
- `GET /api/cluster/uptime?days_back=` → `get_cluster_uptime`, filtered to the one configured cluster (singular path now — not `/clusters/uptime`, since there's exactly one)

`index.html` fetches these client-side via `api.js`; Chart.js renders the CPU-trend line and
status-timeline bars from the JSON responses. The one-time comparison bar chart is gone — see
§3.

---

## 7. Build order

1. Write and smoke-test the 3 new `.sql` functions directly in BigQuery (`bq query` against
   `Vivek`), confirming real output shape before any Python depends on them.
2. `app/config.py` + `app/bigquery/client.py` — both auth modes, a `--check` script path to
   verify connectivity early.
3. `app/bigquery/queries.py` + `services/` + `models/schemas.py` — one vertical slice (Node
   Health) end-to-end first, including its test, before starting the next.
4. Repeat for Applications, then History & Trends.
5. `web/` templates + static JS wiring the 3 tabs to the API.
6. `Dockerfile` + `docker-compose.yml` + `.env.example` + `README.md`.
7. `tests/` — BQ client mocked throughout; no test hits real BigQuery.

## 8. Verification

- `pytest tests/` — query-builder and API tests with BigQuery mocked.
- `docker compose up --build`, then hit `/api/meta/health` to confirm real BigQuery
  connectivity under whichever `BQ_AUTH_MODE` is configured.
- Manually walk all 3 tabs against the real `Vivek` dataset, cross-checking a couple of numbers
  against the existing `bq query` examples in `Dashboard-Queries/README.md` (e.g.
  `get_node_status_summary(1)`) to confirm the app's numbers match the raw function output.

## 9. Out of scope (flagged, not built)

- A multi-cluster fleet view (cluster picker, cross-cluster comparison charts) — deliberately
  dropped in favor of single-cluster scope (§ Context, §2, §3). Monitoring more than one
  cluster means running more than one instance of this app, each with its own `CLUSTER_NAME`.
- Auth/access control on the web app itself (assumed to run on a trusted internal network;
  note this explicitly in the README).
- The other 4 existing dashboard tiles (Ojet Freshness, Tables Configured, Latency, Checkpoint
  Stalled) — not part of the 3 stated requirements; the module layout leaves room to add them
  as additional tabs later without restructuring.
- Writing back to BigQuery (alert thresholds, etc.) — this app is read-only.
