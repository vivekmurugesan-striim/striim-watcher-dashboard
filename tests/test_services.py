"""Service-layer tests, focused on the one piece of real logic this layer owns: the
CLUSTER_NAME single-cluster filter (everything else is thin shaping of query results into
Pydantic models). BigQuery itself and app.config.get_settings/app.bigquery.client.get_bq_client
are monkeypatched per-module — those two are bound via `from x import y`, so patching the
original definitions wouldn't reach the service module's own local name for them.
"""

from __future__ import annotations

from app.bigquery import queries as bq_queries
from app.config import Settings
from app.services import app_history, app_summary, node_health


def make_settings(**overrides) -> Settings:
    defaults = dict(project_id="proj", bq_dataset="Vivek")
    defaults.update(overrides)
    return Settings(**defaults)


def test_node_health_filters_to_configured_cluster(monkeypatch, fake_client):
    monkeypatch.setattr(node_health, "get_bq_client", lambda: fake_client)
    monkeypatch.setattr(node_health, "get_settings", lambda: make_settings(cluster_name="Bandhan"))
    monkeypatch.setattr(
        bq_queries,
        "get_node_status_summary",
        lambda client, settings, days_back: [
            {"clusterName": "Bandhan", "total_nodes": 3, "nodes_up": 2, "nodes_down": 1, "latest_batchdate": None},
            {"clusterName": "HDFC", "total_nodes": 3, "nodes_up": 3, "nodes_down": 0, "latest_batchdate": None},
        ],
    )
    monkeypatch.setattr(
        bq_queries,
        "get_node_status",
        lambda client, settings, days_back: [
            {
                "clusterName": "Bandhan", "nodeName": "N1", "status": "UP", "cpurate": 10.0,
                "freemem": "1 GB", "striimversion": "4.2", "uptime": "1d",
                "last_seen_batchdate": None, "latest_cluster_batchdate": None, "RAG_status": "Amber",
            },
            {
                "clusterName": "HDFC", "nodeName": "N2", "status": "UP", "cpurate": 5.0,
                "freemem": "2 GB", "striimversion": "4.2", "uptime": "1d",
                "last_seen_batchdate": None, "latest_cluster_batchdate": None, "RAG_status": "Green",
            },
        ],
    )

    result = node_health.get_node_health(1)

    assert len(result.clusters) == 1
    assert result.clusters[0].clusterName == "Bandhan"
    assert result.clusters[0].RAG_status == "Amber"  # some, not all, down
    assert [n.nodeName for n in result.nodes] == ["N1"]


def test_node_health_unfiltered_when_cluster_name_unset(monkeypatch, fake_client):
    monkeypatch.setattr(node_health, "get_bq_client", lambda: fake_client)
    monkeypatch.setattr(node_health, "get_settings", lambda: make_settings(cluster_name=None))
    monkeypatch.setattr(
        bq_queries,
        "get_node_status_summary",
        lambda client, settings, days_back: [
            {"clusterName": "Bandhan", "total_nodes": 1, "nodes_up": 1, "nodes_down": 0, "latest_batchdate": None},
            {"clusterName": "HDFC", "total_nodes": 1, "nodes_up": 0, "nodes_down": 1, "latest_batchdate": None},
        ],
    )
    monkeypatch.setattr(bq_queries, "get_node_status", lambda client, settings, days_back: [])

    result = node_health.get_node_health(1)

    assert {c.clusterName for c in result.clusters} == {"Bandhan", "HDFC"}


def test_app_summary_filters_to_configured_cluster(monkeypatch, fake_client):
    monkeypatch.setattr(app_summary, "get_bq_client", lambda: fake_client)
    monkeypatch.setattr(app_summary, "get_settings", lambda: make_settings(cluster_name="Bandhan"))
    monkeypatch.setattr(
        bq_queries,
        "get_app_status_summary",
        lambda client, settings, days_back: [
            {
                "clusterName": "Bandhan", "appName": "admin.App1", "appStatus": "RUNNING",
                "status_bucket": "UP", "isBackpressured": False, "checkpointStatus": "OK",
                "isRecoveryEnabled": True, "totalInput": 10, "totalOutput": 10,
                "deploymentOn": "node1", "latestActivity": None, "latest_batchdate": None,
            },
            {
                "clusterName": "HDFC", "appName": "admin.App2", "appStatus": "HALT",
                "status_bucket": "DOWN", "isBackpressured": False, "checkpointStatus": None,
                "isRecoveryEnabled": False, "totalInput": 0, "totalOutput": 0,
                "deploymentOn": "node2", "latestActivity": None, "latest_batchdate": None,
            },
        ],
    )

    result = app_summary.get_app_summary(1)

    assert [a.appName for a in result.apps] == ["admin.App1"]
    assert result.counts.total == 1
    assert {c.status_bucket: c.count for c in result.counts.by_bucket} == {"UP": 1}


def test_cluster_uptime_filters_to_configured_cluster(monkeypatch, fake_client):
    monkeypatch.setattr(app_history, "get_bq_client", lambda: fake_client)
    monkeypatch.setattr(app_history, "get_settings", lambda: make_settings(cluster_name="Bandhan"))
    monkeypatch.setattr(
        bq_queries,
        "get_cluster_uptime",
        lambda client, settings, days_back: [
            {
                "clusterName": "Bandhan", "app_count": 5, "up_minutes": 90, "down_minutes": 10,
                "total_observed_minutes": 100, "uptime_pct": 90.0, "avg_of_app_uptime_pct": 88.0,
            },
            {
                "clusterName": "HDFC", "app_count": 3, "up_minutes": 95, "down_minutes": 5,
                "total_observed_minutes": 100, "uptime_pct": 95.0, "avg_of_app_uptime_pct": 95.0,
            },
        ],
    )

    result = app_history.get_cluster_uptime(30)

    assert len(result.clusters) == 1
    assert result.clusters[0].clusterName == "Bandhan"
