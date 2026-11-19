from __future__ import annotations

from app.bigquery import queries
from app.bigquery.client import get_bq_client
from app.cache import cached
from app.config import get_settings
from app.models.schemas import (
    AppStatusHistoryPoint,
    AppStatusHistoryResponse,
    AppUptime,
    ClusterUptime,
    ClusterUptimeResponse,
)


@cached("app_status_history")
def get_app_status_history(app_name: str | None, days_back: int) -> AppStatusHistoryResponse:
    client = get_bq_client()
    settings = get_settings()

    rows = queries.get_app_status_history(client, settings, app_name, days_back)
    if settings.cluster_name:
        rows = [r for r in rows if r["clusterName"] == settings.cluster_name]
    points = [AppStatusHistoryPoint(**row) for row in rows]

    return AppStatusHistoryResponse(appName=app_name, days_back=days_back, points=points)


@cached("app_uptime")
def get_app_uptime(days_back: int, app_name: str | None = None) -> list[AppUptime]:
    client = get_bq_client()
    settings = get_settings()

    rows = queries.get_app_uptime(client, settings, days_back)
    if settings.cluster_name:
        rows = [r for r in rows if r["clusterName"] == settings.cluster_name]
    uptimes = [AppUptime(**row) for row in rows]

    if app_name:
        uptimes = [u for u in uptimes if u.appName == app_name]

    return uptimes


@cached("cluster_uptime")
def get_cluster_uptime(days_back: int) -> ClusterUptimeResponse:
    client = get_bq_client()
    settings = get_settings()

    rows = queries.get_cluster_uptime(client, settings, days_back)
    if settings.cluster_name:
        rows = [r for r in rows if r["clusterName"] == settings.cluster_name]
    clusters = [ClusterUptime(**row) for row in rows]

    return ClusterUptimeResponse(days_back=days_back, clusters=clusters)
