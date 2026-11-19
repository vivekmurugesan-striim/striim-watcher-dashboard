from __future__ import annotations

from app.bigquery import queries
from app.config import Settings


def make_settings(**overrides) -> Settings:
    defaults = dict(project_id="proj", bq_dataset="Vivek")
    defaults.update(overrides)
    return Settings(**defaults)


def test_get_node_status_builds_fully_qualified_call(fake_client):
    settings = make_settings()
    fake_client.rows = [{"clusterName": "Bandhan", "nodeName": "N1"}]

    rows = queries.get_node_status(fake_client, settings, 1)

    assert rows == [{"clusterName": "Bandhan", "nodeName": "N1"}]
    call = fake_client.calls[0]
    assert "`proj.Vivek.get_node_status`(@days_back)" in call["sql"]
    assert call["params"][0].name == "days_back"
    assert call["params"][0].value == 1


def test_get_node_status_summary(fake_client):
    settings = make_settings()
    queries.get_node_status_summary(fake_client, settings, 3)
    assert "`proj.Vivek.get_node_status_summary`(@days_back)" in fake_client.calls[0]["sql"]
    assert fake_client.calls[0]["params"][0].value == 3


def test_get_node_resource_trend(fake_client):
    settings = make_settings()
    queries.get_node_resource_trend(fake_client, settings, 2)
    assert "`proj.Vivek.get_node_resource_trend`(@days_back)" in fake_client.calls[0]["sql"]


def test_get_app_status_summary(fake_client):
    settings = make_settings()
    queries.get_app_status_summary(fake_client, settings, 1)
    assert "`proj.Vivek.get_app_status_summary`(@days_back)" in fake_client.calls[0]["sql"]


def test_get_app_status_history_with_app_name(fake_client):
    settings = make_settings()
    queries.get_app_status_history(fake_client, settings, "admin.App1", 7)

    call = fake_client.calls[0]
    assert "`proj.Vivek.get_app_status_history`(@app_name, @days_back)" in call["sql"]
    params_by_name = {p.name: p.value for p in call["params"]}
    assert params_by_name == {"app_name": "admin.App1", "days_back": 7}


def test_get_app_status_history_with_null_app_name(fake_client):
    settings = make_settings()
    queries.get_app_status_history(fake_client, settings, None, 7)

    params_by_name = {p.name: p.value for p in fake_client.calls[0]["params"]}
    assert params_by_name["app_name"] is None


def test_get_app_uptime(fake_client):
    settings = make_settings()
    queries.get_app_uptime(fake_client, settings, 30)
    assert "`proj.Vivek.get_app_uptime`(@days_back)" in fake_client.calls[0]["sql"]


def test_get_cluster_uptime(fake_client):
    settings = make_settings()
    queries.get_cluster_uptime(fake_client, settings, 30)
    assert "`proj.Vivek.get_cluster_uptime`(@days_back)" in fake_client.calls[0]["sql"]


def test_list_clusters(fake_client):
    settings = make_settings()
    fake_client.rows = [{"clusterName": "Bandhan"}, {"clusterName": "HDFC"}]

    result = queries.list_clusters(fake_client, settings)

    assert result == ["Bandhan", "HDFC"]
    assert "proj.Vivek.striim_mon_table_runhistory" in fake_client.calls[0]["sql"]
    assert fake_client.calls[0]["params"] == []


def test_health_check_true_when_ok_row_returned(fake_client):
    fake_client.rows = [{"ok": 1}]
    assert queries.health_check(fake_client) is True


def test_health_check_false_when_no_rows(fake_client):
    fake_client.rows = []
    assert queries.health_check(fake_client) is False


def test_dataset_ref_used_consistently_across_queries(fake_client):
    settings = make_settings(project_id="other-proj", bq_dataset="OtherDs")
    queries.get_app_uptime(fake_client, settings, 1)
    assert "`other-proj.OtherDs.get_app_uptime`" in fake_client.calls[0]["sql"]
