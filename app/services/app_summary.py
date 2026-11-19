from __future__ import annotations

from collections import Counter

from app.bigquery import queries
from app.bigquery.client import get_bq_client
from app.cache import cached
from app.config import get_settings
from app.models.schemas import (
    AppStatusCounts,
    AppStatusSummary,
    AppSummaryResponse,
    RawStatusCount,
    StatusBucketCount,
)


@cached("app_summary")
def get_app_summary(days_back: int) -> AppSummaryResponse:
    client = get_bq_client()
    settings = get_settings()

    rows = queries.get_app_status_summary(client, settings, days_back)
    if settings.cluster_name:
        rows = [r for r in rows if r["clusterName"] == settings.cluster_name]
    apps = [AppStatusSummary(**row) for row in rows]

    bucket_counts = Counter(a.status_bucket for a in apps)
    status_counts = Counter(a.appStatus for a in apps)

    counts = AppStatusCounts(
        total=len(apps),
        by_bucket=[
            StatusBucketCount(status_bucket=bucket, count=n)
            for bucket, n in sorted(bucket_counts.items())
        ],
        by_status=[
            RawStatusCount(appStatus=status, count=n)
            for status, n in sorted(status_counts.items())
        ],
    )

    return AppSummaryResponse(apps=apps, counts=counts)
