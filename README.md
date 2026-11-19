# StriimWatcher Dashboard

A small interactive web app for one Striim cluster: node CPU/memory health (snapshot + trend),
an application inventory with live status, and status-history trends — all read from the
BigQuery tables StriimWatcher already populates. No new agents on the Striim servers; this is
a thin read-only layer on top of the `Dashboard-Queries` function suite one level up in this
project.

Design background, data-source mapping, and the original wireframe: [`DESIGN.md`](DESIGN.md).
In short: single-cluster design — one deployment watches one cluster via `CLUSTER_NAME`, not a
multi-cluster fleet view.

## 1. Prerequisites

1. The base `Dashboard-Queries` suite already deployed (tables, `ApplicationAlertThresholds`,
   `get_node_status`, `get_app_uptime`, `get_cluster_uptime`, etc.) — this project already has
   that; see `../Dashboard-Queries/README.md` if starting fresh elsewhere.
2. **Three new BigQuery table functions this app also needs**, drafted in
   [`Dashboard-Queries-additions/`](Dashboard-Queries-additions/):
   ```bash
   cd Dashboard-Queries-additions
   bq query --use_legacy_sql=false < get_node_resource_trend.sql
   bq query --use_legacy_sql=false < get_app_status_summary.sql
   bq query --use_legacy_sql=false < get_app_status_history.sql
   ```
   See that folder's own README for what each one adds and why it doesn't already exist in the
   base suite. Without these three, the Node Health tab's CPU trend chart, the Applications
   tab, and the status-timeline chart will all return BigQuery "routine not found" errors —
   everything else (node snapshot, app/cluster uptime %) works against the base suite alone.
3. GCP credentials able to run queries against that dataset — either `gcloud auth
   application-default login` (the default, `BQ_AUTH_MODE=adc`) or a service-account key (see
   §3).

## 2. Single-cluster scope

Each deployment of this app watches **one** cluster, set via `CLUSTER_NAME`. The
`Dashboard-Queries` functions themselves are unchanged and still multi-cluster-aware (they all
key on `clusterName`) — only this app's service layer filters every response down to the one
configured cluster. Monitoring more than one cluster means running more than one instance,
each with its own `.env`.

Leave `CLUSTER_NAME` unset to see the dataset unfiltered (fine if it genuinely only contains
one cluster's data). `GET /api/meta/clusters` always returns the *unfiltered* list regardless
of `CLUSTER_NAME` — treat more than one name coming back from it, while running with
`CLUSTER_NAME` unset, as a sign to set it.

## 3. Configuration

Copy `.env.example` to `.env` and fill in:

| Variable | Default | Purpose |
|---|---|---|
| `PROJECT_ID` | *(required)* | GCP project |
| `BQ_DATASET` | `Vivek` | Dataset the `Dashboard-Queries` functions live in |
| `BQ_AUTH_MODE` | `adc` | `adc` or `service_account` |
| `GOOGLE_APPLICATION_CREDENTIALS` | *(unset)* | Path to a mounted service-account JSON key; only used when `BQ_AUTH_MODE=service_account` |
| `CLUSTER_NAME` | *(unset)* | The one cluster this instance watches — see §2 |
| `NODE_TREND_DAYS_BACK` | `1` | Default lookback for node status + CPU trend |
| `APP_HISTORY_DEFAULT_DAYS` | `7` | Default lookback for the status-timeline tab |
| `APP_UPTIME_DEFAULT_DAYS` | `30` | Default lookback for uptime % stats |
| `QUERY_CACHE_TTL_SECONDS` | `60` | In-memory cache TTL for every BigQuery call (StriimWatcher polls every 5 min by default — no point refreshing faster than that) |
| `AUTO_REFRESH_SECONDS` | `60` | Frontend polling interval; `0` disables |
| `APP_PORT` | `8080` | Listen port, used by both the container and the `docker-compose.yml` port mapping |
| `LOG_LEVEL` | `INFO` | — |

**A note on lookback windows from real-world testing:** if a cluster hasn't polled recently
(stopped, or between test runs), the *default* lookback windows above may return empty
results even though historical data exists further back — these functions only look back
`days_back` days from now, they don't search indefinitely for "the last known state." Widen
`days_back` (via the UI's range selector, or the env defaults above) if a panel looks
unexpectedly empty.

## 4. Running it

### With Docker Compose (recommended)

```bash
cp .env.example .env    # fill in PROJECT_ID at minimum
docker compose up --build
# -> http://localhost:8080  (or whatever APP_PORT you set)
```

If `BQ_AUTH_MODE=service_account`, drop the key file at `secrets/key.json` and set
`GOOGLE_APPLICATION_CREDENTIALS=/secrets/key.json` in `.env` — `docker-compose.yml` already
mounts `./secrets` read-only into the container at `/secrets`.

### Locally, without Docker

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export PROJECT_ID=your-project BQ_DATASET=Vivek CLUSTER_NAME=YourCluster
uvicorn app.main:app --reload --port 8080
```

### Troubleshooting: `NameResolutionError` / can't resolve `oauth2.googleapis.com`

```
Failed to resolve 'oauth2.googleapis.com' ([Errno -3] Temporary failure in name resolution)
```

Both auth modes need to reach Google's OAuth token endpoint (ADC refreshes a token;
service-account mode exchanges a signed JWT for one) — this error means the *container*
couldn't resolve that hostname, not that the credentials are wrong. It's almost always
Docker's embedded DNS proxy temporarily failing to forward external lookups — commonly right
after Docker Desktop (re)starts, a VPN connects/disconnects, or the host network changes —
even while the host itself resolves fine. `docker-compose.yml` already pins explicit DNS
servers (`8.8.8.8`, `1.1.1.1`) on the service for exactly this reason; if it still happens:

1. `docker compose restart dashboard` (or `down` + `up` again) — often enough on its own.
2. Restart Docker Desktop if it persists — this resets its internal DNS proxy.
3. If you're on a VPN, check whether it's split-tunneling in a way that only affects traffic
   from Docker's network namespace (host DNS working while container DNS fails is the
   tell-tale sign).

## 5. Testing

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

Every test mocks the BigQuery client or the service layer — nothing in `tests/` makes a real
network call. `tests/test_queries.py` checks the generated SQL/params for each function call,
`tests/test_services.py` checks the `CLUSTER_NAME` filtering logic, `tests/test_api.py` checks
routing and response shape end-to-end through FastAPI's `TestClient`.

This app was also smoke-tested against the real `striimfieldproject.Vivek` dataset during
development (read-only, against the already-deployed base functions — the 3 new ones above
weren't deployed as part of that check). That's what caught one real bug worth knowing about:

> **`nodeName` (and other identity fields) can be `NULL`.** None of the `striim_mon_*` columns
> are declared `NOT NULL`, and at least one real row in this dataset has `nodeName = NULL`.
> Every identity field (`clusterName`, `nodeName`, `appName`) in `app/models/schemas.py` is
> `str | None` for this reason — a strict `str` type crashed the endpoint the first time it hit
> a row like that. The frontend drops/labels these as "—" rather than showing `null`/`None`.

## 6. API reference

See `app/api/routes_*.py` for the full FastAPI route definitions (OpenAPI docs are also
auto-served at `/docs` when the app is running). Summary:

| Route | Backed by |
|---|---|
| `GET /api/meta/clusters` | raw `SELECT DISTINCT clusterName` — unfiltered, diagnostic |
| `GET /api/meta/health` | trivial `SELECT 1` connectivity check |
| `GET /api/nodes/status?days_back=` | `get_node_status` + `get_node_status_summary` |
| `GET /api/nodes/trend?days_back=` | `get_node_resource_trend` *(new)* |
| `GET /api/apps/summary?days_back=` | `get_app_status_summary` *(new)* |
| `GET /api/apps/{app_name}/history?days_back=` | `get_app_status_history` *(new)* |
| `GET /api/apps/{app_name}/uptime?days_back=` | `get_app_uptime` |
| `GET /api/cluster/uptime?days_back=` | `get_cluster_uptime` |

## 7. Project layout

```
app/
  main.py            FastAPI app, mounts routers + templates
  config.py           Settings (env-driven)
  cache.py             shared TTL cache
  bigquery/
    client.py           BQ client factory (adc / service_account)
    queries.py            thin wrappers — one function per Dashboard-Queries routine
  services/            business logic: shapes query rows into response models, applies
                        CLUSTER_NAME filtering, cached
  models/schemas.py    Pydantic response models
  api/                 FastAPI routers
  web/                 Jinja2 templates + vanilla JS + Chart.js (no build step)
tests/                 pytest, BigQuery fully mocked
Dashboard-Queries-additions/   the 3 new .sql functions — see §1
```
