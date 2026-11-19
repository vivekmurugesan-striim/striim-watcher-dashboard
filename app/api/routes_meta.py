from __future__ import annotations

from fastapi import APIRouter

from app.models.schemas import ClustersResponse, HealthResponse
from app.services import meta

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/clusters", response_model=ClustersResponse)
def clusters() -> ClustersResponse:
    return meta.get_clusters()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return meta.check_health()
