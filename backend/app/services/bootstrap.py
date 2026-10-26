"""Start-up bootstrap: make sure a fresh container has a usable warehouse."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from ..config import get_settings
from ..db import SessionLocal
from ..models import WindActual, WindForecast
from .ingest import ingest_window, load_seed, warehouse_is_empty

logger = logging.getLogger(__name__)


def warehouse_counts() -> dict[str, int]:
    with SessionLocal() as session:
        return {
            "actuals": session.execute(select(func.count()).select_from(WindActual)).scalar_one(),
            "forecast_points": session.execute(
                select(func.count()).select_from(WindForecast)
            ).scalar_one(),
        }


async def bootstrap() -> dict[str, Any]:
    """Load the committed seed on first boot; optionally refresh from BMRS.

    Seeding first is deliberate: it makes the container deterministic, works
    with no network access, and keeps cold-start latency low. A live pull is
    only a fallback.
    """
    settings = get_settings()
    with SessionLocal() as session:
        if not warehouse_is_empty(session):
            counts = warehouse_counts()
            logger.info("warehouse already populated: %s", counts)
            return {"status": "existing", **counts}

        seeded = load_seed(session)
        if seeded["actuals"] and seeded["forecasts"]:
            return {"status": "seeded", **seeded}

        if settings.allow_live_ingest:
            logger.info("no seed found; pulling from Elexon BMRS")
            start = datetime.combine(settings.ingest_start, datetime.min.time())
            end = datetime.combine(settings.ingest_end, datetime.min.time())
            run = await ingest_window(session, start, end, trigger="startup", settings=settings)
            return {"status": run.status, "message": run.message}

        logger.warning("warehouse is empty and live ingestion is disabled")
        return {"status": "empty"}
