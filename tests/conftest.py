"""Shared test fakes. No test in this suite talks to real BigQuery — every test either mocks
the BigQuery Client object directly (test_queries.py) or mocks the services/ layer
(test_api.py).
"""

from __future__ import annotations

import os
from typing import Any

import pytest

# Settings requires PROJECT_ID at minimum; set a harmless default before anything imports
# app.config, so collection doesn't fail for whoever runs pytest without a real .env.
os.environ.setdefault("PROJECT_ID", "test-project")
os.environ.setdefault("BQ_DATASET", "test_dataset")


class FakeRow:
    """Mimics just enough of google.cloud.bigquery.table.Row for `dict(row)` to work —
    Row supports the mapping protocol via .keys()/__getitem__, which is what dict()'s
    keys()-based construction path relies on.
    """

    def __init__(self, data: dict[str, Any]):
        self._data = data

    def keys(self):
        return self._data.keys()

    def __getitem__(self, key):
        return self._data[key]


class FakeJob:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = [FakeRow(r) for r in rows]

    def result(self):
        return self._rows


class FakeBigQueryClient:
    """Records every query() call (sql + params) and returns pre-seeded rows."""

    def __init__(self, rows: list[dict[str, Any]] | None = None):
        self.rows = rows or []
        self.calls: list[dict[str, Any]] = []

    def query(self, sql: str, job_config=None):
        params = list(job_config.query_parameters) if job_config else []
        self.calls.append({"sql": sql, "params": params})
        return FakeJob(self.rows)


@pytest.fixture
def fake_client():
    return FakeBigQueryClient()


@pytest.fixture(autouse=True)
def _clear_service_cache():
    """The @cached decorator in app/cache.py uses one process-wide TTL cache. Without this,
    a test that seeds different fake data than an earlier test (but calls a service with the
    same args, e.g. days_back=1) would silently get back the earlier test's cached result.
    """
    from app.cache import clear_cache

    clear_cache()
    yield
    clear_cache()
