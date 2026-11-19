"""API wiring tests — every service-layer call is monkeypatched (routes import the services
*module*, e.g. `from app.services import meta` then call `meta.get_clusters()`, so patching
`app.services.meta.get_clusters` reaches it regardless of which router module made the call).
These tests check routing, status codes, and response shape — not BigQuery or business logic,
which test_queries.py and test_services.py already cover.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import (
    AppStatusCounts,
    AppStatusHistoryResponse,
    AppSummaryResponse,
    AppUptime,
    ClustersResponse,
    ClusterUptime,
    ClusterUptimeResponse,
    HealthResponse,
    NodeHealthResponse,
    NodeTrendResponse,
)
from app.services import app_history, app_summary, meta, node_health

client = TestClient(app)


def test_index_page_renders():
    res = client.get("/")
    assert res.status_code == 200
    assert "StriimWatcher Dashboard" in res.text


def test_clusters_endpoint(monkeypatch):
    monkeypatch.setattr(meta, "get_clusters", lambda: ClustersResponse(clusters=["Bandhan"]))
    res = client.get("/api/meta/clusters")
    assert res.status_code == 200
    assert res.json() == {"clusters": ["Bandhan"]}


def test_health_endpoint_ok(monkeypatch):
    monkeypatch.setattr(
        meta, "check_health", lambda: HealthResponse(status="ok", project_id="proj", dataset="Vivek")
    )
    res = client.get("/api/meta/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_node_status_endpoint(monkeypatch):
    monkeypatch.setattr(
        node_health, "get_node_health", lambda days_back: NodeHealthResponse(clusters=[], nodes=[])
    )
    res = client.get("/api/nodes/status?days_back=2")
    assert res.status_code == 200
    assert res.json() == {"clusters": [], "nodes": []}


def test_node_trend_endpoint_uses_default_when_param_omitted(monkeypatch):
    captured = {}

    def fake_get_node_trend(days_back):
        captured["days_back"] = days_back
        return NodeTrendResponse(days_back=days_back, points=[])

    monkeypatch.setattr(node_health, "get_node_trend", fake_get_node_trend)
    res = client.get("/api/nodes/trend")
    assert res.status_code == 200
    assert captured["days_back"] == 7  # Settings.node_trend_days_back default


def test_app_summary_endpoint(monkeypatch):
    monkeypatch.setattr(
        app_summary,
        "get_app_summary",
        lambda days_back: AppSummaryResponse(
            apps=[], counts=AppStatusCounts(total=0, by_bucket=[], by_status=[])
        ),
    )
    res = client.get("/api/apps/summary")
    assert res.status_code == 200
    assert res.json()["counts"]["total"] == 0


def test_app_history_endpoint(monkeypatch):
    monkeypatch.setattr(
        app_history,
        "get_app_status_history",
        lambda app_name, days_back: AppStatusHistoryResponse(appName=app_name, days_back=days_back, points=[]),
    )
    res = client.get("/api/apps/admin.App1/history?days_back=3")
    assert res.status_code == 200
    body = res.json()
    assert body["appName"] == "admin.App1"
    assert body["days_back"] == 3


def test_app_uptime_endpoint_returns_null_when_app_not_found(monkeypatch):
    monkeypatch.setattr(app_history, "get_app_uptime", lambda days_back, app_name=None: [])
    res = client.get("/api/apps/admin.Missing/uptime")
    assert res.status_code == 200
    assert res.json() is None


def test_app_uptime_endpoint_returns_match(monkeypatch):
    monkeypatch.setattr(
        app_history,
        "get_app_uptime",
        lambda days_back, app_name=None: [
            AppUptime(
                clusterName="Bandhan", appName="admin.App1", up_minutes=90,
                down_minutes=10, total_observed_minutes=100, uptime_pct=90.0,
            )
        ],
    )
    res = client.get("/api/apps/admin.App1/uptime")
    assert res.status_code == 200
    assert res.json()["appName"] == "admin.App1"


def test_cluster_uptime_endpoint(monkeypatch):
    monkeypatch.setattr(
        app_history,
        "get_cluster_uptime",
        lambda days_back: ClusterUptimeResponse(
            days_back=days_back,
            clusters=[
                ClusterUptime(
                    clusterName="Bandhan", app_count=5, up_minutes=90, down_minutes=10,
                    total_observed_minutes=100, uptime_pct=90.0, avg_of_app_uptime_pct=88.0,
                )
            ],
        ),
    )
    res = client.get("/api/cluster/uptime?days_back=30")
    assert res.status_code == 200
    assert res.json()["clusters"][0]["clusterName"] == "Bandhan"
