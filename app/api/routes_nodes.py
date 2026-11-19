from __future__ import annotations

from fastapi import APIRouter, Query

from app.config import get_settings
from app.models.schemas import NodeHealthResponse, NodeTrendResponse
from app.services import node_health

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


@router.get("/status", response_model=NodeHealthResponse)
def status(days_back: int = Query(default=1, ge=1, le=90)) -> NodeHealthResponse:
    return node_health.get_node_health(days_back)


@router.get("/trend", response_model=NodeTrendResponse)
def trend(days_back: int | None = Query(default=None, ge=1, le=90)) -> NodeTrendResponse:
    settings = get_settings()
    return node_health.get_node_trend(days_back or settings.node_trend_days_back)
