"""Forecast accuracy endpoints, including a CSV hand-off for the desk."""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from ..domain.settlement import decision_cutoff
from ..schemas import AccuracyReportOut
from ..services.analytics import PilotDataset, accuracy_report
from .deps import dataset_dependency, pilot_days

router = APIRouter(tags=["accuracy"])


def _window(start: date | None, end: date | None) -> list[date]:
    days = pilot_days()
    if start:
        days = [day for day in days if day >= start]
    if end:
        days = [day for day in days if day <= end]
    return days


@router.get(
    "/accuracy/report",
    response_model=AccuracyReportOut,
    summary="Full accuracy document: scores, calibration, skill, distribution",
)
def report(
    dataset: Annotated[PilotDataset, Depends(dataset_dependency)],
    start: Annotated[date | None, Query(description="First delivery date")] = None,
    end: Annotated[date | None, Query(description="Last delivery date")] = None,
    cutoff_hour: Annotated[int | None, Query(ge=0, le=23)] = None,
    cutoff_minute: Annotated[int | None, Query(ge=0, le=59)] = None,
) -> dict[str, Any]:
    days = _window(start, end)

    def cutoff_fn(day: date):
        return decision_cutoff(day, cutoff_hour, cutoff_minute)

    return accuracy_report(dataset, days, cutoff_fn=cutoff_fn)


@router.get(
    "/accuracy/export.csv",
    summary="Paired forecast/outturn rows as CSV",
    response_class=StreamingResponse,
)
def export_csv(
    dataset: Annotated[PilotDataset, Depends(dataset_dependency)],
    start: Annotated[date | None, Query()] = None,
    end: Annotated[date | None, Query()] = None,
    cutoff_hour: Annotated[int | None, Query(ge=0, le=23)] = None,
    cutoff_minute: Annotated[int | None, Query(ge=0, le=59)] = None,
) -> StreamingResponse:
    days = _window(start, end)

    def cutoff_fn(day: date):
        return decision_cutoff(day, cutoff_hour, cutoff_minute)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "delivery_date",
            "hour",
            "start_utc",
            "vintage_publish_utc",
            "lead_hours",
            "forecast_mw",
            "actual_mw",
            "residual_mw",
            "band_p10_mw",
            "band_p90_mw",
        ]
    )
    for row in dataset.realised_observations(days, cutoff_fn, as_of=dataset.as_of):
        writer.writerow(
            [
                row.delivery_date.isoformat(),
                row.hour,
                row.start_utc.isoformat() + "Z",
                row.publish_time.isoformat() + "Z" if row.publish_time else "",
                row.lead_hours if row.lead_hours is not None else "",
                round(row.forecast_mw, 2) if row.forecast_mw is not None else "",
                round(row.actual_mw, 2) if row.actual_mw is not None else "",
                round(row.residual_mw, 2) if row.residual_mw is not None else "",
                "",
                "",
            ]
        )
    buffer.seek(0)
    filename = f"gridbrick-wind-accuracy-{days[0] if days else 'pilot'}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
