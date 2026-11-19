"""API response models. Field names intentionally mirror the BigQuery function column names
(camelCase and all) rather than being renamed to snake_case — this keeps a response row
traceable 1:1 back to the `Dashboard-Queries` function that produced it, which matters more
here than Python naming convention purity.

Identity fields (clusterName, nodeName, appName) are all `str | None` rather than required
`str`, even though that looks odd for what's conceptually a primary key. Confirmed against
real data in the Vivek dataset: `get_node_status()` can return a row with `nodeName = NULL`
(no NOT NULL constraint anywhere in the underlying striim_mon_* DDL), and FastAPI/Pydantic
will 500 the whole endpoint on one unexpected NULL otherwise. Status/bucket/RAG fields stay
required `str` — those come from SQL CASE expressions that always produce a value, never a
passthrough of a raw nullable column.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


# -- Node health --------------------------------------------------------------


class NodeStatus(BaseModel):
    clusterName: str | None = None
    nodeName: str | None = None
    status: str
    cpurate: float | None = None
    freemem: str | None = None
    striimversion: str | None = None
    uptime: str | None = None
    last_seen_batchdate: datetime | None = None
    latest_cluster_batchdate: datetime | None = None
    RAG_status: str | None = None


class ClusterNodeSummary(BaseModel):
    clusterName: str | None = None
    total_nodes: int
    nodes_up: int
    nodes_down: int
    latest_batchdate: datetime | None = None
    RAG_status: str


class NodeHealthResponse(BaseModel):
    clusters: list[ClusterNodeSummary]
    nodes: list[NodeStatus]


class NodeTrendPoint(BaseModel):
    clusterName: str | None = None
    nodeName: str | None = None
    hour: datetime
    avg_cpurate: float | None = None
    avg_freemem_gb: float | None = None
    sample_count: int
    latest_freemem: str | None = None


class NodeTrendResponse(BaseModel):
    days_back: int
    points: list[NodeTrendPoint]


# -- Applications ---------------------------------------------------------------


class AppStatusSummary(BaseModel):
    clusterName: str | None = None
    appName: str | None = None
    appStatus: str
    status_bucket: str
    isBackpressured: bool | None = None
    checkpointStatus: str | None = None
    isRecoveryEnabled: bool | None = None
    totalInput: int | None = None
    totalOutput: int | None = None
    deploymentOn: str | None = None
    latestActivity: datetime | None = None
    latest_batchdate: datetime | None = None
    # NULL for most apps in practice — see get_app_status_summary.sql's header comment for
    # exactly which StriimWatcher signals this is built from and why coverage is partial.
    sourceTypes: str | None = None
    targetTypes: str | None = None


class StatusBucketCount(BaseModel):
    status_bucket: str
    count: int


class RawStatusCount(BaseModel):
    appStatus: str
    count: int


class AppStatusCounts(BaseModel):
    """Two breakdowns, not one: by_bucket uses get_app_uptime's UP/DOWN/OTHER taxonomy (the
    one meaningful across this whole project), by_status uses the raw appStatus values
    actually present (RUNNING, HALT, CRASH, STOPPED, CREATED, DEPLOYED, ... — whatever this
    deployment's apps are really reporting, not a hardcoded guess at the full vocabulary).
    """

    total: int
    by_bucket: list[StatusBucketCount]
    by_status: list[RawStatusCount]


class AppSummaryResponse(BaseModel):
    apps: list[AppStatusSummary]
    counts: AppStatusCounts


class AppStatusHistoryPoint(BaseModel):
    clusterName: str | None = None
    appName: str | None = None
    hour: datetime
    appStatus: str
    batchdate: datetime


class AppStatusHistoryResponse(BaseModel):
    appName: str | None = None
    days_back: int
    points: list[AppStatusHistoryPoint]


class AppUptime(BaseModel):
    clusterName: str | None = None
    appName: str | None = None
    up_minutes: int
    down_minutes: int
    total_observed_minutes: int
    uptime_pct: float | None = None


class ClusterUptime(BaseModel):
    clusterName: str | None = None
    app_count: int
    up_minutes: int
    down_minutes: int
    total_observed_minutes: int
    uptime_pct: float | None = None
    avg_of_app_uptime_pct: float | None = None


class ClusterUptimeResponse(BaseModel):
    days_back: int
    clusters: list[ClusterUptime]


# -- Meta -----------------------------------------------------------------------


class ClustersResponse(BaseModel):
    clusters: list[str]


class HealthResponse(BaseModel):
    status: str
    project_id: str
    dataset: str
