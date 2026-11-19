"""BigQuery client factory.

Two auth modes, both configurable via Settings (see app/config.py), covering the two realistic
ways this container gets BigQuery access:

- "adc" (default): Application Default Credentials — already present on the host/container via
  `gcloud auth application-default login`, an attached GCP service account, or Workload
  Identity. This is the same auth model the rest of this project's own scripts
  (standalone_alert_poller.py, alert_notifier_function/) already rely on.
- "service_account": an explicit service-account JSON key file, for hosts with no ambient GCP
  credentials (e.g. a bare Docker host) — mounted read-only and pointed to by
  GOOGLE_APPLICATION_CREDENTIALS.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from google.cloud import bigquery
from google.oauth2 import service_account

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _build_client(settings: Settings) -> bigquery.Client:
    if settings.bq_auth_mode == "service_account":
        if not settings.google_application_credentials:
            raise RuntimeError(
                "BQ_AUTH_MODE=service_account requires GOOGLE_APPLICATION_CREDENTIALS to "
                "point at a mounted service-account JSON key file."
            )
        credentials = service_account.Credentials.from_service_account_file(
            settings.google_application_credentials
        )
        return bigquery.Client(project=settings.project_id, credentials=credentials)

    return bigquery.Client(project=settings.project_id)


@lru_cache
def get_bq_client() -> bigquery.Client:
    settings = get_settings()
    logger.info(
        "Initializing BigQuery client: project=%s dataset=%s auth_mode=%s",
        settings.project_id,
        settings.bq_dataset,
        settings.bq_auth_mode,
    )
    return _build_client(settings)
