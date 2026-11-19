from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api import routes_apps, routes_meta, routes_nodes
from app.config import get_settings

settings = get_settings()
logging.basicConfig(level=settings.log_level)

WEB_DIR = Path(__file__).parent / "web"

app = FastAPI(title="StriimWatcher Dashboard")


@app.middleware("http")
async def no_cache_for_frontend_assets(request: Request, call_next):
    """StaticFiles sends an ETag/Last-Modified but no Cache-Control, which leaves browsers
    free to use their own heuristic caching for CSS/JS/HTML — in practice, a tab left open
    across a `docker compose up --build` can sit on stale assets indefinitely, since nothing
    in this app triggers a live reload and the auto-refresh timer only re-fetches /api/*, not
    the page's own CSS/JS. `no-cache` (not `no-store`) still lets the browser revalidate via
    the existing ETag — cheap 304s — it just stops a reload from silently skipping that check.
    """
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEB_DIR / "templates")

app.include_router(routes_meta.router)
app.include_router(routes_nodes.router)
app.include_router(routes_apps.router)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "cluster_name": settings.cluster_name or "all clusters (CLUSTER_NAME unset)",
            "auto_refresh_seconds": settings.auto_refresh_seconds,
            "node_trend_days_back": settings.node_trend_days_back,
            "app_history_default_days": settings.app_history_default_days,
            "app_uptime_default_days": settings.app_uptime_default_days,
        },
    )
