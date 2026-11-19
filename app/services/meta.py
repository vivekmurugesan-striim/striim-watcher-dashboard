from __future__ import annotations

from app.bigquery import queries
from app.bigquery.client import get_bq_client
from app.cache import cached
from app.config import get_settings
from app.models.schemas import ClustersResponse, HealthResponse


@cached("clusters")
def get_clusters() -> ClustersResponse:
    client = get_bq_client()
    settings = get_settings()
    return ClustersResponse(clusters=queries.list_clusters(client, settings))


def check_health() -> HealthResponse:
    """Deliberately NOT cached — a health check should reflect real, current connectivity."""
    client = get_bq_client()
    settings = get_settings()
    ok = queries.health_check(client)
    return HealthResponse(
        status="ok" if ok else "degraded",
        project_id=settings.project_id,
        dataset=settings.bq_dataset,
    )
