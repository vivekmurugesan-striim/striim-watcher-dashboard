from __future__ import annotations

from app.bigquery import queries
from app.bigquery.client import get_bq_client
from app.cache import cached
from app.config import get_settings
from app.models.schemas import (
    ClusterNodeSummary,
    NodeHealthResponse,
    NodeStatus,
    NodeTrendPoint,
    NodeTrendResponse,
)


def _cluster_rag(total_nodes: int, nodes_down: int) -> str:
    """Mirrors get_node_status.sql's own RAG rule exactly (Red = all down, Green = all up,
    Amber = mixed) — get_node_status_summary.sql doesn't expose this column itself, only the
    per-node rows do, so it's computed here rather than by editing the deployed function.
    """
    if total_nodes == 0:
        return "Amber"
    if nodes_down == total_nodes:
        return "Red"
    if nodes_down == 0:
        return "Green"
    return "Amber"


@cached("node_health")
def get_node_health(days_back: int) -> NodeHealthResponse:
    client = get_bq_client()
    settings = get_settings()

    summary_rows = queries.get_node_status_summary(client, settings, days_back)
    node_rows = queries.get_node_status(client, settings, days_back)

    if settings.cluster_name:
        summary_rows = [r for r in summary_rows if r["clusterName"] == settings.cluster_name]
        node_rows = [r for r in node_rows if r["clusterName"] == settings.cluster_name]

    clusters = [
        ClusterNodeSummary(
            **row,
            RAG_status=_cluster_rag(row["total_nodes"], row["nodes_down"]),
        )
        for row in summary_rows
    ]
    nodes = [NodeStatus(**row) for row in node_rows]

    return NodeHealthResponse(clusters=clusters, nodes=nodes)


@cached("node_trend")
def get_node_trend(days_back: int) -> NodeTrendResponse:
    client = get_bq_client()
    settings = get_settings()

    rows = queries.get_node_resource_trend(client, settings, days_back)
    if settings.cluster_name:
        rows = [r for r in rows if r["clusterName"] == settings.cluster_name]
    points = [NodeTrendPoint(**row) for row in rows]

    return NodeTrendResponse(days_back=days_back, points=points)
