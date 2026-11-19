from __future__ import annotations

from fastapi import APIRouter, Query

from app.config import get_settings
from app.models.schemas import (
    AppStatusHistoryResponse,
    AppSummaryResponse,
    AppUptime,
    ClusterUptimeResponse,
)
from app.services import app_history, app_summary

router = APIRouter(prefix="/api", tags=["apps"])


@router.get("/apps/summary", response_model=AppSummaryResponse)
def summary(days_back: int = Query(default=1, ge=1, le=90)) -> AppSummaryResponse:
    return app_summary.get_app_summary(days_back)


@router.get("/apps/{app_name}/history", response_model=AppStatusHistoryResponse)
def history(
    app_name: str,
    days_back: int | None = Query(default=None, ge=1, le=90),
) -> AppStatusHistoryResponse:
    settings = get_settings()
    return app_history.get_app_status_history(app_name, days_back or settings.app_history_default_days)


@router.get("/apps/{app_name}/uptime", response_model=AppUptime | None)
def app_uptime(
    app_name: str,
    days_back: int | None = Query(default=None, ge=1, le=365),
) -> AppUptime | None:
    settings = get_settings()
    rows = app_history.get_app_uptime(days_back or settings.app_uptime_default_days, app_name=app_name)
    return rows[0] if rows else None


@router.get("/cluster/uptime", response_model=ClusterUptimeResponse)
def cluster_uptime(days_back: int | None = Query(default=None, ge=1, le=365)) -> ClusterUptimeResponse:
    """Named singular — this app watches exactly one cluster (CLUSTER_NAME). The response still
    wraps a list (0 or 1 items) for schema consistency with the rest of the API, not because
    multiple clusters are expected here."""
    settings = get_settings()
    return app_history.get_cluster_uptime(days_back or settings.app_uptime_default_days)
