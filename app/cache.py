"""A single shared TTL cache for the service layer.

StriimWatcher polls every 5 minutes by default — there's no value in BigQuery round-trips more
often than that, and these are billed queries. QUERY_CACHE_TTL_SECONDS (default 60s) controls
how stale the dashboard is willing to be in exchange for far fewer BigQuery calls under normal
browsing/auto-refresh.

Deliberately scoped to the *service* layer (business-logic args like days_back/app_name only)
rather than the bigquery/queries.py layer — caching there would mean baking a BigQuery Client
object into every cache key, which is both unnecessary (one client per process) and makes the
query layer's own unit tests awkward to reason about.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar

from cachetools import TTLCache

from app.config import get_settings

_cache: TTLCache | None = None

F = TypeVar("F", bound=Callable[..., Any])


def _get_cache() -> TTLCache:
    global _cache
    if _cache is None:
        settings = get_settings()
        _cache = TTLCache(maxsize=512, ttl=settings.query_cache_ttl_seconds)
    return _cache


def clear_cache() -> None:
    """Used by tests to guarantee a clean cache between cases."""
    global _cache
    _cache = None


def cached(key_prefix: str) -> Callable[[F], F]:
    """Cache a function's return value, keyed by key_prefix + its call arguments.

    Only use on functions whose arguments are simple and hashable (str / int / None) — exactly
    the shape every services/* function has.
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache = _get_cache()
            key = (key_prefix, args, tuple(sorted(kwargs.items())))
            if key in cache:
                return cache[key]
            result = fn(*args, **kwargs)
            cache[key] = result
            return result

        return wrapper  # type: ignore[return-value]

    return decorator
