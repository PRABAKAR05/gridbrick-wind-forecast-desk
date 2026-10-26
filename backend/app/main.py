"""GridBrick Forecast Desk - API entrypoint.

Run locally:  uvicorn app.main:app --reload --port 8000
Docs:         http://localhost:8000/docs
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from .api import accuracy, decision, procurement, system
from .config import get_settings
from .db import init_db
from .services.bootstrap import bootstrap
from .services.elexon import ElexonError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s :: %(message)s",
)
logger = logging.getLogger("gridbrick")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    result = await bootstrap()
    logger.info("bootstrap: %s", result)
    yield
    logger.info("shutdown")


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    summary="Day-ahead wind forecast intelligence for a GB energy utility.",
    description=(
        "Quantifies the accuracy of Elexon WINDFOR wind forecasts **as they were "
        "available at day-ahead gate closure**, and converts that quantified error "
        "into a risk-adjusted procurement quantity.\n\n"
        "## Point-in-time contract\n"
        "Every endpoint accepts an `as_of` instant. A response may only depend on "
        "data published on or before that instant, and forecasts are always selected "
        "by `publish_time <= cutoff`. This is what keeps the accuracy scores honest.\n\n"
        "## Units\n"
        "Generation is MW at hourly resolution; because each value is the mean over "
        "one hour, summing hourly MW gives MWh directly."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Process-Time-Ms"],
)
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def observe(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration = (time.perf_counter() - started) * 1000
        logger.exception("%s %s failed after %.0fms", request.method, request.url.path, duration)
        raise
    duration = (time.perf_counter() - started) * 1000
    response.headers["X-Process-Time-Ms"] = f"{duration:.1f}"
    if request.url.path.startswith("/api"):
        logger.info(
            "%s %s -> %s (%.0fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration,
        )
    return response


@app.exception_handler(ElexonError)
async def elexon_error_handler(_request: Request, exc: ElexonError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"detail": "Upstream Elexon feed unavailable", "upstream_error": str(exc)[:300]},
    )


API_PREFIX = "/api/v1"
app.include_router(system.router, prefix=API_PREFIX)
app.include_router(decision.router, prefix=API_PREFIX)
app.include_router(accuracy.router, prefix=API_PREFIX)
app.include_router(procurement.router, prefix=API_PREFIX)


@app.get("/", include_in_schema=False)
def root() -> dict[str, Any]:
    return {
        "name": settings.app_name,
        "version": settings.version,
        "docs": "/docs",
        "api": API_PREFIX,
        "health": f"{API_PREFIX}/health",
    }
