"""System, metadata, delivery-day enumeration and ingestion control."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

import numpy as np
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select

from ..config import get_settings
from ..domain.demand import available_profiles
from ..domain.settlement import decision_cutoff, iso_utc
from ..models import IngestionRun, WindActual, WindForecast
from ..schemas import DeliveryDaysOut, IngestResultOut, MetaOut
from ..services.analytics import GB_WIND_CAPACITY_MW, PilotDataset, data_bounds
from ..services.ingest import ingest_window
from .deps import SessionDep, dataset_dependency, pilot_days

router = APIRouter(tags=["system"])


@router.get("/health", summary="Liveness and warehouse counters")
def health(session: SessionDep) -> dict[str, Any]:
    try:
        actuals = session.execute(select(func.count()).select_from(WindActual)).scalar_one()
        forecasts = session.execute(select(func.count()).select_from(WindForecast)).scalar_one()
        vintages = session.execute(select(func.count(func.distinct(WindForecast.publish_time)))).scalar_one()
        return {
            "status": "ok",
            "warehouse": {"actuals": actuals, "forecast_points": forecasts, "vintages": vintages},
        }
    except Exception as exc:
        return {"status": "degraded", "error": str(exc)[:200]}


@router.get("/meta", response_model=MetaOut, summary="Everything the UI needs to bootstrap")
def meta(session: SessionDep) -> dict[str, Any]:
    settings = get_settings()
    bounds = data_bounds(session)
    actuals = session.execute(select(func.count()).select_from(WindActual)).scalar_one()
    forecasts = session.execute(select(func.count()).select_from(WindForecast)).scalar_one()
    vintages = session.execute(select(func.count(func.distinct(WindForecast.publish_time)))).scalar_one()

    runs = session.execute(
        select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(5)
    ).scalars()

    return {
        "app": settings.app_name,
        "version": settings.version,
        "environment": settings.environment,
        "pilot": {
            "start": settings.pilot_start.isoformat(),
            "end": settings.pilot_end.isoformat(),
            "days": len(pilot_days()),
            "note": "Wind-only pilot: Elexon FUELHH outturn vs WINDFOR vintages.",
        },
        "data": {
            "actual_start_utc": iso_utc(bounds.actual_start) if bounds.actual_start else None,
            "actual_end_utc": iso_utc(bounds.actual_end) if bounds.actual_end else None,
            "forecast_publish_start_utc": iso_utc(bounds.forecast_publish_start)
            if bounds.forecast_publish_start
            else None,
            "forecast_publish_end_utc": iso_utc(bounds.forecast_publish_end)
            if bounds.forecast_publish_end
            else None,
            "latest_observable_utc": iso_utc(bounds.latest_observable) if bounds.latest_observable else None,
            "actuals": actuals,
            "forecast_points": forecasts,
            "vintages": vintages,
            "capacity_mw": GB_WIND_CAPACITY_MW,
        },
        "defaults": {
            "cutoff_hour": settings.default_cutoff_hour,
            "cutoff_minute": settings.default_cutoff_minute,
            "band_lookback_days": settings.band_lookback_days,
            "band_min_days": settings.band_min_days,
            "c_short": 1.5,
            "c_long": 1.0,
        },
        "demand_profiles": available_profiles(),
        "ingestion_runs": [
            {
                "started_at": iso_utc(run.started_at),
                "finished_at": iso_utc(run.finished_at) if run.finished_at else None,
                "status": run.status,
                "trigger": run.trigger,
                "actuals_upserted": run.actuals_upserted,
                "forecasts_upserted": run.forecasts_upserted,
                "message": run.message,
            }
            for run in runs
        ],
    }


@router.get("/delivery-days", response_model=DeliveryDaysOut, summary="Pilot days with availability state")
def delivery_days(
    dataset: Annotated[PilotDataset, Depends(dataset_dependency)],
    cutoff_hour: Annotated[int | None, Query(ge=0, le=23)] = None,
    cutoff_minute: Annotated[int | None, Query(ge=0, le=59)] = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for day in pilot_days():
        cutoff = decision_cutoff(day, cutoff_hour, cutoff_minute)
        vintage = dataset.vintage_for(day, cutoff)
        observations = dataset.observation(day, cutoff, dataset.as_of)
        paired = [o for o in observations if o.forecast_mw is not None and o.actual_mw is not None]
        realised = sum(1 for o in observations if o.actual_mw is not None)

        if dataset.as_of < cutoff:
            state = "pending_gate"
        elif realised == 0:
            state = "awaiting_outturn"
        elif realised < len(observations):
            state = "partial"
        else:
            state = "realised"

        mae = bias = None
        if paired:
            residuals = [o.forecast_mw - o.actual_mw for o in paired]  # type: ignore[operator]
            mae = round(float(np.mean([abs(r) for r in residuals])), 1)
            bias = round(float(np.mean(residuals)), 1)

        forecasts = [o.forecast_mw for o in observations if o.forecast_mw is not None]
        rows.append(
            {
                "delivery_date": day.isoformat(),
                "cutoff_utc": iso_utc(cutoff),
                "status": state,
                "vintage_publish_utc": iso_utc(vintage) if vintage else None,
                "vintage_age_hours": round((cutoff - vintage).total_seconds() / 3600.0, 2)
                if vintage
                else None,
                "hours_realised": realised,
                "mae_mw": mae,
                "bias_mw": bias,
                "forecast_mwh": round(float(sum(forecasts)), 0) if forecasts else None,
            }
        )

    return {"as_of_utc": iso_utc(dataset.as_of), "days": rows}


@router.post("/admin/ingest", response_model=IngestResultOut, summary="Pull fresh data from Elexon BMRS")
async def trigger_ingest(
    session: SessionDep,
    from_date: Annotated[date | None, Query(description="Publish-date lower bound")] = None,
    to_date: Annotated[date | None, Query(description="Publish-date upper bound")] = None,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> dict[str, Any]:
    settings = get_settings()
    if settings.admin_token and x_admin_token != settings.admin_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token")
    if not settings.allow_live_ingest:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="live ingestion disabled")

    start = datetime.combine(from_date, datetime.min.time()) if from_date else datetime.combine(settings.ingest_start, datetime.min.time())
    end = datetime.combine(to_date, datetime.min.time()) if to_date else datetime.combine(settings.ingest_end, datetime.min.time())

    run = await ingest_window(session, start, end, trigger="admin-api", settings=settings)
    counts = {
        "actuals": session.execute(select(func.count()).select_from(WindActual)).scalar_one(),
        "forecast_points": session.execute(select(func.count()).select_from(WindForecast)).scalar_one(),
    }
    return {
        "status": run.status,
        "trigger": run.trigger,
        "started_at": iso_utc(run.started_at),
        "finished_at": iso_utc(run.finished_at) if run.finished_at else None,
        "actuals_upserted": run.actuals_upserted,
        "forecasts_upserted": run.forecasts_upserted,
        "message": run.message,
        "warehouse": counts,
    }
