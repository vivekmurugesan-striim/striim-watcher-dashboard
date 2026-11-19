"""Thin BigQuery query layer.

Deliberately NOT a query engine: every function here just calls an already-deployed table
function in Dashboard-Queries/ (or, for the two trivial meta lookups, a one-line SELECT that
isn't worth its own .sql file) and returns plain dicts. No business logic, no shaping, no
caching lives here — that's the services/ layer's job. Keeping this boundary thin means the SQL
stays single-sourced in the .sql files, and this module is trivial to unit-test by mocking the
`client` parameter (see tests/test_queries.py).
"""

from __future__ import annotations

from typing import Any

from google.cloud import bigquery

from app.config import Settings


def _run(
    client: bigquery.Client,
    sql: str,
    params: list[bigquery.ScalarQueryParameter] | None = None,
) -> list[dict[str, Any]]:
    job_config = bigquery.QueryJobConfig(query_parameters=params or [])
    job = client.query(sql, job_config=job_config)
    return [dict(row) for row in job.result()]


def _fq(settings: Settings, name: str) -> str:
    """Fully-qualified `` `project.dataset.name` `` reference."""
    return f"`{settings.dataset_ref}.{name}`"


def _days_back_param(days_back: int) -> list[bigquery.ScalarQueryParameter]:
    return [bigquery.ScalarQueryParameter("days_back", "INT64", days_back)]


# -- Node health --------------------------------------------------------------


def get_node_status(client: bigquery.Client, settings: Settings, days_back: int) -> list[dict]:
    sql = f"SELECT * FROM {_fq(settings, 'get_node_status')}(@days_back) ORDER BY clusterName, nodeName"
    return _run(client, sql, _days_back_param(days_back))


def get_node_status_summary(client: bigquery.Client, settings: Settings, days_back: int) -> list[dict]:
    sql = f"SELECT * FROM {_fq(settings, 'get_node_status_summary')}(@days_back) ORDER BY clusterName"
    return _run(client, sql, _days_back_param(days_back))


def get_node_resource_trend(client: bigquery.Client, settings: Settings, days_back: int) -> list[dict]:
    sql = f"SELECT * FROM {_fq(settings, 'get_node_resource_trend')}(@days_back)"
    return _run(client, sql, _days_back_param(days_back))


# -- Applications ---------------------------------------------------------------


def get_app_status_summary(client: bigquery.Client, settings: Settings, days_back: int) -> list[dict]:
    sql = f"SELECT * FROM {_fq(settings, 'get_app_status_summary')}(@days_back)"
    return _run(client, sql, _days_back_param(days_back))


def get_app_status_history(
    client: bigquery.Client, settings: Settings, app_name: str | None, days_back: int
) -> list[dict]:
    sql = f"SELECT * FROM {_fq(settings, 'get_app_status_history')}(@app_name, @days_back)"
    params = [
        bigquery.ScalarQueryParameter("app_name", "STRING", app_name),
        bigquery.ScalarQueryParameter("days_back", "INT64", days_back),
    ]
    return _run(client, sql, params)


def get_app_uptime(client: bigquery.Client, settings: Settings, days_back: int) -> list[dict]:
    sql = f"SELECT * FROM {_fq(settings, 'get_app_uptime')}(@days_back)"
    return _run(client, sql, _days_back_param(days_back))


def get_cluster_uptime(client: bigquery.Client, settings: Settings, days_back: int) -> list[dict]:
    sql = f"SELECT * FROM {_fq(settings, 'get_cluster_uptime')}(@days_back)"
    return _run(client, sql, _days_back_param(days_back))


# -- Meta -----------------------------------------------------------------------


def list_clusters(client: bigquery.Client, settings: Settings) -> list[str]:
    sql = (
        f"SELECT DISTINCT clusterName FROM `{settings.dataset_ref}.striim_mon_table_runhistory` "
        "ORDER BY clusterName"
    )
    rows = _run(client, sql)
    return [r["clusterName"] for r in rows]


def health_check(client: bigquery.Client) -> bool:
    rows = _run(client, "SELECT 1 AS ok")
    return bool(rows) and rows[0]["ok"] == 1
