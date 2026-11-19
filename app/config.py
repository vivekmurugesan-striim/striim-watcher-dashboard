"""All app configuration, sourced from environment variables / a mounted .env file.

Every value here is read exactly once per process (see get_settings()'s lru_cache) and is
documented in full in .env.example at the project root — that file is the reference a reader
should check first for defaults and meaning.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # -- BigQuery connection -------------------------------------------------
    project_id: str
    bq_dataset: str = "Vivek"
    bq_auth_mode: Literal["adc", "service_account"] = "adc"
    google_application_credentials: str | None = None

    # -- Scope -------------------------------------------------------------
    # The one Striim cluster this instance watches. When set, every service-layer function
    # filters its rows to clusterName == cluster_name before returning them — the underlying
    # Dashboard-Queries functions stay generic/multi-cluster-aware and are untouched; only this
    # app's own response shaping is single-cluster. When unset, responses are unfiltered
    # (useful for a dataset already scoped to one cluster, or local testing) — see
    # GET /api/meta/clusters, which stays unfiltered in both cases as a diagnostic check.
    cluster_name: str | None = None

    # -- Default lookback windows (all overridable per-request via query params) --
    # node_trend_days_back doubles as both the Node Health snapshot window and the CPU-trend
    # chart window (see app/web/static/js/main.js). 7, not 1: get_node_status/get_app_status_
    # summary only look back this many days from *now* for the latest poll — a value too close
    # to StriimWatcher's own polling interval means any brief gap (restart, maintenance, a
    # dev/test cluster that's simply idle) makes the whole panel look empty rather than showing
    # the last known state. 7 days tolerates that without making the trend chart unreadable.
    node_trend_days_back: int = 7
    app_history_default_days: int = 7
    app_uptime_default_days: int = 30

    # -- Behaviour -------------------------------------------------------------
    query_cache_ttl_seconds: int = 60
    auto_refresh_seconds: int = 60

    # -- Server ----------------------------------------------------------------
    app_port: int = 8080
    log_level: str = "INFO"

    @property
    def dataset_ref(self) -> str:
        """Fully-qualified `project.dataset` prefix, e.g. 'my-gcp-project.Vivek'."""
        return f"{self.project_id}.{self.bq_dataset}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
